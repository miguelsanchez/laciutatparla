#!/usr/bin/env python3
"""Fix the interventions that break the language rule (C4) and turn the fix into proposals.

The rule (classification.py): idioma_original is the language of more than 50 % of the speech,
by paragraph; the text in that language is text_original verbatim (script 07 fills an empty one
from it); the other is a full translation. For each intervention C4 flags, this proposes one
patches.yml entry with what it needs:

  idioma          → idioma_original: <the majority language>
  original-<f>    → <f>: ""     (script 07 then publishes text_original, bold included)
  untranslated-<f>→ <f>: a new translation of text_original, from Haiku

The translation prompt only translates: it keeps the paragraphs, the ** markers, names and the
anonymisation marks, and never touches text_original. Each result is checked (same paragraphs
and **, no paragraph left in the source language, sane length) and retried once if it fails.
Results are cached in $LCP_QA_STATE/retranslate/, so a second run costs nothing.

    "$PY" scripts/qa/retranslate.py --dry-run                     # what and how much, no API
    "$PY" scripts/qa/retranslate.py --translate                   # call Haiku for the missing ones
    "$PY" scripts/qa/retranslate.py --proposals proposals.json    # propose.py input, no API
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from qa.checks.classification import (C4_RATIO, LANGS, TEXT_FIELD, detect_language,  # noqa: E402
                                      foreign_paragraphs, language_findings, majority_language)
from qa.model import REPO_ROOT, Context, Finding, state_dir  # noqa: E402

MODEL = "claude-haiku-5-5"
PRICE = (0.10, 0.50)   # $ per MTok in/out, prompts under 100k tokens
NAMES = {"castellano": "Spanish (castellano)", "valenciano": "Valencian (valencià)"}

SYSTEM = """You translate citizen speeches given at the plenary sessions of València City Council, \
between Spanish (castellano) and Valencian. You only translate: you never summarise, shorten, \
explain, correct or add anything.

Rules:
- Translate the whole speech into the target language. Any part already in the target language \
stays exactly as it is. Nothing may remain in the other language: greetings, short sentences, \
quotes and interjections are translated too.
- Valencian means standard Valencian as the City Council writes it (AVL norms): "este/esta", \
"hui", "eixe", "servici", first person in -e ("demane").
- Keep the paragraph breaks exactly: the same number of paragraphs, separated as in the input.
- Keep every **bold** marker: put each pair around the translation of the same phrase, with the \
same number of ** as the input.
- Keep proper names, organisation names, acronyms and street or barrio names as written. Keep \
anonymisation marks such as [***] or [*] unchanged.
- Reply with the translated speech only: no preface, no notes, no tags."""


def _paras(text: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", text or "") if p.strip()])


def problems(source: str, result: str, target: str) -> list[str]:
    """What is wrong with a translation; [] when it can be used."""
    out = []
    if _paras(result) != _paras(source):
        out.append(f"{_paras(result)} paragraphs, the input has {_paras(source)}")
    if result.count("**") != source.count("**"):
        out.append(f"{result.count('**')} ** markers, the input has {source.count('**')}")
    bad = foreign_paragraphs(result, target)
    if bad:
        out.append(f"{len(bad)} paragraph(s) not in {NAMES[target]}: «{bad[0][:80]}»")
    ratio = len(result) / max(len(source), 1)
    if not C4_RATIO[0] <= ratio <= C4_RATIO[1]:
        out.append(f"length is {ratio:.2f}× the input")
    if re.match(r"\s*(<|here is|aquí|translation)", result, re.I):
        out.append("starts with a preface or a tag")
    return out


# ── What C4 asks for ─────────────────────────────────────────────────────────

RESUM = {"castellano": "resum_cas", "valenciano": "resum_val"}


def plan(ctx: Context) -> dict[str, dict]:
    """iv_id → {"iv", "findings", "lang", "idioma", "original", "translate", "resums"} for each
    flagged intervention. `resums` are the summaries C4 reads in the wrong language: they are
    translated from the other summary."""
    out = {}
    for iv in ctx.interventions_raw:
        iv_id = str(iv["id"])
        fs = [f for f in language_findings(iv) if f.key == "idioma" or f.key.startswith(("original-", "untranslated-"))]
        resums = []
        for want, field in RESUM.items():
            got = detect_language(iv.get(field))
            if got and got != want:
                resums.append(field)
                fs.append(Finding(check="C4", severity="P1", subject=iv_id, key=f"lang-{field}",
                                  message=f"{field} reads as {got}, not {want}",
                                  details={"pleno_id": iv.get("pleno_id"), "field": field}))
        if not fs:
            continue
        by = {f.key.split("-", 1)[0]: f for f in fs}
        lang = by["idioma"].details["idioma"] if "idioma" in by else iv["idioma_original"]
        out[iv_id] = {
            "iv": iv, "findings": fs, "lang": lang,
            "idioma": "idioma" in by,
            "original": by["original"].details["field"] if "original" in by else None,
            "translate": by["untranslated"].details["field"] if "untranslated" in by else None,
            "resums": resums,
        }
    return out


def jobs(it: dict) -> list[tuple[str, str, str]]:
    """(field, source text, target language) of each translation an item needs."""
    out = []
    if it["translate"]:
        out.append((it["translate"], it["iv"]["text_original"], LANGS[1 - LANGS.index(it["lang"])]))
    for field in it.get("resums", []):
        target = next(l for l, f in RESUM.items() if f == field)
        out.append((field, it["iv"].get(RESUM[LANGS[1 - LANGS.index(target)]]) or "", target))
    return out


def cache_path(cache: Path, iv_id: str, field: str) -> Path:
    return cache / f"{iv_id}.{field}.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def cached(cache: Path, iv_id: str, field: str, source: str) -> dict | None:
    p = cache_path(cache, iv_id, field)
    if not p.exists():
        return None
    c = json.loads(p.read_text(encoding="utf-8"))
    return c if c.get("source_sha256") == _sha(source) else None


# ── Haiku ────────────────────────────────────────────────────────────────────

def _client():
    import anthropic
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC")
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def translate(client, source: str, target: str) -> tuple[str, list[str], dict]:
    """(translation, problems, usage). One retry, told what was wrong with the first answer."""
    messages = [{"role": "user", "content": f"Translate this speech into {NAMES[target]}.\n\n{source}"}]
    usage = {"input_tokens": 0, "output_tokens": 0}
    text, issues = "", ["no answer"]
    for _attempt in range(2):
        resp = client.messages.create(model=MODEL, max_tokens=16000, system=SYSTEM, messages=messages,
                                      output_config={"effort": "low"})
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        if resp.stop_reason == "refusal":
            return "", ["refused"], usage
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason == "max_tokens":
            issues = ["cut at max_tokens"]
        else:
            issues = problems(source, text, target)
        if not issues:
            break
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "That translation has these problems: " + "; ".join(issues)
                      + ". Reply with the corrected full translation only."}]
    return text, issues, usage


def language_rule(entry: dict, translate) -> tuple[dict, str | None]:
    """Apply the language rule to a new intervention before it is saved (script 05,
    complete_manual.py): idioma_original is the majority language by paragraph, the text in that
    language is left empty (script 07 publishes text_original), and the other is a full
    translation, redone with `translate(text, target)` (→ translate() above) when it has
    paragraphs left in the original language.

    Returns (entry with the rule applied, None), or (entry with as much applied as possible, why
    it still breaks the rule): complete_manual.py then writes nothing, script 05 keeps it with a
    validation warning and C4 flags it."""
    new = dict(entry)
    lang = majority_language(new.get("text_original") or "") or new.get("idioma_original")
    if lang not in LANGS:
        return new, "language rule: cannot tell the language of text_original"
    other = LANGS[1 - LANGS.index(lang)]
    new["idioma_original"] = lang
    new[TEXT_FIELD[lang]] = ""
    if any(f.key.startswith("untranslated-") for f in language_findings(new)):
        text, issues, _usage = translate(new["text_original"], other)
        if issues:
            return new, f"language rule: {TEXT_FIELD[other]} retranslation failed ({'; '.join(issues)})"
        new[TEXT_FIELD[other]] = text
    left = [f.message for f in language_findings(new)]
    return new, ("language rule: " + "; ".join(left)) if left else None


# ── Proposals for propose.py ─────────────────────────────────────────────────

def proposals(items: dict[str, dict], cache: Path, patches: list[dict]) -> tuple[list[dict], list[str]]:
    """(propose.py input, ids left out because their translation is missing or failed)."""
    existing = {str(e["iv_id"]): e for e in patches if isinstance(e, dict)}
    out, missing = [], []
    for iv_id, it in sorted(items.items()):
        iv, fields, done = it["iv"], {}, []
        if it["idioma"]:
            fields["idioma_original"] = it["lang"]
            done.append(f"idioma_original {iv.get('idioma_original')} → {it['lang']}")
        if it["original"]:
            fields[it["original"]] = ""
            done.append(f"{it['original']} = text_original")
        results = {field: cached(cache, iv_id, field, source) for field, source, _ in jobs(it)}
        if any(not c or c["problems"] for c in results.values()):
            missing.append(iv_id)   # never half-fixed: the whole intervention waits for its translations
            continue
        for field, c in results.items():
            fields[field] = c["text"]
            src = "text_original" if field.startswith("text_") else ("resum_val" if field == "resum_cas" else "resum_cas")
            done.append(f"{field} retranslated from {src} ({MODEL})")
        reason = "Language rule (C4): " + "; ".join(done) + "."
        old = existing.get(iv_id)
        entry = {"iv_id": iv_id, "fields": fields, "reason": reason}
        if old:
            entry = {k: v for k, v in old.items() if k not in ("date", "finding")}
            entry["fields"] = {**old["fields"], **fields}
            entry["reason"] = f"{old['reason']}; {reason}" if old.get("reason") else reason
        top = min(it["findings"], key=lambda f: f.severity)
        out.append({
            "fp": top.fp, "check": "C4", "severity": top.severity, "subject": iv_id,
            "title": "; ".join(done),
            "message": "\n".join(f"- {f.severity} `{f.key}`: {f.message}" for f in it["findings"]),
            "evidence": {"file": f"data/raw/texts/{iv.get('pleno_id')}.txt", "quote": None},
            "file": "patches.yml", "section": None, "entry": entry,
            "op": "replace" if old else "append",
        })
    return out, missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="list what C4 asks for and the cost, no API")
    mode.add_argument("--translate", action="store_true", help="translate what is not cached yet (API)")
    mode.add_argument("--proposals", type=Path, help="write the propose.py input here (no API)")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--cache", type=Path, default=None, help="default $LCP_QA_STATE/retranslate")
    ap.add_argument("--ids", help="comma-separated iv ids to limit the run to")
    args = ap.parse_args(argv)

    cache = (args.cache or state_dir() / "retranslate").expanduser()
    ctx = Context(args.data_dir)
    items = plan(ctx)
    if args.ids:
        keep = set(args.ids.split(","))
        items = {k: v for k, v in items.items() if k in keep}
    todo = [(k, field, source, target) for k, v in items.items() for field, source, target in jobs(v)
            if not ((c := cached(cache, k, field, source)) and not c["problems"])]

    if args.dry_run:
        n = lambda key: sum(bool(v[key]) for v in items.values())  # noqa: E731
        chars = sum(len(source) for _, _, source, _ in todo)
        tok = chars / 3.2 + 450 * len(todo)   # system prompt per call
        cost = tok * PRICE[0] / 1e6 + chars / 3.2 * PRICE[1] / 1e6
        print(f"{len(items)} interventions: {n('idioma')} idioma_original, {n('original')} original text, "
              f"{n('translate')} translations, {n('resums')} summaries ({len(todo)} not cached yet)")
        print(f"to translate: {chars} chars ≈ {tok:,.0f} tokens in; ≈ ${cost:.2f} with {MODEL} (one attempt each)")
        return 0

    if args.translate:
        cache.mkdir(parents=True, exist_ok=True)
        client, total = _client(), {"input_tokens": 0, "output_tokens": 0}
        for i, (iv_id, field, source, target) in enumerate(todo, 1):
            text, issues, usage = translate(client, source, target)
            for k in total:
                total[k] += usage[k]
            cache_path(cache, iv_id, field).write_text(json.dumps(
                {"iv_id": iv_id, "field": field, "target": target, "model": MODEL,
                 "source_sha256": _sha(source), "text": text, "problems": issues, "usage": usage},
                ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[{i}/{len(todo)}] {iv_id} {field}: {'ok' if not issues else 'FAILED: ' + '; '.join(issues)}",
                  flush=True)
        cost = total["input_tokens"] * PRICE[0] / 1e6 + total["output_tokens"] * PRICE[1] / 1e6
        print(f"usage: {total['input_tokens']:,} in, {total['output_tokens']:,} out ≈ ${cost:.3f}")
        return 0

    patches = yaml.safe_load((args.data_dir / "corrections" / "patches.yml").read_text(encoding="utf-8")) or []
    props, missing = proposals(items, cache, patches)
    args.proposals.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(props)} proposals → {args.proposals}"
          + (f"; {len(missing)} left out (translation missing or failed): {', '.join(missing)}" if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

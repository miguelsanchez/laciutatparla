#!/usr/bin/env python3
"""Complete manual interventions that only carry the acta's text (arquitectura-agentes F2).

The extraction-reviewer recovers missed speakers with their literal `text_original`, but a
manual intervention also needs what script 05 would have produced: both translations (with
bold markers), both summaries, temes_v2, ambit, zones, districts and CAP codes. Without them
/apply-approved fails on C1/C5.

This runs script 05's own per-block extraction (`parse_block_with_claude`, one Haiku call, about
a cent each) on the entry, and fills **only the fields that are missing**. It never changes
text_original, intervinient or entitat: the acta's words and the attribution stay as reviewed.
Entries are rewritten in place in data/corrections/manual_interventions.yml of the QA worktree.

Before writing, the entry must pass the language rule (C4, `language_rule`): idioma_original by
paragraph, the text in that language empty (it is text_original), the other a full translation.
A translation script 05 left half done is redone with retranslate.py's prompt; if it still
fails, the entry is not written. (2026-04-30-102 was published with text_val in castellano.)

    "$PY" scripts/qa/complete_manual.py --worktree ../lcp-qa --dry-run     # which ones, no API
    "$PY" scripts/qa/complete_manual.py --worktree ../lcp-qa --commit      # fill, check C4 and N7, commit
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa import proposals as P  # noqa: E402
from qa.checks.classification import TEXT_FIELD  # noqa: E402
from qa.model import REPO_ROOT, Context, load_script, state_dir  # noqa: E402
from qa.retranslate import language_rule  # noqa: E402

FILE = "manual_interventions.yml"
# What script 05 produces and a manual intervention needs (C1/C5)
FILLED = ("text_cas", "text_val", "resum_cas", "resum_val", "temes_v2", "ambit", "zones", "districtes",
          "cap_major", "cap_subtopics", "idioma_original", "tipus_entitat")
REQUIRED = ("text_cas", "text_val", "resum_cas", "resum_val", "temes_v2", "ambit")
KEEP = ("id", "pleno_id", "ordre", "intervinient", "entitat", "text_original")
ANONYMISED_FIELDS = ("intervinient", "text_original", "text_cas", "text_val", "resum_cas", "resum_val")


def _empty(v) -> bool:
    return v is None or (isinstance(v, (str, list, dict)) and not v)


def incomplete(entries: list, raw_by_id: dict | None = None) -> list[dict]:
    """Entries that miss a required field both in the YAML and in interventions_raw.json.

    Older manual interventions were enriched in interventions_raw.json directly (bold_highlights,
    reclassify…), not in the YAML: filling their YAML would make apply_merges overwrite that
    published classification. Only interventions not yet complete anywhere are taken."""
    raw_by_id = raw_by_id or {}

    def has(e, f):
        raw = raw_by_id.get(str(e.get("id"))) or {}
        if f == TEXT_FIELD.get(e.get("idioma_original") or raw.get("idioma_original")):
            return True   # the text in the original language is text_original: empty by design
        return not _empty(e.get(f)) or not _empty(raw.get(f))
    return [e for e in entries if isinstance(e, dict) and e.get("text_original")
            and not all(has(e, f) for f in REQUIRED)]


def block_for(entry: dict) -> str:
    """The entry as an acta block, the shape script 05's prompt expects."""
    return f"{entry.get('intervinient') or ''} ({entry.get('entitat') or ''}):\n“{entry['text_original'].strip()}”"


def complete(entry: dict, extracted: dict, raw: dict | None = None) -> dict:
    """Fill the fields missing both in the entry and in its interventions_raw.json record: a value
    already published there (an older manual intervention's classification) is never replaced."""
    new = dict(entry)
    raw = raw or {}
    for f in FILLED:
        if _empty(new.get(f)) and _empty(raw.get(f)) and not _empty(extracted.get(f)):
            new[f] = extracted[f]
    for f in KEEP:                 # belt and braces: the reviewed fields never move
        if f in entry:
            new[f] = entry[f]
    return new


def anonymise(entry: dict) -> dict:
    """Write the acta's censored names (******) as [***], as script 05 does. A manual intervention
    copies the acta's text, and six asterisks read as three bold markers (PR #100: C1 "número
    impar de **" on 10 interventions, and bold that swallowed the next words on the web)."""
    return {k: re.sub(r"\[?\*{3,}\]?", "[***]", v) if k in ANONYMISED_FIELDS and isinstance(v, str) else v
            for k, v in entry.items()}


def tidy_geography(entry: dict, barris_ref: list) -> tuple[dict, list[str]]:
    """Make ambit, zones and districtes agree, as script 07 and C3 expect; return what to check.

    Script 05 on a lone speech often gets this wrong (PRs #90, #95): "L'Eixample > El Pla Del
    Remei" prefixes, names that are not barrios ("Horno de Alcedo"), and ambit ciutat with a list
    of barrios. Zones are normalised as script 07 does and unknown ones dropped; ciutat and
    area_metropolitana carry none. A barri ambit left without a barrio is only reported."""
    if not barris_ref:
        return entry, []
    build = load_script("07_build_final_json.py")
    lookup = build._build_barri_lookup(barris_ref)
    new, notes = dict(entry), []
    zones, dists = build.normalize_zones(entry.get("zones") or [], entry.get("districtes") or [], lookup)
    unknown = [z for z in zones if z.lower() not in lookup]
    if unknown:
        notes.append(f"dropped zones that are not barrios: {unknown}")
    zones = [z for z in zones if z.lower() in lookup]
    ambit = entry.get("ambit")
    if ambit in ("ciutat", "area_metropolitana") and (zones or dists):
        notes.append(f"ambit {ambit}: dropped zones {zones} and districtes {dists}")
        zones, dists = [], []
    if ambit in ("barri", "multi_barri") and not zones:
        notes.append(f"ambit {ambit} without a barrio: set ambit or zones by hand")
    if ambit in ("districte", "multi_districte") and not dists:
        notes.append(f"ambit {ambit} without a district: set ambit or districtes by hand")
    if "zones" in entry or zones:
        new["zones"] = zones
    if "districtes" in entry or dists:
        new["districtes"] = dists
    return new, notes


def untranslated_starts(entry: dict, n: int = 6) -> list[str]:
    """Paragraphs of the translation that open with the same n words as a paragraph of
    text_original: script 05 sometimes leaves the start of a paragraph in the original language
    (2012-12-28-101, «Simplemente queremos acompañarles en una **visita guiada** per un edifici…»),
    which the language rule misses when the rest is translated. Only the start is compared:
    castellano and valenciano share many runs of words («la millora de la mobilitat»)."""
    lang = entry.get("idioma_original")
    other = {"valenciano": "text_cas", "castellano": "text_val"}.get(lang)
    if not other or not entry.get(other):
        return []
    def start(text):
        words = re.findall(r"\w+", text.replace("**", "").lower())
        return tuple(words[:n]) if len(words) >= n else None
    source = {start(p) for p in re.split(r"\n\s*\n", entry.get("text_original") or "")} - {None}
    return [p.strip()[:80] for p in re.split(r"\n\s*\n", entry[other]) if start(p) in source]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--worktree", type=Path, required=True, help="the QA worktree on the data PR's branch")
    ap.add_argument("--only", action="append", help="intervention id (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be completed; no API call")
    ap.add_argument("--commit", action="store_true", help="commit each completed entry in the worktree")
    args = ap.parse_args(argv)

    wt = args.worktree.resolve()
    corrections = wt / "data" / "corrections"
    ctx = Context(wt / "data", repo_root=wt)
    raw_by_id = {str(iv.get("id")): iv for iv in ctx.interventions_raw}
    todo = incomplete(ctx.corrections(FILE) or [], raw_by_id)
    if args.only:
        todo = [e for e in todo if str(e.get("id")) in set(args.only)]
    print(f"complete_manual: {len(todo)} manual interventions to complete in {wt.name}")
    for e in todo:
        missing = [f for f in FILLED if _empty(e.get(f))]
        print(f"  {e['id']}  {e.get('intervinient')} ({e.get('entitat')})  "
              f"{len(e['text_original']):,} chars · missing: {', '.join(missing)}")
    if args.dry_run or not todo:
        print("(dry run: no API call)" if args.dry_run else "nothing to do.")
        return 0

    from qa.run_agents import load_api_key
    key = load_api_key()
    if not key:
        print("complete_manual: no API key (ANTHROPIC_API_KEY or .env)", file=sys.stderr)
        return 2
    os.environ["ANTHROPIC_API_KEY"] = key
    s05 = load_script("05_parse_interventions.py")
    from qa import retranslate
    from qa.propose import n7_errors
    client = None

    def translator(text, target):
        nonlocal client
        client = client or retranslate._client()
        return retranslate.translate(client, text, target)

    ref = wt / "data" / "raw" / "barris_referencia.json"
    barris_ref = json.loads(ref.read_text()) if ref.exists() else []
    done, failed, to_check = [], [], []
    for e in todo:
        print(f"  {e['id']}: extracting…", flush=True)
        extracted = s05.parse_block_with_claude(block_for(e), str(e["pleno_id"]), int(e.get("ordre") or 0))
        if not extracted:
            failed.append((e["id"], "script 05 returned nothing"))
            continue
        new = anonymise(complete(e, extracted, raw_by_id.get(str(e["id"]))))
        new, why = language_rule(new, translator)
        if why:   # nothing written: 2026-04-30-102 was committed with text_val in castellano
            failed.append((e["id"], why))
            continue
        new, notes = tidy_geography(new, barris_ref)
        notes += [f"may be untranslated: «{p}»" for p in untranslated_starts(new)]
        if notes:
            to_check.append((e["id"], notes))
        P.replace_entry(corrections, FILE, None, new)
        errors = n7_errors(wt, FILE, str(new["id"]))
        if errors:
            P.replace_entry(corrections, FILE, None, e)       # back to the reviewed entry
            failed.append((e["id"], "N7: " + "; ".join(errors)))
            continue
        filled = [f for f in FILLED if _empty(e.get(f)) and not _empty(new.get(f))]
        done.append(e["id"])
        print(f"    filled {', '.join(filled)}"
              + (f" · warnings: {extracted['validation_warnings']}" if extracted.get("validation_warnings") else ""))
        if args.commit:
            subprocess.run(["git", "add", f"data/corrections/{FILE}"], cwd=wt, check=True)
            subprocess.run(["git", "commit", "-q", "-m",
                            f"qa: complete manual intervention {e['id']} (script 05 extraction)\n\n"
                            f"Filled: {', '.join(filled)}. text_original, intervinient and entitat unchanged.\n\n"
                            "Co-Authored-By: complete_manual.py <noreply@laciutatparla.es>"], cwd=wt, check=True)
    for iv_id, why in failed:
        print(f"  ✗ {iv_id}: {why}")
    if to_check:
        print("complete_manual: fixed or worth a look before /apply-approved:")
        for iv_id, notes in to_check:
            for note in notes:
                print(f"  ? {iv_id}: {note}")
    from qa.run_checks import State
    try:
        State(state_dir()).append("runs.jsonl", [{
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "trigger": "complete_manual",
            "model": "claude-haiku-4-5 (script 05)", "calls": len(todo), "completed": done,
            "failed": [{"id": i, "reason": r} for i, r in failed]}])
    except OSError as e:   # the work is done and committed: a log that cannot be written is not a failure
        print(f"complete_manual: could not write runs.jsonl ({e})", file=sys.stderr)
    print(f"complete_manual: {len(done)} completed, {len(failed)} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

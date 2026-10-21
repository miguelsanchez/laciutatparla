#!/usr/bin/env python3
"""Run the per-pleno review agents (arquitectura-agentes.md §3.1, F2.7).

For each pleno it decides which agents have something to review, builds their context in a
temporary directory, runs each with `claude -p`, records tokens and cost in runs.jsonl, and
passes their output through verify_proposals.py. What survives is written in propose.py's input
format; it never touches data/ or GitHub.

  extraction-reviewer     (sonnet)  always, for a pleno with a citizen-intervention section
  entity-curator          (sonnet)  if the pleno brings new entities or N2/N4 candidates
  classification-auditor  (haiku)   if the pleno has interventions

How each agent runs:
  claude -p --bare            no hooks, no CLAUDE.md, no keychain: auth is ANTHROPIC_API_KEY only,
                              read from the environment or the repo's .env. That is what makes it
                              work from launchd, where the login keychain is locked.
  --subscription              instead: claude -p without --bare and with no API key in its
                              environment, so it draws on the Claude subscription you are logged
                              in with. Only for runs you start yourself (the F5 sweep, at night):
                              the subscription's terms allow scripted access only with an API key,
                              so launchd keeps the API (refused with --trigger launchd).
  --allowedTools Read,Grep,Glob, everything else disallowed; no MCP servers; cwd is the temp
  context dir. --json-schema proposal_schema.json · --max-turns 25 · --max-budget-usd · 15 min timeout.

Stops before spending anything: PAUSE in the state dir, or this month's agent tokens in
runs.jsonl already at the cap (300k by default, LCP_QA_TOKEN_CAP; API runs only).

    "$PY" scripts/qa/run_agents.py --pleno 2026-09-29 --dry-run        # plan and prompt sizes, no API
    "$PY" scripts/qa/run_agents.py --pleno 2026-09-29 --output verified.json
    "$PY" scripts/qa/run_agents.py --subscription --pleno 2013-05-31 --output verified.json
    "$PY" scripts/qa/run_agents.py --data-dir "$TMPDIR/bt/data" --pleno 2026-07-23 --no-state --output …

Without --pleno it reviews the plenos that are in interventions_raw.json but not yet in
intervencions.json (ingested, not built). Nothing new → nothing runs, 0 tokens.

A long sweep (F5: every pleno, overnight) takes the plenos from a file and survives a stop:

    "$PY" scripts/qa/run_agents.py --subscription --plenos-file plenos.txt --output sweep/verified.json
    "$PY" scripts/qa/run_agents.py --subscription --plenos-file plenos.txt --output sweep/verified.json --resume

--output is rewritten after every agent run, and `<output>.done` lists each pleno/agent finished,
so --resume skips those and keeps their proposals. An existing --output is never overwritten
without --resume. After MAX_FAILURES failed runs in a row (the subscription's usage limit, an
outage) the sweep stops, exit 3, rather than burn through the list: run it again with --resume.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa import run_checks  # noqa: E402
from qa.model import REGISTRY, REPO_ROOT, Context, load_script, state_dir  # noqa: E402

AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
SCHEMA_PATH = Path(__file__).resolve().parent / "proposal_schema.json"
TAXONOMY_PATH = REPO_ROOT / "scripts" / "lib" / "taxonomy.json"
ORDER = ("extraction-reviewer", "entity-curator", "classification-auditor")
MAX_TURNS = 25
TIMEOUT_S = 15 * 60
BUDGET_USD = {"sonnet": 1.50, "haiku": 0.30}
DEFAULT_TOKEN_CAP = 300_000
MAX_FAILURES = 3
SECTION_CHARS = 100_000     # see cap_sections
SECTIONS_CHARS = 150_000

EXTRACTION_CHECKS = ("E1", "E1b", "E2", "E5", "E6", "E7")
ENTITY_CHECKS = ("N2", "N4")
CLASSIFICATION_CHECKS = ("C1", "C3", "C4", "C5")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ── Agents ───────────────────────────────────────────────────────────────────

def parse_agent(path: Path) -> tuple[dict, str]:
    """Frontmatter (name, model, tools…) and body of a .claude/agents/*.md file."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path}: no frontmatter")
    import yaml
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip() + "\n"


def load_api_key(repo_root: Path = REPO_ROOT) -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env = repo_root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() in ("ANTHROPIC_API_KEY", "ANTHROPIC") and v.strip():
                return v.strip().strip('"').strip("'")
    return None


def tokens_this_month(state: run_checks.State) -> int:
    p = state.path("runs.jsonl")
    if not state.enabled or not p.exists():
        return 0
    month = dt.date.today().strftime("%Y-%m")
    total = 0
    for line in p.read_text().splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("trigger") == "agents" and str(rec.get("ts", "")).startswith(month):
            total += int(rec.get("weighted_tokens", rec.get("tokens")) or 0)
    return total


# ── Context ──────────────────────────────────────────────────────────────────

def new_plenos(ctx: Context) -> list[str]:
    built = {iv.get("pleno_id") for iv in ctx.intervencions}
    return sorted({str(iv.get("pleno_id")) for iv in ctx.interventions_raw} - built)


CROSS_PLENO_CHECKS = {"E2", "N2", "N4"}   # need every pleno (duplicates across plenos, the catalog)


def pleno_context(ctx: Context, pleno: str, tmp: Path) -> Context:
    """The same data, narrowed to one pleno: its acta and its interventions. The per-acta checks
    (E1b, E6, E7…) otherwise read all ~300 actas to report on one."""
    narrow = Context(ctx.data_dir, repo_root=ctx.repo_root)
    texts = tmp / "texts"
    texts.mkdir(parents=True, exist_ok=True)
    src = ctx.texts_dir / f"{pleno}.txt"
    if src.exists() and not (texts / src.name).exists():
        (texts / src.name).symlink_to(src)
    narrow.texts_dir = texts
    narrow.interventions_raw = [iv for iv in ctx.interventions_raw if str(iv.get("pleno_id")) == pleno]
    return narrow


def findings_for(ctx: Context, checks: tuple[str, ...], keep, narrow: Context | None = None) -> list[dict]:
    run_checks.load_checks()
    out = []
    for cid in checks:
        try:
            use = ctx if narrow is None or cid in CROSS_PLENO_CHECKS else narrow
            for f in REGISTRY[cid].fn(use):
                if keep(f):
                    out.append({"check": f.check, "severity": f.severity, "subject": f.subject,
                                "message": f.message, "details": f.details})
        except Exception as e:  # a crashing check must not stop the review
            out.append({"check": cid, "error": f"{type(e).__name__}: {e}"})
    return out


def _about_pleno(pleno: str, ivs: set[str]):
    def keep(f) -> bool:
        parts = f.subject.split("|")
        return (f.subject == pleno or any(p in ivs for p in parts)
                or (f.details or {}).get("pleno_id") == pleno)
    return keep


def existing_corrections(ctx: Context, pleno: str) -> dict:
    """Correction entries that already mention this pleno, so the agent does not propose them twice."""
    out = {}
    for path in sorted(ctx.corrections_dir.glob("*.yml")):
        doc = ctx.corrections(path.name)
        items = doc if isinstance(doc, list) else [x for v in (doc or {}).values() if isinstance(v, list) for x in v]
        hits = [e for e in items if isinstance(e, dict) and pleno in json.dumps(e, ensure_ascii=False, default=str)]
        if hits:
            out[path.name] = hits
    return out


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


def build_contexts(ctx: Context, pleno: str) -> dict[str, dict]:
    """{agent: {"prompt": str, "files": {name: text}}} for the agents with something to review."""
    ivs = [iv for iv in ctx.interventions_raw if str(iv.get("pleno_id")) == pleno]
    iv_ids = {str(iv.get("id")) for iv in ivs}
    acta = ctx.text(pleno) or ""
    keep = _about_pleno(pleno, iv_ids)
    out: dict[str, dict] = {}
    tmp = Path(tempfile.mkdtemp(prefix="lcp-ctx-"))
    try:
        narrow = pleno_context(ctx, pleno, tmp)
        return _build(ctx, narrow, pleno, ivs, acta, keep, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cap_sections(sections: list[str]) -> list[str]:
    """Cut what script 05's splitter returns to SECTION_CHARS each and SECTIONS_CHARS in all.

    On some actas it misses where the citizen block ends and runs to the end of the acta: one
    section of 2018-05-31 is 634k chars for 3 speeches, and 2021-02-25's prompt cost 0.65 $ alone.
    The longest real block is about 90k (2024-09-16-1, 18 speeches); the agent has acta.txt for
    the rest."""
    out, left = [], SECTIONS_CHARS
    for s in sections:
        limit = min(SECTION_CHARS, left)
        if limit <= 0:
            out.append("[… more sections not shown: search acta.txt]")
            break
        out.append(s if len(s) <= limit else
                   s[:limit] + f"\n\n[… section cut at {limit:,} of {len(s):,} chars: the rest is in acta.txt]")
        left -= min(len(s), limit)
    return out


def _build(ctx: Context, narrow: Context, pleno: str, ivs: list[dict], acta: str, keep, out: dict) -> dict:

    sections = load_script("05_parse_interventions.py").split_intervention_sections(acta) if acta else []
    sections = cap_sections(sections)
    variant_map = ctx._json("raw/entity_variant_map.json") or {}
    catalog = {e["id"]: e for e in ctx.entitats}
    compact = [{k: e.get(k) for k in ("id", "nom_cas", "nom_val", "tipus", "num_intervencions", "variants")}
               for e in ctx.entitats]
    if sections:
        fields = ("id", "ordre", "intervinient", "entitat", "tipus_entitat", "entitat_cessio",
                  "idioma_original", "text_original")
        listed = [{**{k: iv.get(k) for k in fields},
                   "entitat_id": variant_map.get((iv.get("entitat") or "").lower().strip())} for iv in ivs]
        out["extraction-reviewer"] = {
            "prompt": (f"# Pleno {pleno}\n\n"
                       f"## Citizen-intervention sections of the acta (cut by script 05; the full acta is in acta.txt)\n\n"
                       + "\n\n=====\n\n".join(sections)
                       + f"\n\n## Extracted interventions ({len(ivs)}), with the catalog entity each one counts for\n\n"
                       + _dump(listed)
                       + "\n\n## Deterministic findings for this pleno\n\n" + _dump(findings_for(ctx, EXTRACTION_CHECKS, keep, narrow))
                       + "\n\n## Corrections that already exist for this pleno\n\n" + _dump(existing_corrections(ctx, pleno))
                       + "\n\nThe entity catalog (id, names, variants: the entity texts already mapped to it) is in catalog.json."),
            "files": {"acta.txt": acta, "catalog.json": _dump(compact)},
        }

    eids = {variant_map.get((iv.get("entitat") or "").lower().strip()) for iv in ivs} - {None}
    seen_elsewhere = {variant_map.get((iv.get("entitat") or "").lower().strip())
                      for iv in ctx.interventions_raw if str(iv.get("pleno_id")) != pleno}
    new_ids = sorted(eids - seen_elsewhere)
    unknown_texts = sorted({iv.get("entitat") for iv in ivs
                            if (iv.get("entitat") or "").lower().strip() not in variant_map})
    ent_findings = findings_for(ctx, ENTITY_CHECKS, lambda f: any(p in eids for p in f.subject.split("|")))
    if new_ids or unknown_texts or ent_findings:
        out["entity-curator"] = {
            "prompt": (f"# Pleno {pleno}\n\n## Entities of this pleno\n\n"
                       + _dump([{**{k: catalog.get(e, {}).get(k) for k in ("id", "nom_cas", "nom_val", "tipus", "variants")},
                                  "new_in_this_pleno": e in new_ids} for e in sorted(eids)])
                       + "\n\n## Entity texts not in the variant map (script 07 would invent an id)\n\n" + _dump(unknown_texts)
                       + "\n\n## Interventions (who speaks for which entity)\n\n"
                       + _dump([{k: iv.get(k) for k in ("id", "intervinient", "entitat", "tipus_entitat")} for iv in ivs])
                       + "\n\n## N2 / N4 candidates involving these entities\n\n" + _dump(ent_findings)
                       + "\n\nThe whole catalog is in catalog.json and the acta in acta.txt."),
            "files": {"catalog.json": _dump(compact), "acta.txt": acta},
        }

    if ivs:
        barris = ctx._json("raw/barris_referencia.json") or []
        # text_original is the acta's own wording, so quotes come from it; the full acta (with its
        # annexes, ~20k lines) only made the auditor search for 18 turns in the first backtest.
        fields = ("id", "entitat", "tipus_entitat", "idioma_original", "text_original", "resum_cas", "resum_val",
                  "temes_v2", "cap_major", "cap_subtopics", "ambit", "zones", "districtes")
        out["classification-auditor"] = {
            "prompt": (f"# Pleno {pleno}\n\n## Interventions to audit ({len(ivs)})\n\n"
                       + _dump([{**{k: iv.get(k) for k in fields},
                                 "text_cas_empty": not (iv.get("text_cas") or "").strip(),
                                 "text_val_empty": not (iv.get("text_val") or "").strip()} for iv in ivs])
                       + "\n\n## Deterministic findings for these interventions\n\n"
                       + _dump(findings_for(ctx, CLASSIFICATION_CHECKS, keep, narrow))
                       + "\n\nThe taxonomy is in taxonomy.json, the barrios and districts in barris.json."),
            "files": {"taxonomy.json": TAXONOMY_PATH.read_text(encoding="utf-8"),
                      "barris.json": _dump([{"barri": b.get("nom"), "districte": b.get("districte_nom")} for b in barris])},
        }
    return out


# ── Running ──────────────────────────────────────────────────────────────────

def claude_command(meta: dict, system_prompt_file: Path, budget: float, subscription: bool = False) -> list[str]:
    auth = ["--strict-mcp-config"] if subscription else ["--bare"]   # --bare never reads the subscription login
    return [
        os.environ.get("LCP_CLAUDE_BIN", "claude"), "-p", *auth,
        "--model", str(meta.get("model", "sonnet")),
        "--system-prompt-file", str(system_prompt_file),
        "--allowedTools=Read,Grep,Glob",
        "--disallowedTools=Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Task",
        "--json-schema", SCHEMA_PATH.read_text(encoding="utf-8"),
        "--output-format", "json",
        "--max-turns", str(min(int(meta.get("max_turns") or MAX_TURNS), MAX_TURNS)),
        "--max-budget-usd", f"{budget:.2f}",
        "--no-session-persistence",
    ]


# Cache reads cost a tenth of an input token: counting them in full made one 18-turn Haiku run
# (0.014 $) look like 475k tokens and would have spent the monthly cap on a single pleno.
CACHE_READ_WEIGHT = 0.1


def usage_of(out: dict) -> dict:
    u = out.get("usage") or {}
    rec = {"input_tokens": int(u.get("input_tokens") or 0),
           "cache_creation_input_tokens": int(u.get("cache_creation_input_tokens") or 0),
           "cache_read_input_tokens": int(u.get("cache_read_input_tokens") or 0),
           "output_tokens": int(u.get("output_tokens") or 0)}
    rec["tokens"] = sum(rec.values())
    rec["weighted_tokens"] = round(rec["tokens"] - (1 - CACHE_READ_WEIGHT) * rec["cache_read_input_tokens"])
    rec["cost_usd"] = round(float(out.get("total_cost_usd") or 0.0), 4)
    rec["num_turns"] = out.get("num_turns")
    return rec


def structured(out: dict) -> dict | None:
    data = out.get("structured_output")
    if isinstance(data, dict):
        return data
    text = out.get("result")
    if isinstance(text, str):
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


API_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC")   # any of these would bill the API


def run_agent(name: str, context: dict, api_key: str | None) -> tuple[dict | None, dict]:
    """With api_key None the run uses the logged-in subscription (--subscription)."""
    meta, body = parse_agent(AGENTS_DIR / f"{name}.md")
    model = str(meta.get("model", "sonnet"))
    work = Path(tempfile.mkdtemp(prefix=f"lcp-{name}-"))
    try:
        for fname, text in context["files"].items():
            (work / fname).write_text(text, encoding="utf-8")
        (work / ".system-prompt.md").write_text(body, encoding="utf-8")
        cmd = claude_command(meta, work / ".system-prompt.md", BUDGET_USD.get(model, 1.0), subscription=api_key is None)
        if api_key is None:
            env = {k: v for k, v in os.environ.items() if k not in API_ENV}
        else:
            env = {**os.environ, "ANTHROPIC_API_KEY": api_key}
        t0 = time.monotonic()
        try:
            p = subprocess.run(cmd, input=context["prompt"], cwd=work, env=env, capture_output=True,
                               text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return None, {"model": model, "exit": "timeout", "duration_s": round(time.monotonic() - t0, 1), "tokens": 0}
        rec = {"model": model, "auth": "api" if api_key else "subscription",
               "duration_s": round(time.monotonic() - t0, 1)}
        try:
            out = json.loads(p.stdout)
        except ValueError:
            return None, {**rec, "exit": p.returncode or "bad-json", "tokens": 0, "stderr": p.stderr[-500:]}
        rec.update(usage_of(out))
        rec["exit"] = 0 if p.returncode == 0 and not out.get("is_error") else (out.get("subtype") or p.returncode)
        return structured(out), rec
    finally:
        shutil.rmtree(work, ignore_errors=True)


def to_proposals(agent: str, pleno: str, data: dict | None) -> tuple[list[dict], list[dict]]:
    """Agent output → propose.py input. Items whose entry_json does not parse are dropped here."""
    good, bad = [], []
    for item in (data or {}).get("proposals") or []:
        try:
            entry = json.loads(item.get("entry_json") or "")
            if not isinstance(entry, dict):
                raise ValueError("not an object")
        except ValueError as e:
            bad.append({"subject": item.get("subject"), "check": item.get("check"),
                        "reason": f"entry_json: {e}"})
            continue
        canon = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        fp = item["check"] + "-" + hashlib.sha1(f"{agent}|{item['subject']}|{item['file']}|{canon}".encode()).hexdigest()[:10]
        good.append({
            "fp": fp, "check": item["check"], "severity": item["severity"], "subject": item["subject"],
            "title": item["title"], "message": item["message"], "agent": agent,
            "evidence": {"file": f"data/raw/texts/{item.get('evidence_pleno') or pleno}.txt", "quote": item.get("quote")},
            "file": item["file"], "section": item.get("section"), "entry": entry, "op": item.get("op") or "append",
        })
    return good, bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pleno", action="append", help="pleno to review (repeatable); default: ingested, not built")
    ap.add_argument("--plenos-file", type=Path, help="plenos to review, one id per line (# comments)")
    ap.add_argument("--resume", action="store_true", help="skip the pleno/agent runs listed in <output>.done")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--only", help="comma-separated agent names")
    ap.add_argument("--output", type=Path, help="verified proposals, propose.py --input format")
    ap.add_argument("--dry-run", action="store_true", help="show the plan and prompt sizes; no API call")
    ap.add_argument("--no-state", action="store_true", help="no runs.jsonl, no monthly cap (backtests)")
    ap.add_argument("--trigger", default="manual", help="recorded in runs.jsonl")
    ap.add_argument("--subscription", action="store_true",
                    help="use the logged-in Claude subscription, not the API key (runs you start yourself)")
    args = ap.parse_args(argv)
    if args.subscription and args.trigger == "launchd":
        print("run_agents: --subscription is for runs you start yourself; launchd uses the API key", file=sys.stderr)
        return 2

    state = run_checks.State(state_dir(), enabled=not args.no_state)
    if state.paused:
        print(f"PAUSE present in {state.root}: no agent runs.")
        return 0
    journal = args.output.with_name(args.output.name + ".done") if args.output else None
    if args.resume and not args.output:
        print("run_agents: --resume needs --output", file=sys.stderr)
        return 2
    if args.output and args.output.exists() and not args.resume and not args.dry_run:
        print(f"run_agents: {args.output} exists: pass --resume to continue it, or another --output",
              file=sys.stderr)
        return 2
    ctx = Context(args.data_dir)
    listed = list(args.pleno or [])
    if args.plenos_file:
        listed += [l.split("#")[0].strip() for l in args.plenos_file.read_text().splitlines()]
        listed = [p for p in listed if p]
    plenos = list(dict.fromkeys(listed)) or new_plenos(ctx)
    if not plenos:
        print("run_agents: no new pleno to review (0 tokens).")
        return 0
    only = set(args.only.split(",")) if args.only else set(ORDER)
    cap = int(os.environ.get("LCP_QA_TOKEN_CAP") or DEFAULT_TOKEN_CAP)

    plan = []
    for pleno in plenos:
        for name, c in build_contexts(ctx, pleno).items():
            if name in only:
                plan.append((pleno, name, c))
    plan.sort(key=lambda t: (t[0], ORDER.index(t[1])))
    done: set[str] = set()
    accepted_all: list[dict] = []
    if args.resume:
        done = set(journal.read_text().splitlines()) if journal.exists() else set()
        accepted_all = json.loads(args.output.read_text()) if args.output.exists() else []
        before = len(plan)
        plan = [t for t in plan if f"{t[0]} {t[1]}" not in done]
        print(f"run_agents: resuming, {before - len(plan)} runs already done, "
              f"{len(accepted_all)} proposals kept")
    print(f"run_agents: {len(plan)} agent runs for {', '.join(dict.fromkeys(t[0] for t in plan))}")
    for pleno, name, c in plan:
        size = len(c["prompt"])
        print(f"  {pleno}  {name:<23} prompt {size:>7,} chars (~{size // 3:,} tokens)  files: {', '.join(c['files'])}")
    if args.dry_run or not plan:
        print("(dry run: no API call)" if args.dry_run else "nothing to run (0 tokens).")
        return 0

    api_key = None if args.subscription else load_api_key()
    if not api_key and not args.subscription:
        print("run_agents: no ANTHROPIC_API_KEY (environment or .env): not running", file=sys.stderr)
        return 2

    from qa.verify_proposals import verify_all
    used = tokens_this_month(state)
    total_tokens, total_cost, failures, stopped = 0, 0.0, 0, False
    for pleno, name, c in plan:
        estimate = len(c["prompt"]) // 3
        if state.enabled and not args.subscription and used + estimate > cap:
            print(f"  {pleno} {name}: monthly cap reached ({used:,} + ~{estimate:,} > {cap:,} tokens): skipped")
            state.append("runs.jsonl", [{"ts": now(), "trigger": "agents", "agent": name, "pleno": pleno,
                                         "exit": "cap", "tokens": 0}])
            continue
        print(f"  {pleno} {name}: running…", flush=True)
        data, rec = run_agent(name, c, api_key)
        # Keep what was paid for before anything else can fail (a verifier crash once lost a run)
        raw_dir = state.root / "agents" if state.enabled else (args.output.parent if args.output else None)
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw = raw_dir / f"{pleno}.{name}.{now().replace(':', '')}.json"
            raw.write_text(json.dumps({"usage": rec, "output": data}, ensure_ascii=False, indent=2))
            rec["raw"] = str(raw)
        proposals, unparsable = to_proposals(name, pleno, data)
        try:
            accepted, rejected = verify_all(proposals, args.data_dir) if proposals else ([], [])
        except Exception as e:  # never lose the run record: drop everything, say why
            accepted = []
            rejected = [{"subject": p.get("subject"), "check": p.get("check"),
                         "reason": f"verifier crashed: {type(e).__name__}: {e}"} for p in proposals]
        rejected += unparsable
        accepted_all += accepted
        if not args.subscription:
            used += rec.get("weighted_tokens", rec.get("tokens", 0))
        total_tokens += rec.get("tokens", 0)
        total_cost += rec.get("cost_usd", 0.0)
        n = len(proposals) + len(unparsable)
        print(f"    exit {rec.get('exit')} · {rec.get('tokens', 0):,} tokens "
              f"({rec.get('weighted_tokens', 0):,} counting cache reads at 10 %) · {rec.get('cost_usd', 0):.3f} $ · "
              f"{rec.get('num_turns')} turns · {n} proposals, {len(accepted)} verified, {len(rejected)} dropped")
        for r in rejected:
            print(f"      - {r.get('subject')}: {r['reason']}")
        state.append("runs.jsonl", [{
            "ts": now(), "trigger": "agents", "via": args.trigger, "agent": name, "pleno": pleno, **rec,
            "proposals": n, "accepted": len(accepted), "dropped": len(rejected),
            "drop_rate": round(len(rejected) / n, 3) if n else 0.0, "reasons": rejected,
            "notes": (data or {}).get("notes"),
        }])
        if rec.get("exit") == 0:
            failures = 0
            if args.output:  # after every run: a stop in the middle of the night keeps what is done
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(accepted_all, ensure_ascii=False, indent=2))
                with journal.open("a") as fh:
                    fh.write(f"{pleno} {name}\n")
        else:
            failures += 1
            if failures >= MAX_FAILURES:
                print(f"run_agents: {failures} failed runs in a row (usage limit? outage?): stopping. "
                      f"Run again with --resume.")
                stopped = True
                break
    print(f"run_agents: {len(accepted_all)} verified proposals · {total_tokens:,} tokens · {total_cost:.2f} $")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(accepted_all, ensure_ascii=False, indent=2))
        print(f"  → {args.output}")
    return 3 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())

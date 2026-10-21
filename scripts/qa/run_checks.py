#!/usr/bin/env python3
"""QA sentinel: run the deterministic checks and report what is new.

Design: meta/docs/arquitectura-agentes.md §3 (layer 0), §5 (state) and §7 (catalogue).

Reads data/ (or --data-dir), web/ and data/corrections/. Never writes to the repo:
run state lives in $LCP_QA_STATE (default ~/.lcp-qa/):

  findings.jsonl   append-only history of state changes (open / resolved) per fingerprint
  runs.jsonl       one line per run: trigger, checks, counts, duration, exit
  last_run.json    the findings of the last run, with `new` marking the delta
  memory.json      small values checks compare across runs (e.g. index size)
  lock             taken for the whole run; a second run exits instead of overlapping
  PAUSE            if it exists, nothing runs (kill switch)

Decisions live in git, meta/qa/: baseline.json (accepted findings) and suppressions.yml.

    "$PY" scripts/qa/run_checks.py                 # all checks
    "$PY" scripts/qa/run_checks.py --list
    "$PY" scripts/qa/run_checks.py --only E1,S7 --offline --json
    "$PY" scripts/qa/run_checks.py --data-dir "$TMPDIR/fixture" --no-state

Exit: 0 ran (with or without findings) · 1 --strict and new findings · 3 a check crashed
      · 75 another run holds the lock
"""

from __future__ import annotations

import argparse
import fcntl
import importlib
import json
import pkgutil
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ → `qa`, `lib`

from qa.model import REGISTRY, REPO_ROOT, SEVERITIES, Context, Finding, state_dir  # noqa: E402

BASELINE_PATH = REPO_ROOT / "meta" / "qa" / "baseline.json"
SUPPRESSIONS_PATH = REPO_ROOT / "meta" / "qa" / "suppressions.yml"
EXIT_LOCKED = 75


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_checks() -> None:
    import qa.checks
    for m in pkgutil.iter_modules(qa.checks.__path__):
        importlib.import_module(f"qa.checks.{m.name}")


# ── Decisions (git) ───────────────────────────────────────────────────────────

def load_baseline(path: Path | None = None) -> dict[str, dict]:
    path = path or BASELINE_PATH
    if not path.exists():
        return {}
    return {b["fp"]: b for b in json.loads(path.read_text()).get("findings", [])}


def load_suppressions(path: Path | None = None) -> list[dict]:
    path = path or SUPPRESSIONS_PATH
    if not path.exists():
        return []
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return data.get("suppressions", []) if isinstance(data, dict) else data


def is_suppressed(f: Finding, suppressions: list[dict], today: date) -> bool:
    for s in suppressions:
        if s.get("fp") != f.fp:
            continue
        mode = str(s.get("mode", "forever"))
        if mode == "forever":
            return True
        if mode == "until_changed":
            # A check that computes no subject hash cannot tell a change: keep it suppressed
            return not f.subject_hash or not s.get("subject_hash") or s["subject_hash"] == f.subject_hash
        if mode.startswith("until:"):
            return today <= date.fromisoformat(mode[6:].strip())
    return False


# ── Run state (outside git) ───────────────────────────────────────────────────

class State:
    def __init__(self, root: Path, enabled: bool = True) -> None:
        self.root = root
        self.enabled = enabled
        self._lock_fh = None

    def path(self, name: str) -> Path:
        return self.root / name

    @property
    def paused(self) -> bool:
        return self.path("PAUSE").exists()

    def acquire(self) -> bool:
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_fh = open(self.path("lock"), "a+")
        try:
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock_fh.close()
            self._lock_fh = None
            return False
        return True

    def release(self) -> None:
        if self._lock_fh:
            fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
            self._lock_fh.close()
            self._lock_fh = None

    def open_findings(self) -> dict[str, dict]:
        """Latest record per fp whose status is still open."""
        p = self.path("findings.jsonl")
        latest: dict[str, dict] = {}
        if self.enabled and p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    latest[rec["fp"]] = rec
        return {fp: r for fp, r in latest.items() if r.get("status") == "open"}

    def append(self, name: str, records: list[dict]) -> None:
        if not self.enabled or not records:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path(name), "a") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def write_json(self, name: str, obj) -> None:
        if not self.enabled:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path(name + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        tmp.replace(self.path(name))

    def read_json(self, name: str, default):
        p = self.path(name)
        if self.enabled and p.exists():
            return json.loads(p.read_text())
        return default


# ── Running ──────────────────────────────────────────────────────────────────

def select(only: str | None, fast: bool, offline: bool) -> list:
    checks = sorted(REGISTRY.values(), key=lambda c: c.id)
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        unknown = wanted - set(REGISTRY)
        if unknown:
            raise SystemExit(f"unknown check(s): {', '.join(sorted(unknown))}")
        checks = [c for c in checks if c.id in wanted]
    if fast:
        checks = [c for c in checks if c.fast]
    if offline:
        checks = [c for c in checks if not c.network]
    return checks


def run(checks, ctx: Context) -> tuple[list[Finding], list[str]]:
    findings, crashed = [], []
    for c in checks:
        try:
            for f in c.fn(ctx) or []:
                f.family = f.family or c.family
                findings.append(f)
        except Exception as e:  # noqa: BLE001 — one broken check must not hide the others
            crashed.append(c.id)
            findings.append(Finding(
                check=c.id, severity="P1", subject="crash", family=c.family,
                message=f"check {c.id} crashed: {type(e).__name__}: {e}",
                details={"traceback": traceback.format_exc(limit=4)},
            ))
    return findings, crashed


def classify(findings, checks, state: State, baseline, suppressions, ts: str):
    """Split into new / known / baseline / suppressed and build the history records."""
    today = date.today()
    previously_open = state.open_findings()
    ran = {c.id for c in checks}
    out = {"new": [], "known": [], "baseline": [], "suppressed": []}
    history = []
    seen = set()
    for f in findings:
        if f.fp in seen:
            continue
        seen.add(f.fp)
        if f.fp in baseline:
            out["baseline"].append(f)
        elif is_suppressed(f, suppressions, today):
            out["suppressed"].append(f)
        elif f.fp in previously_open:
            out["known"].append(f)
        else:
            out["new"].append(f)
            history.append({"fp": f.fp, "ref": f.ref, "check": f.check, "severity": f.severity,
                            "subject": f.subject, "first_seen": ts, "last_seen": ts,
                            "status": "open", "pr": None})
    for fp, rec in previously_open.items():
        if rec["check"] in ran and fp not in seen:
            history.append({**rec, "last_seen": ts, "status": "resolved"})
    # A finding that moved to baseline or got suppressed is no longer open either
    for f in out["baseline"] + out["suppressed"]:
        if f.fp in previously_open:
            history.append({**previously_open[f.fp], "last_seen": ts,
                            "status": "dismissed"})
    return out, history


def add_to_baseline(findings: list[Finding], reason: str, path: Path | None = None) -> int:
    """Append findings to meta/qa/baseline.json (accepted for now, §5). Returns how many."""
    path = path or BASELINE_PATH
    doc = json.loads(path.read_text()) if path.exists() else {"findings": []}
    have = {b["fp"] for b in doc.get("findings", [])}
    today = date.today().isoformat()
    added = [{"fp": f.fp, "ref": f.ref, "check": f.check, "severity": f.severity,
              "reason": reason, "date": today} for f in findings if f.fp not in have]
    doc.setdefault("findings", []).extend(added)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return len(added)


def print_report(groups: dict, checks, crashed: list[str], duration_s: float | None = None) -> None:
    def line(f: Finding, mark: str) -> str:
        return f"  {mark} {f.severity} {f.check:<4} {f.subject:<28} {f.message}"

    total = sum(len(v) for v in groups.values())
    took = f" · {duration_s:.1f} s" if duration_s is not None else ""
    print(f"run_checks: {len(checks)} checks · {total} findings "
          f"({len(groups['new'])} new, {len(groups['known'])} known, "
          f"{len(groups['baseline'])} baseline, {len(groups['suppressed'])} suppressed){took}")
    order = {s: i for i, s in enumerate(SEVERITIES)}
    for name, mark in (("new", "+"), ("known", "·")):
        items = sorted(groups[name], key=lambda f: (order[f.severity], f.check, f.subject))
        if items:
            print(f"\n{name.upper()}")
            for f in items:
                print(line(f, mark))
    if crashed:
        print(f"\nCRASHED: {', '.join(crashed)}")
    if not groups["new"]:
        print("\n0 hallazgos nuevos")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="list the registered checks and exit")
    ap.add_argument("--only", help="comma-separated check ids")
    ap.add_argument("--fast", action="store_true", help="only checks marked fast (pre-commit)")
    ap.add_argument("--offline", action="store_true", help="skip checks that need the network")
    ap.add_argument("--json", action="store_true", help="print the findings as JSON")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data",
                    help="data directory to check (default: $LCP_ROOT/data)")
    ap.add_argument("--no-state", action="store_true",
                    help="read and write no run state (backtests, fixtures)")
    ap.add_argument("--no-lock", action="store_true",
                    help="the caller already holds the lock (daily.sh)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if there are new findings")
    ap.add_argument("--trigger", default="manual", help="recorded in runs.jsonl (manual, launchd…)")
    ap.add_argument("--baseline-add", action="store_true",
                    help="append this run's new findings to meta/qa/baseline.json (needs --only and --reason)")
    ap.add_argument("--reason", help="why the findings are accepted for now (with --baseline-add)")
    args = ap.parse_args(argv)
    if args.baseline_add and not (args.only and args.reason):
        ap.error("--baseline-add needs --only (never the whole run at once) and --reason")

    load_checks()
    if args.list:
        for c in sorted(REGISTRY.values(), key=lambda c: c.id):
            flags = ",".join(f for f, on in (("network", c.network), ("fast", c.fast)) if on)
            print(f"{c.id:<5} {c.family:<15} {c.title}" + (f"  [{flags}]" if flags else ""))
        return 0

    state = State(state_dir(), enabled=not args.no_state)
    if state.paused:
        print(f"PAUSE present in {state.root}: nothing runs.")
        return 0
    if state.enabled and not args.no_lock and not state.acquire():
        print(f"another run holds {state.path('lock')}; exiting.", file=sys.stderr)
        state.append("runs.jsonl", [{"ts": now(), "trigger": args.trigger, "exit": "locked"}])
        return EXIT_LOCKED

    t0 = time.monotonic()
    ts = now()
    try:
        checks = select(args.only, args.fast, args.offline)
        memory = state.read_json("memory.json", {})
        ctx = Context(args.data_dir, offline=args.offline, memory=memory)
        findings, crashed = run(checks, ctx)
        groups, history = classify(findings, checks, state, load_baseline(),
                                   load_suppressions(), ts)
        new_fps = {f.fp for f in groups["new"]}
        exit_code = 3 if crashed else (1 if args.strict and new_fps else 0)

        state.append("findings.jsonl", history)
        state.write_json("memory.json", ctx.memory)
        all_findings = [f for g in groups.values() for f in g]
        state.write_json("last_run.json", {
            "ts": ts, "trigger": args.trigger, "data_dir": str(args.data_dir),
            "checks": [c.id for c in checks],
            "findings": [{**f.to_dict(), "new": f.fp in new_fps,
                          "status": next(k for k, g in groups.items() if f in g)}
                         for f in all_findings],
        })
        state.append("runs.jsonl", [{
            "ts": ts, "trigger": args.trigger, "checks_run": [c.id for c in checks],
            "findings_total": len(all_findings), "findings_new": len(new_fps),
            "new_by_severity": {s: sum(f.severity == s for f in groups["new"]) for s in SEVERITIES},
            "crashed": crashed, "agent": None, "model": None,
            "input_tokens": 0, "output_tokens": 0,
            "duration_s": round(time.monotonic() - t0, 2), "exit": exit_code,
        }])

        if args.json:
            json.dump({"checks": [c.id for c in checks],
                       **{k: [f.to_dict() for f in v] for k, v in groups.items()}},
                      sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            print_report(groups, checks, crashed, time.monotonic() - t0)
        if args.baseline_add:
            n = add_to_baseline(groups["new"] + groups["known"], args.reason)
            where = BASELINE_PATH
            if where.is_relative_to(REPO_ROOT):
                where = where.relative_to(REPO_ROOT)
            print(f"\nbaseline: {n} findings added to {where}")
            return 3 if crashed else 0
        return exit_code
    finally:
        state.release()


if __name__ == "__main__":
    sys.exit(main())

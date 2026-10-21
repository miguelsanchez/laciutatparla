#!/usr/bin/env python3
"""QA status at a glance, for /qa-status (arquitectura-agentes.md F1.6). Read-only.

  - last sentinel run, open findings by check and severity, baseline size
  - the open qa-data PR, its live and rejected proposals, the overflow queue
  - rejection rate per check (merged proposals vs rejects), time from PR to merge
  - tokens used this month (runs.jsonl)

    "$PY" scripts/qa/status.py           # markdown tables
    "$PY" scripts/qa/status.py --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from qa.model import REPO_ROOT, state_dir  # noqa: E402


def _json_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _gh(args: list[str]):
    try:
        r = subprocess.run(["gh", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def collect() -> dict:
    state = state_dir()
    last = json.loads((state / "last_run.json").read_text()) if (state / "last_run.json").exists() else {}
    findings = last.get("findings", [])
    open_findings = [f for f in findings if f.get("status") in ("new", "known")]
    baseline = json.loads((REPO_ROOT / "meta/qa/baseline.json").read_text()).get("findings", [])
    sups = yaml.safe_load((REPO_ROOT / "meta/qa/suppressions.yml").read_text()) or []

    pr = (_gh(["pr", "list", "--label", "qa-data", "--state", "open", "--json", "number,url,headRefName"]) or [None])
    pr = pr[0] if pr else None
    merged = _gh(["pr", "list", "--label", "qa-data", "--state", "merged", "--limit", "50",
                  "--json", "number,createdAt,mergedAt"]) or []
    hours = [(dt.datetime.fromisoformat(m["mergedAt"].replace("Z", "+00:00"))
              - dt.datetime.fromisoformat(m["createdAt"].replace("Z", "+00:00"))).total_seconds() / 3600
             for m in merged if m.get("mergedAt")]

    log = subprocess.run(["git", "log", "origin/main", "--format=%B"], cwd=REPO_ROOT,
                         capture_output=True, text=True).stdout
    merged_props = Counter(m.group(1).split("-")[0] for m in re.finditer(r"^QA-Finding: (\S+)", log, re.M))
    rejected = Counter(s.get("check") or str(s.get("fp", "")).split("-")[0] for s in sups if isinstance(s, dict))
    checks = sorted(set(merged_props) | set(rejected))
    reject_rate = {c: {"merged": merged_props[c], "rejected": rejected[c],
                       "rate": round(rejected[c] / (merged_props[c] + rejected[c]), 2)} for c in checks}

    month = dt.date.today().strftime("%Y-%m")
    runs = _json_lines(state / "runs.jsonl")
    tokens = sum((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
                 for r in runs if str(r.get("ts", "")).startswith(month))
    return {
        "last_run": {k: last.get(k) for k in ("ts", "trigger")} | {"checks": len(last.get("checks", []))},
        "open_by_check": dict(Counter(f"{f['check']} {f['severity']}" for f in open_findings)),
        "new": sum(1 for f in findings if f.get("new")),
        "baseline": len(baseline),
        "suppressed": len(sups),
        "pr": pr,
        "queue": len(_json_lines(state / "queue.jsonl")),
        "reject_rate": reject_rate,
        "merge_hours_median": round(statistics.median(hours), 1) if hours else None,
        "merged_prs": len(hours),
        "tokens_month": tokens,
        "runs_month": sum(1 for r in runs if str(r.get("ts", "")).startswith(month)),
    }


def render(s: dict) -> str:
    lr = s["last_run"]
    out = ["## QA status", "",
           "| | |", "|---|---|",
           f"| Last run | {lr.get('ts') or 'never (no ~/.lcp-qa/last_run.json here)'} · {lr.get('trigger') or ''} · {lr['checks']} checks |",
           f"| New findings in last run | {s['new']} |",
           f"| Accepted (baseline) / rejected (suppressions) | {s['baseline']} / {s['suppressed']} |",
           f"| Open qa-data PR | {('#%s %s' % (s['pr']['number'], s['pr']['headRefName'])) if s['pr'] else 'none'} |",
           f"| Proposals waiting in the queue | {s['queue']} |",
           f"| Median time PR → merge | {s['merge_hours_median'] if s['merge_hours_median'] is not None else '—'} h ({s['merged_prs']} merged) |",
           f"| Runs / tokens this month | {s['runs_month']} / {s['tokens_month']:,} |", ""]
    if s["open_by_check"]:
        out += ["### Open findings", "| Check · severity | Count |", "|---|---|"]
        out += [f"| {k} | {v} |" for k, v in sorted(s["open_by_check"].items())]
        out.append("")
    if s["reject_rate"]:
        out += ["### Rejection rate by check (review the check above 20 %)", "| Check | Merged | Rejected | Rate |",
                "|---|---|---|---|"]
        out += [f"| {c} | {v['merged']} | {v['rejected']} | {v['rate']:.0%}{' ⚠️' if v['rate'] > 0.2 else ''} |"
                for c, v in s["reject_rate"].items()]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    s = collect()
    print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())

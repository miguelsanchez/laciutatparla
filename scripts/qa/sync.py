#!/usr/bin/env python3
"""Process the rejects of the open qa-data PR, on its branch (arquitectura-agentes.md §6.3, F1.4).

A proposal is rejected when:
  - a PR comment has a line `reject <fingerprint> [reason]` (one per line, any number), or
  - its entry was deleted by hand from data/corrections/*.yml in the PR.

For each one it removes the entry from the YAML (if still there), marks it rejected in
meta/qa/proposals.json, adds it to meta/qa/suppressions.yml (`until_changed`, with your reason)
so the sentinel never proposes it again while the subject stays the same, records it as
dismissed in $LCP_QA_STATE/findings.jsonl, and commits on the PR branch. Idempotent.

    "$PY" scripts/qa/sync.py                    # the open qa-data PR, in the QA worktree
    "$PY" scripts/qa/sync.py --pr 57 --no-push
    "$PY" scripts/qa/sync.py --here --comments-json recorded.json --no-push   # tests
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa import proposals as P  # noqa: E402
from qa.model import state_dir  # noqa: E402

REJECT_LINE = re.compile(r"^\s*reject\s+([A-Za-z0-9]+-[A-Za-z0-9]{6,})\b[ \t]*(.*)$", re.I | re.M)
SUPPRESSIONS = "meta/qa/suppressions.yml"


def parse_rejects(comments: list[dict]) -> dict[str, str]:
    """fp → reason, from PR comments (the latest reason wins)."""
    out: dict[str, str] = {}
    for c in sorted(comments, key=lambda c: c.get("created_at") or ""):
        who = (c.get("user") or {}).get("login") or "?"
        for m in REJECT_LINE.finditer(c.get("body") or ""):
            reason = m.group(2).strip() or "rejected in the PR"
            out[m.group(1)] = f"{reason} (@{who})"
    return out


def append_suppression(wt: Path, entry: dict) -> None:
    path = wt / SUPPRESSIONS
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    kept = [l for l in text.splitlines(keepends=True) if l.strip() != "[]"]
    head = "".join(kept).rstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((head + "\n" if head else "") + P.render_entry(entry), encoding="utf-8")


def process(wt: Path, doc: dict, comments: list[dict]) -> list[dict]:
    """Apply rejects to the worktree files; return the proposals newly rejected."""
    corrections = wt / "data" / "corrections"
    asked = parse_rejects(comments)
    known = {p["fp"] for p in doc["proposals"]}
    for fp in asked:
        if fp not in known:
            print(f"  warning: reject {fp}: no such proposal in this PR")
    done = []
    for p in doc["proposals"]:
        if p["status"] != "proposed":
            continue
        reason = asked.get(p["fp"])
        if reason is None and not P.applied(corrections, p, doc):
            reason = "removed from the diff by hand"
        if reason is None:
            continue
        if P.applied(corrections, p):
            if not P.undo(corrections, p):
                print(f"  warning: {p['fp']}: entry edited in the PR, remove it by hand")
                continue
        p["status"], p["reject_reason"] = "rejected", reason
        append_suppression(wt, {"fp": p["fp"], "check": p["check"], "reason": reason, "date": P.today(),
                                "mode": "until_changed", "subject_hash": P.subject_hash(p)})
        done.append(p)
        print(f"  - rejected {p['fp']}: {reason}")
    if done:
        P.save(wt, doc)
    return done


def record_dismissed(done: list[dict]) -> None:
    state = state_dir()
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "findings.jsonl", "a") as fh:
        for p in done:
            fh.write(json.dumps({"fp": p["fp"], "check": p["check"], "severity": p["severity"],
                                 "subject": p["subject"], "status": "dismissed", "last_seen": P.today(),
                                 "reason": p["reject_reason"]}, ensure_ascii=False) + "\n")


def fetch_comments(wt: Path, pr: int) -> list[dict]:
    out = P.run(["gh", "api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{pr}/comments"], cwd=wt)
    # --paginate concatenates JSON arrays: "][" between pages
    return json.loads("[" + out.strip()[1:-1].replace("][", ",") + "]") if out.strip() else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int, help="PR number (default: the open qa-data PR)")
    ap.add_argument("--worktree", type=Path, default=None)
    ap.add_argument("--here", action="store_true", help="use the current checkout as is (no fetch/switch)")
    ap.add_argument("--comments-json", type=Path, help="recorded `gh api …/comments` output instead of gh")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args(argv)

    from qa.propose import checkout_branch, default_worktree
    wt = Path.cwd() if args.here else (args.worktree or default_worktree()).resolve()
    pr = None
    if not args.here:
        P.run(["git", "fetch", "-q", "origin"], cwd=wt)
        pr = {"number": args.pr} if args.pr else P.open_data_pr(wt)
        if not pr:
            print("no open qa-data PR: nothing to sync")
            return 0
        head = P.run(["gh", "pr", "view", str(pr["number"]), "--json", "headRefName,url",
                      "--jq", ".headRefName"], cwd=wt)
        checkout_branch(wt, head)
    doc = P.load(wt)
    comments = (json.loads(args.comments_json.read_text()) if args.comments_json
                else fetch_comments(wt, pr["number"]) if pr else [])
    done = process(wt, doc, comments)
    if not done:
        print("no new rejects")
        return 0
    record_dismissed(done)
    files = sorted({f"data/corrections/{p['file']}" for p in done} | {SUPPRESSIONS, P.PROPOSALS_FILE})
    P.run(["git", "add", *files], cwd=wt)
    P.run(["git", "commit", "-q", "-m", "qa: reject " + ", ".join(p["fp"] for p in done) + "\n\n"
           + "\n".join(f"- {p['fp']}: {p['reject_reason']}" for p in done)
           + "\n\nCo-Authored-By: sync.py <noreply@laciutatparla.es>"], cwd=wt)
    if not args.no_push and pr:
        P.run(["git", "push", "-q"], cwd=wt)
        P.update_pr_body(wt, pr["number"], doc)
    print(f"{len(done)} reject(s) committed{'' if args.no_push else ' and pushed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

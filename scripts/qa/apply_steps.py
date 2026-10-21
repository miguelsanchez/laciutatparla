#!/usr/bin/env python3
"""Steps of /apply-approved that need more than shell (arquitectura-agentes.md §6.3 step 4).

Run by scripts/qa/apply.sh inside the QA worktree, on the branch of the qa-data PR:

  check PR        refuse unless PR is open, labelled qa-data, from a qa/* or ingest/* branch
  rebase          if the branch does not contain origin/main: rebuild it on origin/main carrying
                  only source changes (the proposals' YAML blocks, or the branch's own edits to
                  data/corrections when it has no proposals; the branch's suppressions and, for
                  ingest/*, data/raw). Derived JSON is never merged by hand: it is regenerated.
  preview         what the live proposals will change, field by field where possible
  bold-count      number of published texts with ** in interventions_raw.json (C1b: must not drop)
  prune-baseline  after applying, drop baseline entries the applied proposals fixed (shrink only)
  summary PR      diff of the public data against origin/main, written into the PR body
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from qa import proposals as P  # noqa: E402

SOURCE_RAW = "data/raw/"
CORRECTIONS = "data/corrections"
SUPPRESSIONS = "meta/qa/suppressions.yml"
DIFF_FIELDS = ("entitat", "entitat_id", "entitat_cessio", "intervinient", "temes_v2", "ambit", "zones",
               "districtes", "cap_major", "cap_subtopics", "resum_cas", "resum_val", "text_cas", "text_val",
               "idioma_original", "fecha", "mandat_id")


def git(*args: str, cwd: Path) -> str:
    return P.run(["git", *args], cwd=cwd)


def check_pr(wt: Path, number: int) -> str:
    info = json.loads(P.run(["gh", "pr", "view", str(number), "--json",
                             "state,headRefName,labels,baseRefName"], cwd=wt))
    head = info["headRefName"]
    labels = {l["name"] for l in info["labels"]}
    problems = []
    if info["state"] != "OPEN":
        problems.append(f"PR #{number} is {info['state'].lower()}")
    if "qa-data" not in labels:
        problems.append(f"PR #{number} has no qa-data label")
    if head == "main" or not head.startswith(("qa/", "ingest/")):
        problems.append(f"branch {head!r} is not qa/* or ingest/*")
    if info["baseRefName"] != "main":
        problems.append(f"PR #{number} does not target main")
    if problems:
        raise SystemExit("refusing: " + "; ".join(problems))
    return head


def rebase(wt: Path) -> bool:
    """Rebuild the branch on origin/main with its source changes only. True if it changed."""
    if _is_ancestor(wt):
        print("branch already contains origin/main: no rebase needed")
        return False
    branch = git("branch", "--show-current", cwd=wt)
    old = git("rev-parse", "HEAD", cwd=wt)
    base = git("merge-base", "origin/main", "HEAD", cwd=wt)
    doc = P.load(wt)
    branch_sup = _yaml_list(git("show", f"{old}:{SUPPRESSIONS}", cwd=wt))
    base_sup_fps = {s["fp"] for s in _yaml_list(_show(wt, f"{base}:{SUPPRESSIONS}"))}
    new_sups = [s for s in branch_sup if s["fp"] not in base_sup_fps]
    raw_changed = [l for l in git("diff", "--name-only", f"{base}..{old}", "--", SOURCE_RAW, cwd=wt).splitlines() if l]
    # A data PR made by hand (#103) has no proposals: its edits to data/corrections are its sources
    hand = "" if P.active(doc) else _diff(wt, base, old, CORRECTIONS)

    git("switch", "-q", "-C", branch, "origin/main", cwd=wt)
    if raw_changed:
        git("checkout", old, "--", *raw_changed, cwd=wt)
    if hand:
        r = subprocess.run(["git", "apply", "--3way", "--index"], input=hand, cwd=wt, text=True, capture_output=True)
        if r.returncode != 0:
            git("reset", "-q", "--hard", old, cwd=wt)
            raise SystemExit(f"rebase stopped: the branch's own edits to {CORRECTIONS} do not apply on origin/main:\n"
                             f"{(r.stderr or r.stdout).strip()}\nResolve it by hand; nothing was pushed.")
    corrections = wt / CORRECTIONS
    for p in P.active(doc):
        try:
            block, old_text = P.apply_op(corrections, p)
            if old_text is not None:
                p["old_text"] = old_text
        except P.ProposalError as e:
            git("reset", "-q", "--hard", old, cwd=wt)
            raise SystemExit(f"rebase stopped: {p['fp']}: {e}. Resolve it by hand; nothing was pushed.")
        p["yaml_text"] = block
    main_sup_fps = {s["fp"] for s in _yaml_list(_read(wt / SUPPRESSIONS))}
    from qa.sync import append_suppression
    for s in new_sups:
        if s["fp"] not in main_sup_fps:
            append_suppression(wt, s)
    P.save(wt, doc)
    git("add", "data/corrections", SUPPRESSIONS, P.PROPOSALS_FILE, *raw_changed, cwd=wt)
    git("commit", "-q", "-m", "qa: rebase source changes onto origin/main\n\nDerived data is regenerated "
        "by /apply-approved, never merged by hand.\n\nCo-Authored-By: apply.sh <noreply@laciutatparla.es>", cwd=wt)
    print(f"rebased {branch} onto origin/main: {len(P.active(doc))} proposal(s), {len(new_sups)} suppression(s), "
          f"{len(raw_changed)} data/raw file(s)" + (", the branch's own edits to data/corrections" if hand else ""))
    return True


def _diff(wt: Path, base: str, head: str, path: str) -> str:
    """base..head under path, as a patch (git() strips the final newline git apply needs)."""
    return subprocess.run(["git", "diff", "--binary", f"{base}..{head}", "--", path], cwd=wt, check=True,
                          text=True, capture_output=True).stdout


def _is_ancestor(wt: Path) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], cwd=wt).returncode == 0


def _show(wt: Path, spec: str) -> str:
    import subprocess
    r = subprocess.run(["git", "show", spec], cwd=wt, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _yaml_list(text: str) -> list:
    data = yaml.safe_load(text) if text else None
    return [d for d in (data or []) if isinstance(d, dict)]


def preview(wt: Path) -> str:
    doc = P.load(wt)
    raw = {iv["id"]: iv for iv in json.loads(_read(wt / "data/raw/interventions_raw.json") or "[]")}
    lines = []
    for p in P.active(doc):
        lines.append(f"- {p['severity']} `{p['fp']}` {p['title']} → data/corrections/{p['file']}")
        e = p["entry"]
        if p["file"] == "patches.yml":
            iv = raw.get(str(e.get("iv_id")), {})
            for field, new in (e.get("fields") or {}).items():
                lines.append(f"    {e.get('iv_id')}.{field}: {json.dumps(iv.get(field), ensure_ascii=False)} "
                             f"→ {json.dumps(new, ensure_ascii=False)}")
        else:
            lines.append("    " + json.dumps({k: v for k, v in e.items() if k not in ('reason', 'date', 'finding')},
                                             ensure_ascii=False)[:300])
    rejected = [p for p in doc["proposals"] if p["status"] == "rejected"]
    if rejected:
        lines.append(f"(rejected, not applied: {', '.join(p['fp'] for p in rejected)})")
    return "\n".join(lines) or "no live proposals"


def bold_count(wt: Path) -> int:
    # an empty text_cas/text_val is published as text_original (script 07): a proposal that empties
    # a translation because the speech is already in that language keeps its bold
    ivs = json.loads(_read(wt / "data/raw/interventions_raw.json") or "[]")
    return sum(1 for iv in ivs for f in ("text_original", "text_cas", "text_val")
               if "**" in (iv.get(f) or iv.get("text_original") or ""))


def data_summary(wt: Path) -> str:
    before = {iv["id"]: iv for iv in json.loads(_show(wt, "origin/main:data/intervencions.json") or "[]")}
    after = {iv["id"]: iv for iv in json.loads(_read(wt / "data/intervencions.json") or "[]")}
    ents_b = len(json.loads(_show(wt, "origin/main:data/entitats.json") or "[]"))
    ents_a = len(json.loads(_read(wt / "data/entitats.json") or "[]"))
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = []
    for iv_id in sorted(set(before) & set(after)):
        fields = [f for f in DIFF_FIELDS if before[iv_id].get(f) != after[iv_id].get(f)]
        if fields:
            changed.append((iv_id, fields))
    out = [f"| | before (main) | after (this branch) |", "|---|---|---|",
           f"| Interventions | {len(before)} | {len(after)} |", f"| Entities | {ents_b} | {ents_a} |", ""]
    if added:
        out.append("**Added:** " + ", ".join(f"`{i}`" for i in added))
    if removed:
        out.append("**Removed:** " + ", ".join(f"`{i}`" for i in removed))
    if changed:
        out.append("**Changed:**")
        for iv_id, fields in changed:
            detail = "; ".join(
                f"{f}: {json.dumps(before[iv_id].get(f), ensure_ascii=False)[:80]} → "
                f"{json.dumps(after[iv_id].get(f), ensure_ascii=False)[:80]}"
                if f not in ("text_cas", "text_val") else f"{f} (text edited)" for f in fields)
            out.append(f"- `{iv_id}`: {detail}")
    if not (added or removed or changed):
        out.append("_No public intervention changes._")
    return "\n".join(out)


def prune_baseline(wt: Path) -> list[str]:
    """Shrink meta/qa/baseline.json after applying: drop the findings of the proposals just
    applied, and the known-issue ids that no longer have the problem. Never adds anything."""
    path = wt / "meta/qa/baseline.json"
    base = json.loads(path.read_text(encoding="utf-8"))
    applied = {p["fp"] for p in P.active(P.load(wt))}
    removed = [f["fp"] for f in base.get("findings", []) if f["fp"] in applied]
    base["findings"] = [f for f in base.get("findings", []) if f["fp"] not in applied]
    ivs = {iv["id"]: iv for iv in json.loads(_read(wt / "data/intervencions.json") or "[]")}
    tax_file = wt / "scripts/lib/taxonomy.json"
    tax = json.loads(tax_file.read_text(encoding="utf-8"))["categories"] if tax_file.exists() else None
    CATEGORIES = set(tax or {})
    SUBCATEGORIES = {s for subs in (tax or {}).values() for s in subs}
    still = {
        "ambit_barri_without_zones": lambda iv: iv.get("ambit") == "barri" and not iv.get("zones"),
        "missing_temes_v2": lambda iv: not iv.get("temes_v2"),
        "invalid_temes_v2": lambda iv: any(c not in CATEGORIES or any(s not in SUBCATEGORIES for s in subs)
                                           for c, subs in (iv.get("temes_v2") or {}).items()),
    }
    if tax is None:  # no single taxonomy file in this checkout: leave that list alone
        still.pop("invalid_temes_v2")
    for name, issue in base.get("known_issues", {}).items():
        test = still.get(name)
        if not test:
            continue
        keep = [i for i in issue["ids"] if i in ivs and test(ivs[i])]
        removed += [f"{name}:{i}" for i in issue["ids"] if i not in keep]
        issue["ids"] = keep
    if removed:
        path.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return removed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("step", choices=["check", "rebase", "preview", "bold-count", "summary", "prune-baseline"])
    ap.add_argument("--pr", type=int)
    ap.add_argument("--worktree", type=Path, default=Path.cwd())
    args = ap.parse_args(argv)
    wt = args.worktree.resolve()
    if args.step == "check":
        print(check_pr(wt, args.pr))
    elif args.step == "rebase":
        rebase(wt)
    elif args.step == "preview":
        print(preview(wt))
    elif args.step == "prune-baseline":
        removed = prune_baseline(wt)
        print("baseline: removed " + (", ".join(removed) if removed else "nothing"))
    elif args.step == "bold-count":
        print(bold_count(wt))
    elif args.step == "summary":
        text = data_summary(wt)
        print(text)
        if args.pr:
            P.update_pr_body(wt, args.pr, P.load(wt), text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

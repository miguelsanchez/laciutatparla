#!/usr/bin/env python3
"""Fail when the derived data does not reflect data/corrections/ (the PR #63 incident).

A qa-data PR carries YAML corrections; /apply-approved then regenerates the derived data on the
same branch (apply_merges → 07 → export_dataset). If the PR is merged before that, main holds
corrections the site never shows. Run on every PR by .github/workflows/derived-data.yml, this
check turns that state red:

  1. apply_merges, run in memory on data/, must reproduce interventions_raw.json and
     entity_variant_map.json byte for byte (it is idempotent once applied);
  2. data/intervencions.json must hold the same ids as interventions_raw.json, with the fields
     script 07 copies verbatim unchanged.

Read-only, no API, a few seconds. entitats.json is not compared: script 07 rewrites it.

    "$PY" scripts/qa/check_derived.py [--data-dir data]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apply_merges as A  # noqa: E402

# Fields script 07 copies from interventions_raw.json without transforming them
VERBATIM = ("pleno_id", "ordre", "intervinient", "entitat", "idioma_original", "resum_cas", "resum_val",
            "temes_v2", "ambit", "cap_major", "cap_subtopics")
SHOWN = 8


def _ids(items, limit=SHOWN) -> str:
    items = sorted(items)
    return ", ".join(items[:limit]) + (f" … (+{len(items) - limit})" if len(items) > limit else "")


def unapplied(data_dir: Path) -> list[str]:
    """What apply_merges would still change in data/raw."""
    result = A.apply_corrections(A.load_inputs(data_dir), log=lambda *a, **k: None)
    p = A.paths(data_dir)
    problems = []
    current = json.loads(p["interventions"].read_text(encoding="utf-8"))
    expected = result["interventions"]
    if p["interventions"].read_text(encoding="utf-8") != json.dumps(expected, ensure_ascii=False, indent=2):
        cur, exp = {i["id"]: i for i in current}, {i["id"]: i for i in expected}
        changed = [k for k in set(cur) & set(exp) if cur[k] != exp[k]]
        problems.append("interventions_raw.json is behind data/corrections/: "
                        + "; ".join(part for part in (
                            f"missing {_ids(set(exp) - set(cur))}" if set(exp) - set(cur) else "",
                            f"should be gone {_ids(set(cur) - set(exp))}" if set(cur) - set(exp) else "",
                            f"changed {_ids(changed)}" if changed else "",
                            "order or formatting" if not (set(exp) ^ set(cur) or changed) else "") if part))
    if p["variant_map"].read_text(encoding="utf-8") != json.dumps(result["variant_map"], ensure_ascii=False, indent=2):
        problems.append("entity_variant_map.json is behind data/corrections/")
    return problems


def stale_final(data_dir: Path) -> list[str]:
    """Where intervencions.json does not reflect interventions_raw.json (script 07 not rerun)."""
    raw = {i["id"]: i for i in json.loads((data_dir / "raw/interventions_raw.json").read_text(encoding="utf-8"))}
    final = {i["id"]: i for i in json.loads((data_dir / "intervencions.json").read_text(encoding="utf-8"))}
    problems = []
    if set(raw) - set(final):
        problems.append(f"intervencions.json lacks {_ids(set(raw) - set(final))}")
    if set(final) - set(raw):
        problems.append(f"intervencions.json still has {_ids(set(final) - set(raw))}")
    changed = [k for k in set(raw) & set(final) if any(raw[k].get(f) != final[k].get(f) for f in VERBATIM)]
    if changed:
        problems.append(f"intervencions.json differs from interventions_raw.json in {_ids(changed)}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=A.DATA_DIR)
    args = ap.parse_args(argv)
    problems = unapplied(args.data_dir) + stale_final(args.data_dir)
    if not problems:
        print("check_derived: the derived data reflects data/corrections/")
        return 0
    for p in problems:
        print(f"check_derived: {p}")
    print("\nThe corrections are not applied yet. On the dedicated Mac run /apply-approved <PR> before "
          "merging: merging now would publish without them.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Detect plenary sessions where the parser likely missed citizen interventions.

For each text file in data/raw/texts/, counts occurrences of the citizen
intervention section headers, deduplicates repeated page-header copies, and
compares with the number of interventions extracted in interventions_raw.json.

Heuristic signals used:
  1. Sessions with header blocks but 0 interventions extracted (high confidence)
  2. Sessions with header blocks but unusually few interventions per block
  3. Sessions whose extracted count changed after manual corrections were applied
     (these are already fixed, shown for reference)

Note: the heading `INTERVENCIONS CIUTADANES` may appear multiple times in a
single acta because pdftotext copies page headers — we deduplicate by ignoring
any occurrence within 200 characters of the previous one.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXTS_DIR = ROOT / "data" / "raw" / "texts"
INTERVENTIONS_FILE = ROOT / "data" / "raw" / "interventions_raw.json"
MANUAL_CORRECTIONS_FILE = ROOT / "data" / "corrections" / "manual_interventions.yml"

HEADER_PATTERN = re.compile(
    r"INTERVENCI[OÓ]N?S? CIUTADAN[AE]S?(?:/INTERVENCIONES CIUDADANAS)?",
    re.IGNORECASE,
)

# Occurrences within this many characters of each other are considered the same
# (page-header copy), not a new section
DEDUP_WINDOW = 500

# Sessions with fewer interventions than this per block are flagged as suspicious
MIN_PER_BLOCK = 1


def count_header_blocks(text: str) -> int:
    """Count deduplicated occurrences of the citizen intervention header."""
    positions = [m.start() for m in HEADER_PATTERN.finditer(text)]
    if not positions:
        return 0
    deduped = [positions[0]]
    for pos in positions[1:]:
        if pos - deduped[-1] > DEDUP_WINDOW:
            deduped.append(pos)
    return len(deduped)


def load_manual_pleno_ids() -> set[str]:
    """Return pleno_ids that have manual interventions (already fixed)."""
    try:
        import yaml
        data = yaml.safe_load(MANUAL_CORRECTIONS_FILE.read_text()) or []
        return {iv["pleno_id"] for iv in data}
    except Exception:
        return set()


def main():
    # ── Load extracted interventions ──────────────────────────────────────────
    ivs = json.loads(INTERVENTIONS_FILE.read_text())
    extracted_counts = defaultdict(int)
    for iv in ivs:
        extracted_counts[iv["pleno_id"]] += 1

    manual_plenos = load_manual_pleno_ids()

    # ── Analyse each text file ────────────────────────────────────────────────
    rows = []
    for tfile in sorted(TEXTS_DIR.glob("*.txt")):
        pleno_id = tfile.stem
        text = tfile.read_text(errors="replace")
        blocks = count_header_blocks(text)
        n_extracted = extracted_counts.get(pleno_id, 0)
        has_manual = pleno_id in manual_plenos
        rows.append({
            "pleno_id": pleno_id,
            "blocks": blocks,
            "extracted": n_extracted,
            "has_manual": has_manual,
        })

    # ── Categorise ───────────────────────────────────────────────────────────
    # HIGH: header blocks present but 0 interventions extracted
    high = [r for r in rows if r["blocks"] > 0 and r["extracted"] == 0]
    # LOW: extracted < blocks (fewer than 1 per block), suspicious
    low = [r for r in rows if r["blocks"] > 0 and 0 < r["extracted"] < r["blocks"] * MIN_PER_BLOCK]
    # ALREADY FIXED: had manual additions
    fixed = [r for r in rows if r["has_manual"]]
    # OK: blocks > 0 and extracted >= blocks
    ok = [r for r in rows if r["blocks"] > 0 and r["extracted"] >= r["blocks"] and not r["has_manual"]]
    # NO_HEADER: no header found (normal — many sessions have no citizen interventions)
    no_header = [r for r in rows if r["blocks"] == 0]

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"=== detect_missed_interventions.py ===")
    print(f"Analysed {len(rows)} text files\n")

    if high:
        print(f"🔴 HIGH RISK — {len(high)} session(s) with header but 0 interventions extracted:")
        for r in sorted(high, key=lambda x: x["pleno_id"], reverse=True):
            print(f"  {r['pleno_id']:25s}  blocks={r['blocks']}  extracted=0")
        print()
    else:
        print("✓  No sessions with headers and 0 interventions.\n")

    if low:
        print(f"🟡 LOW RISK — {len(low)} session(s) with fewer extractions than blocks:")
        for r in sorted(low, key=lambda x: x["pleno_id"], reverse=True):
            ratio = r["extracted"] / r["blocks"] if r["blocks"] else 0
            print(f"  {r['pleno_id']:25s}  blocks={r['blocks']}  extracted={r['extracted']}  ({ratio:.1f} per block)")
        print()

    if fixed:
        print(f"ℹ️   {len(fixed)} session(s) had manual corrections applied (already fixed):")
        for r in sorted(fixed, key=lambda x: x["pleno_id"], reverse=True):
            print(f"  {r['pleno_id']:25s}  blocks={r['blocks']}  extracted={r['extracted']}")
        print()

    print(f"Summary:")
    print(f"  {len(high):3d}  sessions need investigation (headers, 0 extracted)")
    print(f"  {len(low):3d}  sessions possibly under-extracted")
    print(f"  {len(fixed):3d}  sessions already fixed with manual corrections")
    print(f"  {len(ok):3d}  sessions OK")
    print(f"  {len(no_header):3d}  sessions with no citizen intervention header")

    if high:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

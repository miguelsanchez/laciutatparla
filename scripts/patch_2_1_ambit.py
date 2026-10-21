#!/usr/bin/env python3
"""
Patch 2.1: Fix ambit=ciutat interventions that have specific zones/districtes.

Rule:
  - 19 districtes → keep ciutat
  - 2+ districtes → multi_districte
  - 1 districte, 2+ zones → multi_barri
  - 1 districte, 1 zone → barri

Also fixes:
  - 2020-11-19-001: missing entitat name
  - 2025-10-02-1-006: missing temes_v2

Run from repo root. Patches interventions_raw.json and intervencions.json in place.
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_FILE = ROOT / "data" / "raw" / "interventions_raw.json"
FINAL_FILE = ROOT / "data" / "intervencions.json"
PLENOS_DIR = ROOT / "data" / "plenos"


def new_ambit(iv: dict) -> str | None:
    """Return corrected ambit or None if no change needed."""
    if iv.get("ambit") != "ciutat":
        return None
    zones = iv.get("zones") or []
    districtes = iv.get("districtes") or []
    if not zones and not districtes:
        return None
    n_dist = len(districtes)
    n_zones = len(zones)
    if n_dist == 19:
        return None  # genuinely city-wide
    if n_dist >= 2:
        return "multi_districte"
    if n_zones == 1:
        return "barri"
    return "multi_barri"


def patch_intervention(iv: dict) -> bool:
    changed = False

    # Ambit fix
    corrected = new_ambit(iv)
    if corrected:
        iv["ambit"] = corrected
        changed = True

    # Missing entitat name
    if iv.get("id") == "2020-11-19-001" and not iv.get("entitat"):
        iv["entitat"] = "Particular"
        changed = True

    # Missing temes_v2
    if iv.get("id") == "2025-10-02-1-006" and not iv.get("temes_v2"):
        iv["temes_v2"] = {"mobilitat": ["mobilitat_activa"], "urbanisme": ["espai_public"]}
        changed = True

    return changed


def main():
    # ── Patch interventions_raw.json ─────────────────────────────────────────
    raw = json.loads(RAW_FILE.read_text())
    raw_changed = 0
    for iv in raw:
        if patch_intervention(iv):
            raw_changed += 1
    RAW_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"interventions_raw.json: {raw_changed} interventions patched")

    # ── Patch intervencions.json ─────────────────────────────────────────────
    final = json.loads(FINAL_FILE.read_text())
    final_changed = Counter()
    for iv in final:
        corrected = new_ambit(iv)
        if corrected:
            final_changed[f"ciutat→{corrected}"] += 1
            iv["ambit"] = corrected
        if iv.get("id") == "2020-11-19-001" and not iv.get("entitat"):
            iv["entitat"] = "Particular"
            final_changed["entitat"] += 1
        if iv.get("id") == "2025-10-02-1-006" and not iv.get("temes_v2"):
            iv["temes_v2"] = {"mobilitat": ["mobilitat_activa"], "urbanisme": ["espai_public"]}
            final_changed["temes_v2"] += 1
    FINAL_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2))
    print(f"intervencions.json: {dict(final_changed)}")

    # ── Patch data/plenos/*.json ─────────────────────────────────────────────
    plenos_patched = 0
    for pleno_file in sorted(PLENOS_DIR.glob("*.json")):
        pleno = json.loads(pleno_file.read_text())
        changed = False
        for iv in pleno.get("intervencions", []):
            if patch_intervention(iv):
                changed = True
        if changed:
            pleno_file.write_text(json.dumps(pleno, ensure_ascii=False, indent=2))
            plenos_patched += 1
    print(f"data/plenos/: {plenos_patched} files patched")

    print("\nDone. Run tests to verify:")
    print("  cd scripts && python3 -m pytest tests/ -v")


if __name__ == "__main__":
    main()

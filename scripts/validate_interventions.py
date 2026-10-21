#!/usr/bin/env python3
"""
Validate all interventions in interventions_raw.json against canonical
taxonomies, CAP codes, and data quality rules.

Outputs a summary report to stdout and optionally a JSON file with errors.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

INTERVENTIONS_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"
BARRIS_FILE = Path(__file__).parent.parent / "data" / "raw" / "barris_referencia.json"

# ── Canonical taxonomy and CAP codebook (single source: scripts/lib/taxonomy.json) ──

sys.path.insert(0, str(Path(__file__).parent))
from lib import taxonomy  # noqa: E402

VALID_TAXONOMY = taxonomy.TAXONOMY
VALID_CATS = taxonomy.CATEGORIES
VALID_AMBITS = taxonomy.AMBITS
VALID_TIPUS = taxonomy.TIPUS
VALID_IDIOMES = taxonomy.IDIOMES
VALID_CAP_CODES = taxonomy.CAP_CODES

# A name the acta censored, as script 05 writes it ([***], sometimes [*]): its asterisks are not
# bold markers. The acta's own form (******) is not covered: it must not reach the data.
ANONYMISED = re.compile(r"\[\*+\]")


def load_barris():
    """Load barri reference data for zone validation."""
    if not BARRIS_FILE.exists():
        return set(), set()
    barris = json.loads(BARRIS_FILE.read_text())
    barri_names = {b["nom"].lower() for b in barris}
    districte_names = {b["districte_nom"].lower() for b in barris}
    return barri_names, districte_names


def load_zone_normalizer():
    """normalize_zones() and the barri lookup from script 07, so zones are judged exactly as
    the final build will write them ("Districte > Barri" → barri, district names → districtes).
    Returns None when the reference file is missing."""
    if not BARRIS_FILE.exists():
        return None
    path = Path(__file__).parent / "07_build_final_json.py"
    spec = importlib.util.spec_from_file_location("build_final_json", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lookup = mod._build_barri_lookup(json.loads(BARRIS_FILE.read_text()))
    return lambda zones, districtes: mod.normalize_zones(zones, districtes, lookup)


def fuzzy_suggest(name: str, valid: set[str], threshold: float = 0.6) -> str | None:
    """Find the closest match in valid set."""
    best, best_score = None, 0
    name_lower = name.lower()
    for v in valid:
        score = SequenceMatcher(None, name_lower, v).ratio()
        if score > best_score:
            best_score = score
            best = v
    return best if best_score >= threshold else None


def validate(ivs: list[dict], barri_names: set[str], districte_names: set[str],
             normalize=None) -> tuple[list, list]:
    """Validate all interventions. Returns (errors, warnings).

    `normalize(zones, districtes) -> (zones, districtes)` is applied before the zone checks
    (see load_zone_normalizer); without it zones are checked as written.
    """
    errors = []
    warnings = []

    for iv in ivs:
        iv_id = iv.get("id", "?")
        zones = iv.get("zones") or []
        districtes = iv.get("districtes") or []
        if normalize:
            zones, districtes = normalize(zones, districtes)

        # ── Errors (strict validation) ──

        # temes_v2
        temes = iv.get("temes_v2")
        if isinstance(temes, dict):
            for cat, subs in temes.items():
                if cat not in VALID_CATS:
                    errors.append(f"{iv_id}: temes_v2 categoria '{cat}' inválida")
                elif isinstance(subs, list):
                    valid_subs = set(VALID_TAXONOMY[cat])
                    for s in subs:
                        if s not in valid_subs:
                            errors.append(f"{iv_id}: temes_v2 subcategoría '{s}' inválida para '{cat}'")

        # ambit
        ambit = iv.get("ambit", "")
        if ambit and ambit not in VALID_AMBITS:
            errors.append(f"{iv_id}: ambit '{ambit}' inválido")

        # cap_subtopics
        for code in iv.get("cap_subtopics", []):
            if isinstance(code, (int, float)) and int(code) not in VALID_CAP_CODES:
                errors.append(f"{iv_id}: cap_subtopic {int(code)} no existe en codebook")

        # tipus_entitat
        tipus = iv.get("tipus_entitat", "")
        if tipus and tipus not in VALID_TIPUS:
            errors.append(f"{iv_id}: tipus_entitat '{tipus}' inválido")

        # idioma_original
        idioma = iv.get("idioma_original", "")
        if idioma and idioma not in VALID_IDIOMES:
            errors.append(f"{iv_id}: idioma_original '{idioma}' inválido")

        # text_original empty or too short
        text_orig = iv.get("text_original") or ""
        if len(text_orig) < 50:
            errors.append(f"{iv_id}: text_original vacío o < 50 chars ({len(text_orig)})")

        # Bold marker balance, the anonymised names ([***]) aside: they are not markers
        for field in ("text_original", "text_cas", "text_val"):
            text = ANONYMISED.sub("", iv.get(field) or "")
            if text and text.count("**") % 2 != 0:
                errors.append(f"{iv_id}: número impar de ** en {field}")

        # ── Warnings (soft validation) ──

        # Zones not in barris_referencia
        if barri_names:
            for zone in zones:
                if zone.lower() not in barri_names:
                    suggestion = fuzzy_suggest(zone, barri_names)
                    hint = f" (sugerencia: '{suggestion}')" if suggestion else ""
                    warnings.append(f"{iv_id}: zona '{zone}' no reconocida{hint}")

        # Districtes not in reference
        if districte_names:
            for dist in districtes:
                if dist.lower() not in districte_names:
                    suggestion = fuzzy_suggest(dist, districte_names)
                    hint = f" (sugerencia: '{suggestion}')" if suggestion else ""
                    warnings.append(f"{iv_id}: districte '{dist}' no reconocido{hint}")

        # Entity contains institutional role names
        entitat = (iv.get("entitat") or "").lower()
        for suspect in ("presidenta", "alcaldesa", "alcalde", "concejal", "regidor"):
            if suspect in entitat:
                warnings.append(f"{iv_id}: entitat contiene '{suspect}' — posible error de atribución")

        # Suspiciously long text
        if len(text_orig) > 20000:
            warnings.append(f"{iv_id}: text_original muy largo ({len(text_orig)} chars)")

        # Both translations empty
        cas = iv.get("text_cas") or ""
        val = iv.get("text_val") or ""
        if not cas and not val:
            warnings.append(f"{iv_id}: text_cas y text_val ambos vacíos")

        # Too many CAP codes
        cap = iv.get("cap_subtopics", [])
        if len(cap) > 4:
            warnings.append(f"{iv_id}: {len(cap)} cap_subtopics (máximo recomendado: 4)")

        # Too many temes categories
        if isinstance(temes, dict) and len(temes) > 3:
            warnings.append(f"{iv_id}: {len(temes)} categorías temes_v2 (máximo recomendado: 3)")

        # No bold markers in texts
        has_bold = "**" in text_orig or "**" in cas or "**" in val
        if not has_bold and len(text_orig) >= 100:
            warnings.append(f"{iv_id}: sin marcadores ** en ningún texto")

        # Validation warnings from extraction
        if iv.get("validation_warnings"):
            for w in iv["validation_warnings"]:
                warnings.append(f"{iv_id}: [extraction] {w}")

    return errors, warnings


def main():
    if not INTERVENTIONS_FILE.exists():
        print(f"Error: {INTERVENTIONS_FILE} not found")
        sys.exit(1)

    ivs = json.loads(INTERVENTIONS_FILE.read_text())
    barri_names, districte_names = load_barris()

    print(f"Validating {len(ivs)} interventions...")
    print(f"Valid categories: {sorted(VALID_CATS)}")
    print(f"Valid CAP codes: {len(VALID_CAP_CODES)}")
    print(f"Barris reference: {len(barri_names)} barris, {len(districte_names)} districtes")
    print()

    errors, warnings = validate(ivs, barri_names, districte_names, load_zone_normalizer())

    # Summary
    ok = len(ivs) - len(set(e.split(":")[0] for e in errors))
    print(f"=== Informe de validación ===")
    print(f"Total: {len(ivs)} intervenciones")
    print(f"OK: {ok} | Errores: {len(errors)} | Warnings: {len(warnings)}")
    print()

    if errors:
        print("ERRORES:")
        for e in sorted(errors):
            print(f"  {e}")
        print()

    if warnings:
        print("WARNINGS:")
        for w in sorted(warnings):
            print(f"  {w}")
        print()

    # Optionally save report to JSON
    if "--json" in sys.argv:
        report_file = Path(__file__).parent.parent / "data" / "raw" / "validation_report.json"
        report = {"total": len(ivs), "errors": errors, "warnings": warnings}
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Report saved to {report_file}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

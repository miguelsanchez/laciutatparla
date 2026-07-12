#!/usr/bin/env python3
"""
Script 07: Build the final JSON files for the web.
Combines raw data into the structured format expected by the Astro site.
Output:
  - data/plenos.json
  - data/plenos/{id}.json
  - data/intervencions.json
  - data/entitats.json (updated with barri field)
"""

import json
import re
from collections import defaultdict
from pathlib import Path

from slugify import slugify


# ─── Text paragraphing ──────────────────────────────────────────────────────
# Many texts come as a single long block without line breaks.
# Split them into paragraphs at sentence boundaries for readability.

_SENTENCE_END = re.compile(
    r'\.\s+(?=[A-ZÁÉÍÓÚÀÈÒÜÇÑ¿¡«])'  # period + space + uppercase/opening
)

def _split_long_block(block: str, target: int = 450) -> list[str]:
    """Split a long text block into paragraphs at sentence boundaries."""
    if len(block) <= target:
        return [block]
    result = []
    remaining = block
    while len(remaining) > target:
        best = -1
        for m in _SENTENCE_END.finditer(remaining):
            pos = m.start() + 1  # after the dot
            if pos <= target * 1.3:
                best = pos
            else:
                break
        if best > target * 0.3:
            result.append(remaining[:best].strip())
            remaining = remaining[best:].strip()
        else:
            break
    if remaining.strip():
        result.append(remaining.strip())
    return result


def paragraphize(text: str) -> str:
    """Ensure text has paragraph breaks. Returns text with \n between paragraphs."""
    if not text or '\n' in text:
        return text  # already has structure
    parts = _split_long_block(text)
    if len(parts) <= 1:
        return text  # couldn't find good split points
    return '\n'.join(parts)

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

SESSIONS_META_FILE = RAW_DIR / "sessions_metadata.json"
INTERVENTIONS_FILE = RAW_DIR / "interventions_raw.json"
ENTITY_VARIANT_MAP_FILE = RAW_DIR / "entity_variant_map.json"
BARRIS_FILE = RAW_DIR / "barris_referencia.json"
ENTITIES_FILE = DATA_DIR / "entitats.json"

PLENOS_DIR = DATA_DIR / "plenos"
PLENOS_INDEX_FILE = DATA_DIR / "plenos.json"
INTERVENCIONS_FILE = DATA_DIR / "intervencions.json"
MANDATS_FILE = DATA_DIR / "mandats.json"


# ─── Zone / district normalization ─────────────────────────────────────────

def _build_barri_lookup(barris_ref: list) -> tuple:
    """Build lookup tables from barris_referencia.json.
    Returns (barri_by_name, districte_for_barri) where keys are lowercase.
    """
    barri_by_name = {}   # lowercase name → official record
    for b in barris_ref:
        barri_by_name[b["nom"].lower()] = b
    return barri_by_name


def normalize_zones(raw_zones: list, raw_districtes: list, barri_lookup: dict) -> tuple:
    """Normalize zones to official barri names and infer districtes.

    Handles:
    - "Districte > Barri" format → extract barri part
    - Exact match against barris_referencia
    - District names used as zones → move to districtes only
    Returns (zones, districtes) with official names.
    """
    # Collect all known district names
    all_districtes = {b["districte_nom"].lower(): b["districte_nom"] for b in barri_lookup.values()}

    normalized_zones = []
    inferred_districtes = set()

    for z in raw_zones:
        z_stripped = z.strip()

        # Handle "Districte > Barri" format
        if " > " in z_stripped:
            parts = z_stripped.split(" > ", 1)
            barri_part = parts[1].strip()
        else:
            barri_part = z_stripped

        # Try exact match (case-insensitive)
        barri_key = barri_part.lower()
        if barri_key in barri_lookup:
            official = barri_lookup[barri_key]
            normalized_zones.append(official["nom"])
            inferred_districtes.add(official["districte_nom"])
        elif barri_key in all_districtes:
            # It's a district name, not a barri — add to districtes only
            inferred_districtes.add(all_districtes[barri_key])
        else:
            # Unknown zone — keep as-is but don't duplicate
            normalized_zones.append(barri_part)

    # Also include raw districtes that weren't inferred
    for d in raw_districtes:
        d_key = d.strip().lower()
        if d_key in all_districtes:
            inferred_districtes.add(all_districtes[d_key])

    # Deduplicate while preserving order
    seen_z = set()
    unique_zones = []
    for z in normalized_zones:
        if z.lower() not in seen_z:
            seen_z.add(z.lower())
            unique_zones.append(z)

    return unique_zones, sorted(inferred_districtes)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def get_mandat_id(fecha: str, mandats: list) -> str:
    """Find the mandate a pleno belongs to based on its date."""
    for m in mandats:
        inici = m["inici"]
        fi = m.get("fi")
        if fecha >= inici and (fi is None or fecha <= fi):
            return m["id"]
    return "desconegut"


def get_entity_id(entitat: str, variant_map: dict) -> str:
    """Get canonical entity ID from any variant name."""
    if not entitat:
        return "desconegut"
    return variant_map.get(entitat.lower().strip(), slugify(entitat))


def build_intervention(raw: dict, variant_map: dict, entities_by_id: dict, mandats: list, barri_lookup: dict) -> dict:
    """Transform a raw intervention into the final web format."""
    entitat_raw = raw.get("entitat") or ""
    entitat_id = get_entity_id(entitat_raw, variant_map)
    entity = entities_by_id.get(entitat_id)
    tipus = entity["tipus"] if entity else (raw.get("tipus_entitat") or "altres")
    fecha = raw["pleno_id"][:10]
    zones, districtes = normalize_zones(raw.get("zones", []), raw.get("districtes", []), barri_lookup)

    return {
        "id": raw["id"],
        "pleno_id": raw["pleno_id"],
        "fecha": fecha,
        "mandat_id": get_mandat_id(fecha, mandats),
        "ordre": raw.get("ordre", 0),
        "intervinient": raw.get("intervinient") or "",
        "entitat": entitat_raw,
        "entitat_id": entitat_id,
        "tipus_entitat": tipus,
        "barri_o_zona": raw.get("barri_o_zona"),
        "punts_ordre_dia": raw.get("punts_ordre_dia") or "",
        "idioma_original": raw.get("idioma_original") or "castellano",
        # text_cas/text_val may be empty string when original is already in that language
        "text_cas": paragraphize(raw.get("text_cas") or raw.get("text_original", "")),
        "text_val": paragraphize(raw.get("text_val") or raw.get("text_original", "")),
        "temes": raw.get("temes", []),
        "temes_v2": raw.get("temes_v2", {}),
        "ambit": raw.get("ambit", "no_especificat"),
        "zones": zones,
        "districtes": districtes,
        "resum_cas": raw.get("resum_cas", ""),
        "resum_val": raw.get("resum_val", ""),
        "cap_subtopics": raw.get("cap_subtopics", []),
        "cap_major": raw.get("cap_major", []),
    }


def main():
    # Load raw data
    print("Loading raw data...")
    sessions_meta = {s["id"]: s for s in load_json(SESSIONS_META_FILE)}
    interventions_raw = load_json(INTERVENTIONS_FILE)
    variant_map = load_json(ENTITY_VARIANT_MAP_FILE) if ENTITY_VARIANT_MAP_FILE.exists() else {}
    entities_list = load_json(ENTITIES_FILE) if ENTITIES_FILE.exists() else []
    mandats = load_json(MANDATS_FILE) if MANDATS_FILE.exists() else []
    barris_ref = load_json(BARRIS_FILE) if BARRIS_FILE.exists() else []
    barri_lookup = _build_barri_lookup(barris_ref)

    print(f"  Sessions: {len(sessions_meta)}")
    print(f"  Interventions: {len(interventions_raw)}")
    print(f"  Entities: {len(entities_list)}")
    print(f"  Barris reference: {len(barri_lookup)}")

    # Transform all interventions
    print("\nBuilding interventions...")
    entities_by_id = {e["id"]: e for e in entities_list}
    all_interventions = [build_intervention(r, variant_map, entities_by_id, mandats, barri_lookup) for r in interventions_raw]

    # Group by pleno
    by_pleno = defaultdict(list)
    for iv in all_interventions:
        by_pleno[iv["pleno_id"]].append(iv)

    # Sort each pleno's interventions by order
    for pleno_id in by_pleno:
        by_pleno[pleno_id].sort(key=lambda iv: iv["ordre"])

    # Build per-pleno JSON files
    PLENOS_DIR.mkdir(parents=True, exist_ok=True)
    print("\nBuilding per-pleno JSON files...")
    plenos_index = []

    for sid, session in sorted(sessions_meta.items(), reverse=True):
        interventions = by_pleno.get(sid, [])
        fecha = session.get("fecha", sid[:10])

        pleno_data = {
            "id": sid,
            "fecha": fecha,
            "tipo": session.get("tipo", "ordinaria"),
            "mandat_id": get_mandat_id(fecha, mandats),
            "acta_disponible": session.get("acta_disponible", False),
            "url_web": session.get("url_web", ""),
            "url_acta": session.get("url_acta"),
            "url_orden_dia": session.get("url_orden_dia"),
            "url_video": session.get("url_video"),
            "num_intervencions": len(interventions),
            "intervencions": interventions,
        }

        pleno_file = PLENOS_DIR / f"{sid}.json"
        pleno_file.write_text(json.dumps(pleno_data, ensure_ascii=False, indent=2))

        # Index entry (without full intervention text for performance)
        plenos_index.append({
            "id": sid,
            "fecha": pleno_data["fecha"],
            "tipo": pleno_data["tipo"],
            "mandat_id": pleno_data["mandat_id"],
            "acta_disponible": pleno_data["acta_disponible"],
            "num_intervencions": pleno_data["num_intervencions"],
            "url_web": pleno_data["url_web"],
            "url_video": pleno_data["url_video"],
            # Preview: first entity names
            "entitats_preview": [iv["entitat"] for iv in interventions[:3]],
        })

    PLENOS_INDEX_FILE.write_text(json.dumps(plenos_index, ensure_ascii=False, indent=2))
    print(f"  Wrote {len(plenos_index)} pleno files + index")

    # Build flat interventions file
    print("\nBuilding global interventions index...")
    # Sort by date descending
    all_interventions.sort(key=lambda iv: (iv["fecha"], iv["ordre"]), reverse=True)
    INTERVENCIONS_FILE.write_text(json.dumps(all_interventions, ensure_ascii=False, indent=2))
    print(f"  Wrote {len(all_interventions)} interventions")

    # Update entities with barri info from interventions
    print("\nUpdating entities with aggregated data...")
    entity_barris = defaultdict(set)
    entity_temes = defaultdict(list)
    for iv in all_interventions:
        eid = iv["entitat_id"]
        if iv.get("barri_o_zona"):
            entity_barris[eid].add(iv["barri_o_zona"])
        entity_temes[eid].extend(iv.get("temes", []))

    entities_map = {e["id"]: e for e in entities_list}
    for eid, entity in entities_map.items():
        barris = list(entity_barris.get(eid, set()))
        entity["barri"] = barris[0] if len(barris) == 1 else (", ".join(sorted(barris)) if barris else None)
        # Most frequent themes for this entity
        from collections import Counter
        temes_count = Counter(entity_temes.get(eid, []))
        entity["temes_principals"] = [t for t, _ in temes_count.most_common(3)]

    updated_entities = sorted(entities_map.values(), key=lambda e: -e["num_intervencions"])
    ENTITIES_FILE.write_text(json.dumps(updated_entities, ensure_ascii=False, indent=2))
    print(f"  Updated {len(updated_entities)} entities")

    # Summary
    print("\n=== Build complete ===")
    print(f"  data/plenos.json          → {len(plenos_index)} plenos")
    print(f"  data/plenos/*.json        → {len(plenos_index)} files")
    print(f"  data/intervencions.json   → {len(all_interventions)} interventions")
    print(f"  data/entitats.json        → {len(updated_entities)} entities")

    with_iv = sum(1 for p in plenos_index if p["num_intervencions"] > 0)
    print(f"\n  Plenos with interventions: {with_iv}/{len(plenos_index)}")


if __name__ == "__main__":
    main()

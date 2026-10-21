#!/usr/bin/env python3
"""
Apply corrections to the intervention dataset.

All corrections are declarative YAML files in data/corrections/:
  entity_merges.yml       — merge multiple entity variants into one canonical entity
  variant_map_forced.yml  — force-correct specific entity text → entity ID mappings
  reassignments.yml       — re-attribute floor cessions to the actual speaker
  deletions.yml           — remove non-citizen interventions and spurious entities
  patches.yml             — field-level corrections for individual interventions
  manual_interventions.yml — interventions missed by the parser
  text_merges.yml         — concatenate split speeches into one intervention
  new_entities.yml        — entities to create from scratch (not via merges)

Run from project root or scripts/ after script 05 and 06.

  python3 scripts/apply_merges.py                     # rewrite data/ in place
  python3 scripts/apply_merges.py --data-dir DIR      # work on another copy of data/
  python3 scripts/apply_merges.py --dry-run           # compute everything, write nothing

Importable: load_inputs(data_dir) → apply_corrections(inputs) → write_outputs(data_dir, result).
apply_corrections() does no I/O, so the QA verifier can run it in memory (arquitectura-agentes §3.3).
"""
import argparse
import json
import yaml
from pathlib import Path
from slugify import slugify
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"

CORRECTION_FILES = {
    "variant_map_forced": "variant_map_forced.yml",    # list of {text, entity_id}
    "entity_merges":      "entity_merges.yml",         # list of merge groups
    "reassignments":      "reassignments.yml",         # list of {iv_id, entitat, entitat_id}
    "deletions":          "deletions.yml",             # {interventions: [...], entities: [...]}
    "patches":            "patches.yml",               # list of {iv_id, fields}
    "manual_interventions": "manual_interventions.yml",  # list of full intervention dicts
    "text_merges":        "text_merges.yml",           # list of {base_id, merge_ids}
    "new_entities":       "new_entities.yml",          # list of {id, nom_cas, nom_val, tipus}
}


def paths(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    return {
        "corrections": data_dir / "corrections",
        "interventions": data_dir / "raw" / "interventions_raw.json",
        "entities": data_dir / "entitats.json",
        "variant_map": data_dir / "raw" / "entity_variant_map.json",
    }


def load_yaml(corrections_dir: Path, filename: str):
    path = Path(corrections_dir) / filename
    data = yaml.safe_load(path.read_text()) or []
    return data


# ── Load source data ──────────────────────────────────────────────────────────
def load_inputs(data_dir: Path = DATA_DIR, corrections: dict | None = None) -> dict:
    """Read the source data and the correction YAMLs. `corrections` overrides any of them
    (same keys as CORRECTION_FILES) with already-parsed values, e.g. proposals not yet written."""
    p = paths(data_dir)
    variant_map_file = p["variant_map"]
    inputs = {
        "interventions": json.loads(p["interventions"].read_text()),
        "entities_list": json.loads(p["entities"].read_text()),
        "variant_map": json.loads(variant_map_file.read_text()) if variant_map_file.exists() else {},
    }
    for key, filename in CORRECTION_FILES.items():
        if corrections and key in corrections:
            inputs[key] = corrections[key]
        else:
            inputs[key] = load_yaml(p["corrections"], filename)
    return inputs


def apply_corrections(inputs: dict, log=print) -> dict:
    """Apply every correction in memory. Mutates `inputs`; returns the three outputs."""
    interventions = inputs["interventions"]
    entities_list = inputs["entities_list"]
    entities = {e["id"]: e for e in entities_list}
    variant_map = inputs["variant_map"]

    variant_map_forced = inputs["variant_map_forced"]
    entity_merges      = inputs["entity_merges"]
    reassignments_list = inputs["reassignments"]
    deletions_data     = inputs["deletions"]
    patches_list       = inputs["patches"]
    manual_ivs         = inputs["manual_interventions"]
    text_merges_list   = inputs["text_merges"]
    new_entities_list  = inputs["new_entities"]

    # ── Normalise loaded corrections into working dicts ───────────────────────

    # 1. Force-patch the variant map
    for entry in variant_map_forced:
        key = entry["text"].lower().strip()
        if variant_map.get(key) != entry["entity_id"]:
            log(f"  VM patch: {repr(key)} {variant_map.get(key)} -> {entry['entity_id']}")
            variant_map[key] = entry["entity_id"]

    # 2. Build helpers from deletions
    DELETE_IV_IDS    = {e["iv_id"]     for e in (deletions_data.get("interventions") or [])}
    DELETE_ENTITY_IDS = {e["entity_id"] for e in (deletions_data.get("entities")      or [])}

    # 3. Build reassignment lookup: iv_id → (entitat_name, entitat_id)
    REASSIGN = {
        e["iv_id"]: (e["entitat"], e["entitat_id"])
        for e in reassignments_list
    }

    # 3b. Floor-cession mentions: iv_id → the organisation the speaker really represented.
    # Display-only; never counted in entity aggregates.
    CESSIO = {
        e["iv_id"]: e["entitat_cessio"]
        for e in reassignments_list
        if e.get("entitat_cessio")
    }

    # 4. Build patches lookup: iv_id → fields dict
    IV_PATCHES = {e["iv_id"]: e["fields"] for e in patches_list}

    def text_to_eid(entitat_text: str) -> str:
        """Resolve entity text → entity ID via variant map, fallback to slug."""
        if not entitat_text:
            return "desconegut"
        return variant_map.get(entitat_text.lower().strip(), slugify(entitat_text))

    # ── Resolve entity merge groups ───────────────────────────────────────────
    # match_texts resolve via variant_map to find which current entity IDs belong
    # to each merge group.
    for m in entity_merges:
        found_ids = set()
        for text in m.get("match_texts", []):
            eid = variant_map.get(text.lower().strip())
            if eid:
                found_ids.add(eid)
        excluded_ids = set()
        for text in m.get("exclude_texts", []):
            eid = variant_map.get(text.lower().strip())
            if eid:
                excluded_ids.add(eid)
        m["_merge_from_ids"] = found_ids - excluded_ids
        if not found_ids and m.get("match_texts"):
            log(f"  WARNING: No entity IDs found for merge group '{m['canonical_id']}'")

    # Build old_id → canonical_id remap
    id_remap = {}
    for m in entity_merges:
        for old_id in m["_merge_from_ids"]:
            id_remap[old_id] = m["canonical_id"]

    log(f"Built id_remap with {len(id_remap)} entries")

    # ── Build new entity catalog ──────────────────────────────────────────────

    new_entities = {}

    # Add entities created by merges
    for m in entity_merges:
        cid = m["canonical_id"]
        new_entities[cid] = {
            "id": cid,
            "nom_cas": m["nom_cas"],
            "nom_val": m["nom_val"],
            "tipus": m["tipus"],
            "variants": [],
            "num_intervencions": 0,
            "barri": None,
            "temes_principals": [],
        }

    # Copy unchanged entities (not consumed by a merge, not deleted)
    merged_old_ids = set(id_remap.keys()) | {m["canonical_id"] for m in entity_merges}
    for eid, entity in entities.items():
        if eid not in merged_old_ids and eid not in DELETE_ENTITY_IDS:
            new_entities[eid] = entity

    # Ensure explicitly listed new entities exist (override if already present)
    for ne in new_entities_list:
        eid = ne["id"]
        new_entities[eid] = {
            "id": eid,
            "nom_cas": ne["nom_cas"],
            "nom_val": ne["nom_val"],
            "tipus": ne["tipus"],
            "variants": [],
            "num_intervencions": 0,
            "barri": None,
            "temes_principals": [],
        }

    # ── Apply manual interventions (insert or update) ────────────────────────
    _existing_idx = {iv.get("id", ""): i for i, iv in enumerate(interventions)}
    for miv in manual_ivs:
        iv_id = miv["id"]
        if iv_id not in _existing_idx:
            interventions.append(miv)
            log(f"  MANUAL INSERT: {iv_id} {miv['intervinient']} ({miv['entitat']})")
        else:
            interventions[_existing_idx[iv_id]].update(miv)
            log(f"  MANUAL UPDATE: {iv_id} {miv['intervinient']} ({miv['entitat']})")

    # ── Apply text merges (concatenate split speeches) ────────────────────────
    _iv_by_id = {iv.get("id", ""): iv for iv in interventions}
    _merge_delete = set()
    for tm in text_merges_list:
        base = _iv_by_id.get(tm["base_id"])
        if not base:
            log(f"  WARNING: merge base {tm['base_id']} not found")
            continue
        for mid in tm["merge_ids"]:
            src = _iv_by_id.get(mid)
            if not src:
                log(f"  WARNING: merge source {mid} not found")
                continue
            for field in ("text_cas", "text_val"):
                base_text = base.get(field) or ""
                src_text = src.get(field) or ""
                if src_text:
                    base[field] = base_text + "\n" + src_text if base_text else src_text
            base_temes = set(base.get("temes") or [])
            base_temes.update(src.get("temes") or [])
            base["temes"] = sorted(base_temes)
            _merge_delete.add(mid)
            log(f"  TEXT_MERGE: {mid} -> {tm['base_id']}")
    DELETE_IV_IDS.update(_merge_delete)

    # ── Build final intervention list ─────────────────────────────────────────
    new_interventions = []
    for iv in interventions:
        iv_id = iv.get("id", "")

        if iv_id in DELETE_IV_IDS:
            log(f"  DELETE: {iv_id}")
            continue

        current_entitat = iv.get("entitat") or ""
        current_eid = text_to_eid(current_entitat)

        if current_eid in DELETE_ENTITY_IDS:
            log(f"  DELETE (spurious entity {current_eid}): {iv_id}")
            continue

        iv = dict(iv)

        # Apply field patches
        if iv_id in IV_PATCHES:
            for field, value in IV_PATCHES[iv_id].items():
                old_val = iv.get(field, "")
                iv[field] = value
                log(f"  PATCH: {iv_id} {field}: {repr(old_val)} -> {repr(value)}")

        # Apply entity reassignment or merge remap
        if iv_id in REASSIGN:
            new_entitat, canonical_eid = REASSIGN[iv_id]
            iv["entitat"] = new_entitat
            iv["_eid"] = canonical_eid
            log(f"  REASSIGN: {iv_id} -> {canonical_eid}")
            cessio = CESSIO.get(iv_id)
            if cessio:
                iv["entitat_cessio"] = cessio
                log(f"    cessió: en nom de {cessio.get('nom_cas')}")
        else:
            canonical_eid = id_remap.get(current_eid, current_eid)
            iv["_eid"] = canonical_eid

        new_interventions.append(iv)

    # ── Recount and update entity counts ─────────────────────────────────────
    counts = defaultdict(int)
    for iv in new_interventions:
        eid = iv.get("_eid") or ""
        if eid and eid != "desconegut":
            counts[eid] += 1

    for eid in new_entities:
        new_entities[eid]["num_intervencions"] = counts.get(eid, 0)

    # Keep entities with interventions plus those explicitly always kept
    # (reassignment targets that may have 0 if the pleno isn't in the dataset yet)
    KEEP_ALWAYS = {e["entitat_id"] for e in reassignments_list}
    final_entities = [
        e for e in new_entities.values()
        if e["num_intervencions"] > 0 or e["id"] in KEEP_ALWAYS
    ]
    final_entities.sort(key=lambda e: -e["num_intervencions"])

    # ── Rebuild variant map and entity variants from actual intervention texts ─
    new_variant_map = {}
    entity_actual_texts = defaultdict(set)
    for iv in new_interventions:
        entitat = iv.get("entitat") or ""
        eid = iv.get("_eid") or ""
        if entitat and eid and eid != "desconegut":
            new_variant_map[entitat.lower().strip()] = eid
            entity_actual_texts[eid].add(entitat)
    for entity in final_entities:
        new_variant_map.setdefault(entity["nom_cas"].lower().strip(), entity["id"])
        new_variant_map.setdefault(entity["nom_val"].lower().strip(), entity["id"])
        entity["variants"] = sorted(entity_actual_texts.get(entity["id"], set()))

    # Remove temporary internal field
    for iv in new_interventions:
        iv.pop("_eid", None)

    # ── Verify ────────────────────────────────────────────────────────────────
    entity_ids = {e["id"] for e in final_entities}
    orphaned = set()
    for iv in new_interventions:
        eid = new_variant_map.get((iv.get("entitat") or "").lower().strip())
        if eid and eid not in entity_ids and eid != "desconegut":
            orphaned.add(eid)

    return {
        "interventions": new_interventions,
        "entities": final_entities,
        "variant_map": new_variant_map,
        "orphaned": orphaned,
        "n_interventions_before": len(interventions),
        "n_entities_before": len(entities),
    }


# ── Write outputs ─────────────────────────────────────────────────────────────
def write_outputs(data_dir: Path, result: dict) -> None:
    p = paths(data_dir)
    p["interventions"].write_text(json.dumps(result["interventions"], ensure_ascii=False, indent=2))
    p["entities"].write_text(json.dumps(result["entities"], ensure_ascii=False, indent=2))
    p["variant_map"].write_text(json.dumps(result["variant_map"], ensure_ascii=False, indent=2))


def print_summary(result: dict, log=print) -> None:
    log(f"\n=== Done ===")
    log(f"  Interventions: {result['n_interventions_before']} -> {len(result['interventions'])}")
    log(f"  Entities: {result['n_entities_before']} -> {len(result['entities'])}")
    if result["orphaned"]:
        log(f"  WARNING orphaned entity_ids: {result['orphaned']}")
    else:
        log("  All entity_ids resolved OK")

    log(f"\nTop 10 entities:")
    for e in result["entities"][:10]:
        log(f"  {e['num_intervencions']:3d}  {e['id']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR,
                    help="directory laid out like data/ (default: the repo's data/)")
    ap.add_argument("--dry-run", action="store_true",
                    help="apply the corrections in memory and write nothing")
    args = ap.parse_args(argv)

    result = apply_corrections(load_inputs(args.data_dir))
    if not args.dry_run:
        write_outputs(args.data_dir, result)
    print_summary(result)
    if args.dry_run:
        print("\n(dry run: nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

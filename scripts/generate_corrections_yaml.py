#!/usr/bin/env python3
"""
One-off script: extract constants from apply_merges.py and write data/corrections/*.yml.

Uses ast.literal_eval so no file I/O from apply_merges.py is executed.
Run once; after that, apply_merges.py reads from the YAMLs.
"""
import ast
import json
import yaml
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
ROOT = SCRIPTS_DIR.parent
CORRECTIONS_DIR = ROOT / "data" / "corrections"
APPLY_MERGES = SCRIPTS_DIR / "apply_merges.py"


def extract_constants(source: str) -> dict:
    """
    Execute only the constant-definition sections of apply_merges.py.
    We isolate lines between the MERGES/REASSIGN/etc. definitions and the
    processing code (which starts with 'Resolve merge_from entity IDs').
    """
    # Find the end of constant definitions (where processing begins)
    # The MANUAL_INTERVENTIONS processing loop comes first, before IV_TEXT_MERGES
    sentinel = "# Insert manual interventions or update existing ones"
    end_idx = source.find(sentinel)
    if end_idx == -1:
        sentinel = "# Resolve merge_from entity IDs"
        end_idx = source.find(sentinel)
    if end_idx == -1:
        raise ValueError(f"Could not find sentinel '{sentinel}' in apply_merges.py")
    constants_source = source[:end_idx]

    # Replace file-reading calls with safe stubs so the top of the file doesn't crash
    # We don't need variant_map at extraction time — MERGES uses literal strings
    stub_preamble = """
import json
from pathlib import Path
class _FakePath:
    def __init__(self, *a): pass
    def __truediv__(self, o): return self
    def exists(self): return False
    def read_text(self): return '{}'
    def write_text(self, t): pass
    def glob(self, p): return []

_orig_loads = json.loads
def _safe_loads(s):
    try: return _orig_loads(s)
    except: return {}

variant_map = {}
entities = {}
entities_list = []
interventions = []

from slugify import slugify
"""
    # Remove the original import block (lines up to first blank line after imports)
    # by replacing it; we prepend our stub and skip file-reading lines
    import re
    # Strip the original imports and data loading (lines 1–23 approx)
    # Find "VARIANT_MAP_FORCED = {" and keep from there
    vmf_start = constants_source.find("\nVARIANT_MAP_FORCED")
    if vmf_start == -1:
        vmf_start = constants_source.find("VARIANT_MAP_FORCED")
    constants_only = constants_source[vmf_start:]

    # Remove the loop that applies variant_map patches (side effect)
    constants_only = re.sub(
        r"for k, v in VARIANT_MAP_FORCED\.items\(\):.*?variant_map\[k\] = v\n",
        "",
        constants_only,
        flags=re.DOTALL,
    )
    # Remove the text_to_eid function definition (uses slugify, not needed)
    constants_only = re.sub(r"def text_to_eid.*?(?=\n# )", "", constants_only, flags=re.DOTALL)

    ns = {"__builtins__": {
        "dict": dict, "list": list, "set": set, "tuple": tuple,
        "print": print, "True": True, "False": False, "None": None,
        "enumerate": enumerate, "range": range, "len": len,
        "str": str, "int": int, "bool": bool,
    }}
    exec(constants_only, ns)

    # IV_TEXT_MERGES comes after the processing code — extract it separately
    tm_match = re.search(r"IV_TEXT_MERGES\s*=\s*(\[.*?\])\s*\n\n", source, re.DOTALL)
    if tm_match:
        ns["IV_TEXT_MERGES"] = ast.literal_eval(tm_match.group(1))

    # Extract manually-created entities from processing section
    # Pattern: new_entities["id"] = { dict literal }
    ensure_entities = []
    processing_section = source[end_idx:]
    for m in re.finditer(
        r'new_entities(?:\.setdefault)?\["([^"]+)"\]\s*=\s*(\{[^{}]+\})',
        processing_section,
        re.DOTALL,
    ):
        eid = m.group(1)
        try:
            data = ast.literal_eval(m.group(2))
            ensure_entities.append({
                "id": eid,
                "nom_cas": data.get("nom_cas", ""),
                "nom_val": data.get("nom_val", ""),
                "tipus": data.get("tipus", ""),
                "reason": "",
            })
        except (ValueError, SyntaxError):
            pass
    ns["ENSURE_ENTITIES"] = ensure_entities

    return ns


def write_yaml(path: Path, data, header: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ""
    if header:
        for line in header.strip().splitlines():
            text += f"# {line}\n"
        text += "\n"
    text += yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    path.write_text(text)
    print(f"  wrote {path.relative_to(ROOT)} ({len(data) if isinstance(data, (list, dict)) else '?'} entries)")


def main():
    source = APPLY_MERGES.read_text()
    c = extract_constants(source)

    print("Extracted constants:", [k for k in c if not k.startswith("_")])

    # ── variant_map_forced.yml ────────────────────────────────────────────────
    vmf = c.get("VARIANT_MAP_FORCED", {})
    vmf_list = [
        {"text": text, "entity_id": eid, "reason": ""}
        for text, eid in vmf.items()
    ]
    write_yaml(
        CORRECTIONS_DIR / "variant_map_forced.yml",
        vmf_list,
        header=(
            "Forced corrections to entity_variant_map.json.\n"
            "Applied before MERGES so that match_texts resolve to the right entity ID.\n"
            "reason: why Claude misgroups this text."
        ),
    )

    # ── entity_merges.yml ─────────────────────────────────────────────────────
    merges = c.get("MERGES", [])
    # Remove duplicate entries for same canonical_id (keep last, which has more match_texts)
    seen = {}
    for m in merges:
        cid = m["canonical_id"]
        if cid in seen:
            # Merge match_texts from both (deduplicated)
            existing = seen[cid]
            combined = list(dict.fromkeys(existing["match_texts"] + m["match_texts"]))
            existing["match_texts"] = combined
            if m.get("exclude_texts"):
                existing.setdefault("exclude_texts", [])
                for t in m["exclude_texts"]:
                    if t not in existing["exclude_texts"]:
                        existing["exclude_texts"].append(t)
        else:
            entry = {
                "canonical_id": m["canonical_id"],
                "nom_cas": m["nom_cas"],
                "nom_val": m["nom_val"],
                "tipus": m["tipus"],
                "match_texts": m["match_texts"],
            }
            if m.get("exclude_texts"):
                entry["exclude_texts"] = m["exclude_texts"]
            entry["reason"] = ""
            seen[cid] = entry
    write_yaml(
        CORRECTIONS_DIR / "entity_merges.yml",
        list(seen.values()),
        header=(
            "Entity merge groups.\n"
            "match_texts: entity name strings from interventions that identify members of this group.\n"
            "exclude_texts: entity texts whose IDs must NOT be included in the merge.\n"
            "reason: why these names represent the same entity."
        ),
    )

    # ── reassignments.yml ─────────────────────────────────────────────────────
    reassign = c.get("REASSIGN", {})
    reassign_list = [
        {
            "iv_id": iv_id,
            "entitat": tup[0],
            "entitat_id": tup[1],
            "reason": "Floor cession — original speaker yielded their turn",
        }
        for iv_id, tup in reassign.items()
    ]
    write_yaml(
        CORRECTIONS_DIR / "reassignments.yml",
        reassign_list,
        header=(
            "Floor-cession re-attributions.\n"
            "When an entity yielded their speaking time to another entity,\n"
            "Claude attributes the speech to the registered entity. These entries correct that."
        ),
    )

    # ── deletions.yml ─────────────────────────────────────────────────────────
    delete_ivs = c.get("DELETE_IV_IDS", set())
    delete_eids = c.get("DELETE_ENTITY_IDS", set())
    deletions = {
        "interventions": [
            {"iv_id": iv_id, "reason": ""}
            for iv_id in sorted(delete_ivs)
        ],
        "entities": [
            {"entity_id": eid, "reason": ""}
            for eid in sorted(delete_eids)
        ],
    }
    write_yaml(
        CORRECTIONS_DIR / "deletions.yml",
        deletions,
        header=(
            "IDs to delete from the final dataset.\n"
            "interventions: Claude extracted these but they are not valid citizen interventions.\n"
            "entities: entity IDs to remove entirely."
        ),
    )

    # ── patches.yml ───────────────────────────────────────────────────────────
    patches = c.get("IV_PATCHES", {})
    patches_list = [
        {"iv_id": iv_id, "fields": fields, "reason": ""}
        for iv_id, fields in patches.items()
    ]
    write_yaml(
        CORRECTIONS_DIR / "patches.yml",
        patches_list,
        header=(
            "Field-level patches for individual interventions.\n"
            "fields: dict of field → corrected value.\n"
            "reason: what was wrong in the original Claude output."
        ),
    )

    # ── manual_interventions.yml ──────────────────────────────────────────────
    manual = c.get("MANUAL_INTERVENTIONS", [])
    for iv in manual:
        iv["source"] = "manual"
    write_yaml(
        CORRECTIONS_DIR / "manual_interventions.yml",
        manual,
        header=(
            "Interventions missed by script 05 and added manually.\n"
            "source: always 'manual' (marks them as human-curated, not from pipeline).\n"
            "If an id already exists in interventions_raw.json, the full entry replaces it."
        ),
    )

    # ── text_merges.yml ───────────────────────────────────────────────────────
    text_merges = c.get("IV_TEXT_MERGES", [])
    write_yaml(
        CORRECTIONS_DIR / "text_merges.yml",
        text_merges,
        header=(
            "Split speeches that should be concatenated into one intervention.\n"
            "base_id keeps its metadata; texts from merge_ids are appended in order.\n"
            "merge_ids are deleted after merging."
        ),
    )

    # ── new_entities.yml ──────────────────────────────────────────────────────
    ensure = c.get("ENSURE_ENTITIES", [])
    write_yaml(
        CORRECTIONS_DIR / "new_entities.yml",
        ensure,
        header=(
            "Entities to create from scratch (not via merges).\n"
            "These appear in variant_map_forced or reassignments but\n"
            "don't yet have a MERGE entry that would create the canonical entity.\n"
            "reason: why the entity needs to be explicitly created."
        ),
    )

    print(f"\nAll YAML files written to data/corrections/")
    print("Next step: rewrite apply_merges.py to read from these files.")


if __name__ == "__main__":
    main()

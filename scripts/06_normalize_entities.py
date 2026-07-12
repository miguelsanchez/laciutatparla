#!/usr/bin/env python3
"""
Script 06: Normalize entity names and build the entities catalog.
Groups variants of the same entity (typos, abbrevs, both languages).
Output: data/entitats.json
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

_api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC")
if _api_key:
    os.environ["ANTHROPIC_API_KEY"] = _api_key

import anthropic
import httpx
from slugify import slugify

INPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "entitats.json"

client = anthropic.Anthropic(http_client=httpx.Client(trust_env=False))

NORMALIZE_PROMPT = """Tens una llista d'entitats que han intervingut en plens de l'Ajuntament de València.
Algunes entitats apareixen amb variacions de nom (castellano/valencià, abreviatures, errors tipogràfics).

Agrupa les entitats que clarament són la mateixa organització i proporciona per a cada grup:
- El nom normalitzat en castellano (nom_cas)
- El nom normalitzat en valencià (nom_val)
- Un slug únic en minúscules amb guions (id)
- El tipus: av | plataforma | ong | sindical | cultural | educacio | esportiu | empresa | particular | altres

IMPORTANT: El camp "variants" ha de contenir els textos EXACTAMENT tal com apareixen a la llista
d'entrada (còpia literal, sense correccions ortogràfiques ni canvis). Cada element de la llista
d'entrada ha d'aparèixer en exactament un grup.

Entitats a normalitzar:
{entities_list}

Respon amb un JSON array:
[
  {{
    "id": "slug-unic",
    "nom_cas": "Nombre en castellano",
    "nom_val": "Nom en valencià",
    "tipus": "tipus",
    "variants": ["text exacte de la llista", "altre text exacte"]
  }}
]

Respon ÚNICAMENT amb el JSON array."""


def extract_all_entities(interventions: list[dict]) -> list[str]:
    """Get unique entity names from all interventions."""
    entities = set()
    for iv in interventions:
        entitat = iv.get("entitat")
        if entitat and entitat.strip():
            entities.add(entitat.strip())
    return sorted(entities)


def _word_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word sets."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _ensure_coverage(batch: list[str], batch_result: list[dict]) -> list[dict]:
    """Guarantee every original entity name appears in some group's variants."""
    covered = set()
    for entity in batch_result:
        for v in entity.get("variants", []):
            covered.add(v.lower().strip())
        covered.add(entity.get("nom_cas", "").lower().strip())
        covered.add(entity.get("nom_val", "").lower().strip())

    for original in batch:
        key = original.lower().strip()
        if key in covered:
            continue
        # Find best-matching group by word overlap
        best_entity = None
        best_score = 0.0
        for entity in batch_result:
            for name in [entity.get("nom_val", ""), entity.get("nom_cas", "")]:
                score = _word_similarity(original, name)
                if score > best_score:
                    best_score = score
                    best_entity = entity
        if best_entity and best_score >= 0.3:
            best_entity.setdefault("variants", []).append(original)
            covered.add(key)
            print(f"    Coverage fix: '{original}' → '{best_entity['id']}' (sim={best_score:.2f})")
        else:
            batch_result.append({
                "id": slugify(original),
                "nom_cas": original,
                "nom_val": original,
                "tipus": "altres",
                "variants": [original],
            })
            covered.add(key)
            print(f"    Coverage fix: '{original}' → standalone entry")

    return batch_result


def normalize_with_claude(entities: list[str]) -> list[dict]:
    """Use Claude to group and normalize entity names."""
    # Smaller batches reduce the chance of Claude errors
    batch_size = 30
    all_normalized = []

    for i in range(0, len(entities), batch_size):
        batch = entities[i:i + batch_size]
        entities_list = "\n".join(f"- {e}" for e in batch)

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8096,
                messages=[{"role": "user", "content": NORMALIZE_PROMPT.format(
                    entities_list=entities_list
                )}],
            )
            response_text = message.content[0].text.strip()
            response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

            try:
                batch_result = json.loads(response_text)
            except json.JSONDecodeError:
                decoder = json.JSONDecoder()
                batch_result, _ = decoder.raw_decode(response_text)

            batch_result = _ensure_coverage(batch, batch_result)
            all_normalized.extend(batch_result)
            print(f"  Batch {i//batch_size + 1}: {len(batch)} → {len(batch_result)} groups")

        except Exception as e:
            print(f"  Batch {i//batch_size + 1} ERROR: {e}")
            for entity in batch:
                all_normalized.append({
                    "id": slugify(entity),
                    "nom_cas": entity,
                    "nom_val": entity,
                    "tipus": "altres",
                    "variants": [entity],
                })

    return all_normalized


def build_variant_map(normalized: list[dict]) -> dict[str, str]:
    """Build a map from any variant name to the canonical entity ID."""
    variant_map = {}
    for entity in normalized:
        for variant in entity.get("variants", []):
            variant_map[variant.lower().strip()] = entity["id"]
        # Also map the canonical names
        variant_map[entity["nom_cas"].lower().strip()] = entity["id"]
        variant_map[entity["nom_val"].lower().strip()] = entity["id"]
    return variant_map


def main():
    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found. Run 05_parse_interventions.py first.")
        raise SystemExit(1)

    interventions = json.loads(INPUT_FILE.read_text())
    print(f"Loaded {len(interventions)} interventions")

    # Extract unique entity names
    all_entities = extract_all_entities(interventions)
    print(f"Found {len(all_entities)} unique entity names")
    for e in all_entities[:10]:
        print(f"  - {e}")
    if len(all_entities) > 10:
        print(f"  ... and {len(all_entities) - 10} more")

    # Normalize with Claude
    print("\nNormalizing entities with Claude...")
    normalized = normalize_with_claude(all_entities)

    # Ensure unique IDs (handle duplicates from batching)
    seen_ids = {}
    deduped = []
    for entity in normalized:
        base_id = entity["id"]
        if base_id in seen_ids:
            # Merge variants
            seen_ids[base_id]["variants"] = list(set(
                seen_ids[base_id].get("variants", []) + entity.get("variants", [])
            ))
        else:
            seen_ids[base_id] = entity
            deduped.append(entity)

    # Build variant map and count interventions per entity
    variant_map = build_variant_map(deduped)
    intervention_counts = defaultdict(int)
    for iv in interventions:
        entitat = (iv.get("entitat") or "").lower().strip()
        entity_id = variant_map.get(entitat, slugify(entitat))
        intervention_counts[entity_id] += 1

    # Add intervention count and sort
    for entity in deduped:
        entity["num_intervencions"] = intervention_counts.get(entity["id"], 0)

    # Remove ghost duplicates: entities with 0 interventions whose variants are
    # all mapped to a different entity (Claude created separate cas/val groups for the same entity)
    clean = []
    for entity in deduped:
        if entity["num_intervencions"] > 0:
            clean.append(entity)
            continue
        all_names = (
            entity.get("variants", []) +
            [entity.get("nom_cas", ""), entity.get("nom_val", "")]
        )
        mapped_to = {variant_map.get(n.lower().strip()) for n in all_names if n}
        mapped_to.discard(None)
        mapped_to.discard(entity["id"])
        if mapped_to:
            print(f"  Ghost duplicate removed: '{entity['id']}' (variants covered by {mapped_to})")
        else:
            clean.append(entity)
    deduped = clean

    deduped.sort(key=lambda e: -e["num_intervencions"])

    # Save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(deduped, ensure_ascii=False, indent=2))
    print(f"\nSaved {len(deduped)} normalized entities to {OUTPUT_FILE}")

    # Save variant map for use by build script
    variant_map_file = Path(__file__).parent.parent / "data" / "raw" / "entity_variant_map.json"
    variant_map_file.write_text(json.dumps(variant_map, ensure_ascii=False, indent=2))
    print(f"Saved variant map to {variant_map_file}")


if __name__ == "__main__":
    main()

"""Thematic taxonomy, scopes, entity types and CAP codebook: one source for every script.

The data lives in taxonomy.json (also read by web/src/utils/labels.ts). Before F1.1 each
script carried its own copy and they had drifted (D8): reclassify still used categories that no
longer exist, and the CAP codebook differed between 05, validate and cap_classify.

The text renderers reproduce byte for byte what 05 and cap_classify used to embed, so their
prompts did not change when the copies were removed (scripts/tests/test_taxonomy.py).
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA = json.loads((Path(__file__).with_name("taxonomy.json")).read_text(encoding="utf-8"))

TAXONOMY: dict[str, list[str]] = _DATA["categories"]
CATEGORIES: set[str] = set(TAXONOMY)
SUB_TO_CAT: dict[str, str] = {s: c for c, subs in TAXONOMY.items() for s in subs}
SUBCATEGORIES: set[str] = set(SUB_TO_CAT)
SUB_DESCRIPTIONS: dict[str, str] = _DATA["subcategory_descriptions"]
AMBITS: set[str] = set(_DATA["ambits"])
TIPUS: set[str] = set(_DATA["tipus"])
IDIOMES: set[str] = set(_DATA["idiomes"])

CAP_MAJORS: list[dict] = _DATA["cap"]["majors"]
CAP_SUBTOPICS: list[dict] = _DATA["cap"]["subtopics"]
CAP_CODES: set[int] = {s["code"] for s in CAP_SUBTOPICS}
CAP_MAJOR_CODES: set[int] = {m["code"] for m in CAP_MAJORS}


def taxonomy_text() -> str:
    """One line per category: "urbanisme: espai_public, habitatge, …" (05, backfill)."""
    return "\n".join(f"{cat}: {', '.join(subs)}" for cat, subs in TAXONOMY.items())


def taxonomy_text_described() -> str:
    """Categories with a short description per subcategory (reclassify)."""
    blocks = []
    for cat, subs in TAXONOMY.items():
        lines = [f"{cat}:"] + [f"  {s} — {SUB_DESCRIPTIONS[s]}" for s in subs]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def cap_codebook_compact() -> str:
    """The codes of the extraction prompt, one line per major topic (05, backfill)."""
    lines = []
    for m in CAP_MAJORS:
        subs = [s for s in CAP_SUBTOPICS if s["major"] == m["code"] and s["in_extraction_prompt"]]
        if subs:
            lines.append(f"{m['code']} {m['short']}: " + ", ".join(f"{s['code']} {s['short']}" for s in subs))
    return "\n".join(lines)


def cap_codebook_full() -> str:
    """Every code with its CAP name, as cap_classify embeds it."""
    parts = ["", "CODEBOOK COMPARATIVE AGENDAS PROJECT (CAP)",
             "Major topics and subtopics relevant for municipal-level politics:", ""]
    for i, m in enumerate(CAP_MAJORS):
        parts.append(f"{m['code']} {m['name']}")
        parts += [f"  {s['code']} {s['name']}" for s in CAP_SUBTOPICS if s["major"] == m["code"]]
        if i < len(CAP_MAJORS) - 1:
            parts.append("")
    return "\n".join(parts) + "\n"

"""Taxonomy: the single source (lib/taxonomy.json) and how script 05 validates against it."""

import hashlib
import json
from pathlib import Path

import pytest

from lib import taxonomy

REPO = Path(__file__).resolve().parents[2]

# sha256 of the prompts as they were before F1.1 removed the per-script copies. If you change
# taxonomy.json on purpose, the extraction prompt changes too: update the hash in the same PR.
# Changed on purpose by the language rule (no "mixt", full translations): 2026-10-18; and by the
# barrio names with their accents (Sant Marcel·lí, Camí Real…), which the prompt lists: 2026-10-21.
EXTRACTION_PROMPT_SHA256 = "a72b10fc3f740ad03e1b285b9f5ddc7b01a2a94358b3eb8865cdd4202f78cff4"
CAP_CLASSIFY_PROMPT_SHA256 = "7256e62de65f481567cf54efc0803442e845f60aed39e1efe194fb5c061dbd8d"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_extraction_prompt_unchanged(mod_05):
    assert _sha(mod_05.EXTRACTION_PROMPT) == EXTRACTION_PROMPT_SHA256


def test_cap_classify_prompt_unchanged():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cap_classify", REPO / "scripts" / "cap_classify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert _sha(mod.PROMPT) == CAP_CLASSIFY_PROMPT_SHA256


def test_every_subcategory_has_a_description():
    assert set(taxonomy.SUB_DESCRIPTIONS) == taxonomy.SUBCATEGORIES


def test_subcategories_are_unique():
    subs = [s for ss in taxonomy.TAXONOMY.values() for s in ss]
    assert len(subs) == len(set(subs))


def test_cap_codebook_is_consistent():
    codes = [s["code"] for s in taxonomy.CAP_SUBTOPICS]
    assert len(codes) == len(set(codes))
    assert {s["major"] for s in taxonomy.CAP_SUBTOPICS} <= taxonomy.CAP_MAJOR_CODES
    assert all(s["short"] for s in taxonomy.CAP_SUBTOPICS if s["in_extraction_prompt"])


@pytest.mark.parametrize("lang", ["cas", "val"])
def test_web_has_a_label_for_every_id(lang):
    strings = json.loads((REPO / "web" / "src" / "i18n" / f"{lang}.json").read_text())
    keys = ([f"cat_{c}" for c in taxonomy.CATEGORIES] + [f"sub_{s}" for s in taxonomy.SUBCATEGORIES]
            + [f"ambit_{a}" for a in taxonomy.AMBITS])
    missing = [k for k in keys if k not in strings]
    assert missing == [], f"{lang}.json lacks {missing}"


def test_valid_taxonomy_structure(mod_05):
    """All 9 categories present with at least one subcategory each."""
    expected_cats = {
        "urbanisme", "mobilitat", "medi_ambient", "serveis_publics",
        "economia", "drets_i_igualtat", "persones", "cultura", "participacio",
    }
    assert set(mod_05.VALID_TAXONOMY.keys()) == expected_cats
    for cat, subs in mod_05.VALID_TAXONOMY.items():
        assert len(subs) > 0, f"Category '{cat}' has no subcategories"


def test_valid_subs_index_covers_all_subcategories(mod_05):
    """VALID_SUBS reverse index covers every subcategory exactly once."""
    for cat, subs in mod_05.VALID_TAXONOMY.items():
        for sub in subs:
            assert sub in mod_05.VALID_SUBS, f"'{sub}' missing from VALID_SUBS"
            assert mod_05.VALID_SUBS[sub] == cat


def test_validate_temes_accepts_valid_input(mod_05):
    raw = {"urbanisme": ["habitatge", "espai_public"], "mobilitat": ["transit"]}
    result = mod_05.validate_temes(raw)
    assert result == raw


def test_validate_temes_drops_invalid_category(mod_05):
    raw = {"urbanisme": ["habitatge"], "inexistent": ["foo"]}
    result = mod_05.validate_temes(raw)
    assert "inexistent" not in result
    assert "urbanisme" in result


def test_validate_temes_drops_invalid_subcategory(mod_05):
    raw = {"urbanisme": ["habitatge", "subcategoria_falsa"]}
    result = mod_05.validate_temes(raw)
    assert "subcategoria_falsa" not in result["urbanisme"]
    assert "habitatge" in result["urbanisme"]


def test_validate_temes_promotes_subcategory_as_key(mod_05):
    """If a subcategory name is used as a category key, it gets moved to the right category."""
    raw = {"habitatge": ["espai_public"]}
    result = mod_05.validate_temes(raw)
    assert "habitatge" not in result
    assert "urbanisme" in result


def test_validate_temes_empty_input(mod_05):
    assert mod_05.validate_temes({}) == {}


def test_validate_response_valid(mod_05):
    data = {
        "temes_v2": {"urbanisme": ["habitatge"]},
        "ambit": "barri",
        "tipus_entitat": "av",
    }
    errors = mod_05.validate_response(data)
    assert errors == []


def test_validate_response_invalid_ambit(mod_05):
    data = {"temes_v2": {}, "ambit": "planeta", "tipus_entitat": "av"}
    errors = mod_05.validate_response(data)
    assert any("ambit" in e for e in errors)


def test_validate_response_invalid_tipus(mod_05):
    data = {"temes_v2": {}, "ambit": "ciutat", "tipus_entitat": "superheroi"}
    errors = mod_05.validate_response(data)
    assert any("tipus_entitat" in e for e in errors)


def test_validate_response_invalid_category(mod_05):
    data = {"temes_v2": {"politica": ["eleccions"]}, "ambit": "ciutat"}
    errors = mod_05.validate_response(data)
    assert any("temes_v2" in e for e in errors)


def test_validate_response_invalid_subcategory(mod_05):
    data = {"temes_v2": {"urbanisme": ["gratacels"]}, "ambit": "ciutat"}
    errors = mod_05.validate_response(data)
    assert any("temes_v2" in e for e in errors)


@pytest.mark.parametrize("ambit", [
    "barri", "districte", "multi_barri", "multi_districte",
    "ciutat", "area_metropolitana", "no_especificat",
])
def test_all_valid_ambits_accepted(mod_05, ambit):
    data = {"temes_v2": {}, "ambit": ambit}
    errors = mod_05.validate_response(data)
    assert not any("ambit" in e for e in errors)

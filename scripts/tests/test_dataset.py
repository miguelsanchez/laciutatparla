"""Invariant tests for the final dataset (intervencions.json + entitats.json).

Run after every data update to catch regressions before export_dataset.py.
Known issues are listed by id in meta/qa/baseline.json: those ids are tolerated,
any other id with the same problem fails. Deletions and reassignments are read
from data/corrections/*.yml, the same files apply_merges.py applies.
"""

import pytest

from lib.taxonomy import AMBITS as VALID_AMBITS  # single source (F1.1)

VALID_MANDATS = {"2011-2015", "2015-2019", "2019-2023", "2023-2027"}

# ── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def iv_by_id(intervencions):
    return {iv["id"]: iv for iv in intervencions}


@pytest.fixture(scope="module")
def entitat_ids(entitats):
    return {e["id"] for e in entitats}


# ── Volume ───────────────────────────────────────────────────────────────────

def test_intervention_count_at_least_597(intervencions):
    assert len(intervencions) >= 597


def test_entity_count_at_least_247(entitats):
    assert len(entitats) >= 247


# ── Mandatory fields ─────────────────────────────────────────────────────────

def test_all_interventions_have_required_fields(intervencions):
    required = {"id", "pleno_id", "fecha", "mandat_id", "entitat_id"}
    missing = [iv["id"] for iv in intervencions if not required.issubset(iv)]
    assert missing == [], f"Missing required fields in: {missing[:5]}"


def test_all_ids_unique(intervencions):
    ids = [iv["id"] for iv in intervencions]
    assert len(ids) == len(set(ids)), "Duplicate intervention IDs found"


# ── Mandats ──────────────────────────────────────────────────────────────────

def test_all_mandats_known(intervencions):
    unknown = {iv["mandat_id"] for iv in intervencions} - VALID_MANDATS - {"desconegut"}
    assert unknown == set(), f"Unknown mandat_id values: {unknown}"


def test_four_mandats_present(intervencions):
    mandats = {iv["mandat_id"] for iv in intervencions} & VALID_MANDATS
    assert mandats == VALID_MANDATS


# ── Entity references ─────────────────────────────────────────────────────────

def test_no_orphan_entitat_ids(intervencions, entitat_ids):
    orphans = [iv["id"] for iv in intervencions if iv.get("entitat_id") not in entitat_ids]
    assert orphans == [], f"entitat_id not in entitats.json: {orphans}"


# ── Geographic scope ─────────────────────────────────────────────────────────

def test_all_ambits_valid(intervencions):
    invalid = [
        (iv["id"], iv["ambit"])
        for iv in intervencions
        if iv.get("ambit") and iv["ambit"] not in VALID_AMBITS
    ]
    assert invalid == [], f"Invalid ambit values: {invalid[:5]}"


def test_ambit_barri_without_zones_only_baseline(intervencions, known_issue):
    bad = {iv["id"] for iv in intervencions if iv.get("ambit") == "barri" and not iv.get("zones")}
    new = bad - known_issue("ambit_barri_without_zones")
    assert new == set(), f"ambit=barri without zones (not in baseline.json): {sorted(new)}"


# ── Taxonomy ─────────────────────────────────────────────────────────────────

from lib.taxonomy import TAXONOMY as VALID_TAXONOMY  # noqa: E402  single source (F1.1)

_VALID_CATS = set(VALID_TAXONOMY)
_VALID_SUBS = {s for subs in VALID_TAXONOMY.values() for s in subs}


def test_missing_temes_v2_only_baseline(intervencions, known_issue):
    missing = {iv["id"] for iv in intervencions if not iv.get("temes_v2")}
    new = missing - known_issue("missing_temes_v2")
    assert new == set(), f"Missing temes_v2 (not in baseline.json): {sorted(new)}"


def test_temes_v2_only_valid_categories(intervencions, known_issue):
    accepted = known_issue("invalid_temes_v2")
    invalid = [
        (iv["id"], cat)
        for iv in intervencions
        if iv["id"] not in accepted
        for cat in iv.get("temes_v2", {})
        if cat not in _VALID_CATS
    ]
    assert invalid == [], f"Invalid temes_v2 categories: {invalid[:5]}"


def test_temes_v2_only_valid_subcategories(intervencions, known_issue):
    accepted = known_issue("invalid_temes_v2")
    invalid = [
        (iv["id"], cat, sub)
        for iv in intervencions
        if iv["id"] not in accepted
        for cat, subs in iv.get("temes_v2", {}).items()
        for sub in subs
        if sub not in _VALID_SUBS
    ]
    assert invalid == [], f"Invalid temes_v2 subcategories: {invalid[:5]}"


# ── apply_merges.py correctness ───────────────────────────────────────────────

def test_deletions_yaml_not_empty(deletions):
    assert deletions.get("interventions"), "deletions.yml has no interventions"


def test_deleted_ids_not_in_dataset(intervencions, deletions):
    deleted = {str(d["iv_id"]) for d in deletions.get("interventions") or []}
    present = {iv["id"] for iv in intervencions} & deleted
    assert present == set(), f"Deleted interventions reappeared: {present}"


@pytest.mark.derived
def test_reassignments_target_existing_interventions(iv_by_id, reassignments):
    """A reassignment whose iv_id vanished (e.g. a pleno id rename) silently stops applying."""
    missing = [str(r["iv_id"]) for r in reassignments if str(r["iv_id"]) not in iv_by_id]
    assert missing == [], f"reassignments.yml points at unknown iv_ids: {missing}"


@pytest.mark.derived
def test_reassignments_applied(iv_by_id, reassignments):
    for r in reassignments:
        iv_id = str(r["iv_id"])
        if iv_id not in iv_by_id or "entitat_id" not in r:
            continue
        actual = iv_by_id[iv_id].get("entitat_id")
        assert actual == r["entitat_id"], (
            f"{iv_id}: expected entitat_id='{r['entitat_id']}', got '{actual}'"
        )


# ── Dates ────────────────────────────────────────────────────────────────────

def test_all_dates_parseable(intervencions):
    from datetime import date
    bad = []
    for iv in intervencions:
        try:
            date.fromisoformat(iv["fecha"])
        except (ValueError, TypeError):
            bad.append((iv["id"], iv.get("fecha")))
    assert bad == [], f"Unparseable dates: {bad[:5]}"


def test_all_dates_within_covered_range(intervencions):
    from datetime import date
    start = date(2011, 1, 1)
    end = date(2027, 12, 31)
    out_of_range = [
        iv["id"] for iv in intervencions
        if not (start <= date.fromisoformat(iv["fecha"]) <= end)
    ]
    assert out_of_range == [], f"Dates out of mandate range: {out_of_range}"

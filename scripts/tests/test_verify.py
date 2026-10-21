"""verify_proposals.py (arquitectura-agentes §3.3, F2.2), on real acta fragments.

The fixture quote comes from data/raw/texts/2021-04-29.txt, where pdftotext left a dash at a line
end inside the speech of 2021-04-29-005 (Col·lectiu Lambda):

    ... però quan la zitzània -la cizaña, en castellano-
                       infecta un espai s’acaba havent de votar ...
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from qa import verify_proposals as V  # noqa: E402

DATA = ROOT / "data"
ACTA = "data/raw/texts/2021-04-29.txt"
IV = "2021-04-29-005"

needs_data = pytest.mark.skipif(not (DATA / "raw/texts/2021-04-29.txt").exists(), reason="data/ not present")


def prop(quote, subject=IV, entry=None, file="patches.yml", section=None, **kw):
    return {"fp": f"TEST-{abs(hash((quote, subject))) % 10**10:010d}", "check": "TEST", "severity": "P2",
            "subject": subject, "title": "test proposal", "message": "",
            "evidence": {"file": kw.pop("evidence_file", ACTA), "quote": quote},
            "file": file, "section": section,
            "entry": entry or {"iv_id": subject, "fields": {"idioma_original": "valenciano"}}, **kw}


# ── normalisation, no data needed ────────────────────────────────────────────

def test_split_word_across_lines_matches_joined_quote():
    acta = V.forms("la plataforma veï-\n                      nal del barri", source=True)
    assert V.quote_in("la plataforma veïnal del barri", acta)
    assert V.quote_in("la plataforma veï- nal del barri", acta)


def test_dash_at_line_end_matches_both_readings():
    acta = V.forms("la zitzània -la cizaña, en castellano-\n          infecta un espai", source=True)
    assert V.quote_in("la cizaña, en castellano- infecta un espai", acta)
    assert V.quote_in("la cizaña, en castellano-infecta un espai", acta)


def test_typographic_quotes_dashes_and_case():
    acta = V.forms("Diu: “No volem   més\ncotxes” — i s’acaba", source=True)
    assert V.quote_in('diu: "no volem més cotxes" - i s\'acaba', acta)


def test_dash_and_space_inside_a_line_match_as_written():
    """2012-12-28 (AMPA Teodor Llorente): «–algo menos de 2.000 euros- por falta de respuesta»."""
    acta = V.forms("del comedor –algo menos de 2.000 euros- por falta de\nrespuesta", source=True)
    assert V.quote_in("–algo menos de 2.000 euros- por falta de respuesta", acta)


def test_a_sentence_across_a_page_header_is_found():
    page = "\n\nSESIÓN ORDINARIA DE 28 DE DICIEMBRE DE 2012\n\nACTA DE PLE\n\n"
    text = ("Primera página." + page + "Sigue el acta. El salón de actos no tiene salida antipánico "
            "a pesar de tener un aforo de más" + page + "de 300 personas." + page + "RESPOSTA\nFin.")
    acta = V.acta_forms(text)
    assert V.quote_in("a pesar de tener un aforo de más de 300 personas.", acta)
    assert V.quote_in("ACTA DE PLE", acta)             # the acta as it is still matches
    assert not V.quote_in("más de 300 personas. Primera", acta)


def test_no_accent_folding_and_no_fuzzy_match():
    acta = V.forms("una societat democràtica", source=True)
    assert not V.quote_in("una societat democratica", acta)
    assert not V.quote_in("una societat democràtiques", acta)


# ── the five gates on the real data ──────────────────────────────────────────

@pytest.fixture
def verifier(data_without_patches):
    # the proposals below patch real interventions: a real patch for them would make N7 reject
    # every one as a duplicate, so the verifier reads a copy of data/ without those patches
    v = V.Verifier(data_without_patches(IV, "2026-07-23-005"))
    yield v
    v.close()


@needs_data
@pytest.mark.slow
def test_real_quote_with_line_end_dash_is_accepted(verifier):
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai s’acaba havent de votar")
    assert verifier.verify(p) is None


@needs_data
def test_translated_quote_is_rejected(verifier):
    p = prop("pero cuando la cizaña infecta un espacio se acaba teniendo que votar")
    assert verifier.verify(p).startswith("idioma:")


@needs_data
def test_invented_quote_is_rejected(verifier):
    p = prop("quan la zitzània infecta tots els espais de la ciutat")
    assert verifier.verify(p) == "quote: not found in the acta"


@needs_data
def test_short_or_missing_quote_is_rejected(verifier):
    assert verifier.verify(prop("la zitzània")).startswith("quote: missing")
    assert verifier.verify(prop(None)).startswith("quote: missing")


@needs_data
def test_quote_from_another_acta_is_rejected(verifier):
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai", subject="2026-07-23-005",
             entry={"iv_id": "2026-07-23-005", "fields": {"idioma_original": "valenciano"}})
    assert "evidence is from 2021-04-29" in verifier.verify(p)


@needs_data
def test_invented_intervention_id_is_rejected(verifier):
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai", subject="2021-04-29-099",
             entry={"iv_id": "2021-04-29-099", "fields": {"idioma_original": "valenciano"}})
    assert verifier.verify(p) == "ids: intervention '2021-04-29-099' does not exist"


@needs_data
def test_invented_entity_id_is_rejected(verifier):
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai", file="reassignments.yml",
             entry={"iv_id": IV, "entitat": "Col·lectiu Inventat", "entitat_id": "collectiu-inventat"})
    assert verifier.verify(p).startswith("ids: entity 'collectiu-inventat'")


@needs_data
@pytest.mark.slow
def test_bad_field_value_is_rejected_by_c1_in_the_dry_run(verifier):
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai",
             entry={"iv_id": IV, "fields": {"tipus_entitat": "partit"}})
    assert verifier.verify(p).startswith("N7: ")        # N7 checks tipus_entitat before the dry run
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai",
             entry={"iv_id": IV, "fields": {"ambit": "planeta"}})
    assert verifier.verify(p).startswith("dry-run: C1 ")


@needs_data
def test_n7_rejects_a_duplicate_entry(verifier):
    existing = (verifier.ctx.corrections("reassignments.yml") or [])[0]
    p = prop("quan la zitzània -la cizaña, en castellano- infecta un espai", file="reassignments.yml",
             subject=existing["iv_id"], entry=dict(existing),
             evidence_file=f"data/raw/texts/{verifier.iv(existing['iv_id'])['pleno_id']}.txt")
    p["evidence"]["quote"] = None
    assert verifier.check_n7(p)[0].startswith("N7:")


def test_overlay_is_writable_when_the_data_dir_is_read_only(tmp_path):
    """Backtests run on a chmod a-w copy of data/; the second backtest crashed on it."""
    d = tmp_path / "data"
    (d / "corrections").mkdir(parents=True)
    (d / "corrections" / "patches.yml").write_text("[]\n")
    (d / "corrections" / "patches.yml").chmod(0o444)
    v = V.Verifier(d)
    try:
        target = v._overlay() / "corrections" / "patches.yml"
        target.write_text("- iv_id: x\n")   # raises PermissionError if the mode was copied
        assert v._snapshot()["patches.yml"] == b"- iv_id: x\n"
    finally:
        v.close()


BARBA_QUOTE = "José Antonio Barba Guillem (AV Nazaret Unido-FAVV)"
BARBA_TEXT = ("Me llamo José Antonio Barba, soy vecino de Natzaret y hablo en nombre de cientos de "
              "familias que llevan más de 30 años esperando que alguien desde su despacho en Madrid se "
              "acuerde de que existimos Natzaret y La Punta, que también está perjudicada con lo de "
              "Serrería. Vengo aquí sin protocolo ni tecnicismo.")
# 2026-04-30-101 itself was recovered for real (PR #63): the backtest needs an id that does not exist.
MISSED = {"fp": "TEST-missed", "check": "E1b", "severity": "P1", "subject": "2026-04-30-199",
          "title": "missed speaker", "message": "",
          "evidence": {"file": "data/raw/texts/2026-04-30.txt", "quote": BARBA_QUOTE},
          "file": "manual_interventions.yml", "section": None,
          "entry": {"id": "2026-04-30-199", "pleno_id": "2026-04-30", "ordre": 199,
                    "intervinient": "José Antonio Barba Guillem", "entitat": "AV Golden Test Nova",
                    "tipus_entitat": "av", "idioma_original": "castellano",
                    "text_original": BARBA_TEXT}}
NEW_ENTITY = {**MISSED, "fp": "TEST-entity", "check": "N6", "subject": "av-golden-test-nova",
              "file": "new_entities.yml",
              "entry": {"id": "av-golden-test-nova", "nom_cas": "AV Golden Test Nueva",
                        "nom_val": "AV Golden Test Nova", "tipus": "av"}}


@pytest.mark.skipif(not (DATA / "raw/texts/2026-04-30.txt").exists(), reason="data/ not present")
@pytest.mark.slow
def test_missed_speaker_with_a_new_entity_needs_both_proposals():
    """Backtest B: a manual intervention for an entity not in the catalog is an orphan alone,
    and passes when the batch also proposes the entity (checked first, whatever the order)."""
    accepted, rejected = V.verify_all([MISSED], DATA)
    assert not accepted and "orphaned" in rejected[0]["reason"]
    accepted, rejected = V.verify_all([MISSED, NEW_ENTITY], DATA)
    assert rejected == [] and {p["fp"] for p in accepted} == {"TEST-missed", "TEST-entity"}


@pytest.mark.skipif(not (DATA / "raw/texts/2026-04-30.txt").exists(), reason="data/ not present")
@pytest.mark.slow
def test_a_rejected_proposal_is_rolled_back():
    bad_entity = {**NEW_ENTITY, "entry": {**NEW_ENTITY["entry"], "tipus": "partit"}}   # N7: invalid tipus
    accepted, rejected = V.verify_all([bad_entity, MISSED], DATA)
    assert accepted == [] and len(rejected) == 2


@pytest.mark.skipif(not (DATA / "raw/texts/2026-04-30.txt").exists(), reason="data/ not present")
def test_an_invented_speech_is_rejected_even_with_a_good_quote(verifier):
    invented = {**MISSED, "entry": {**MISSED["entry"], "text_original":
                BARBA_TEXT + " Exigimos que el Ayuntamiento construya un puerto deportivo en la "
                "Punta antes de que acabe el año. También queremos un tranvía hasta Pinedo que "
                "salga cada cinco minutos. Y un parque nuevo con lago en el antiguo cauce del río."}}
    assert verifier.check_quote(invented).startswith("text: only 2 of 5 sentences")
    assert verifier.check_quote(MISSED) is None


@pytest.mark.skipif(not (DATA / "raw/texts/2026-04-30.txt").exists(), reason="data/ not present")
def test_new_entity_like_an_existing_one_gets_a_warning():
    """Backtest B proposed av-el-palmar while the catalog has av-del-palmar."""
    palmar = {**NEW_ENTITY, "subject": "av-el-palmar",
              "entry": {"id": "av-el-palmar", "nom_cas": "Asociación de Vecinos de El Palmar",
                        "nom_val": "Associació de Veïns del Palmar", "tipus": "av"}}
    v = V.Verifier(DATA)
    try:
        assert any("av-del-palmar" in w for w in v.warnings(palmar))
        assert v.warnings(NEW_ENTITY) == []
    finally:
        v.close()


@pytest.mark.slow
@pytest.mark.skipif(not (DATA / "raw/texts/2026-04-30.txt").exists(), reason="data/ not present")
def test_replace_without_an_existing_entry_becomes_append():
    patch = {**MISSED, "fp": "TEST-replace", "check": "C6", "subject": "2026-04-30-001", "op": "replace",
             "file": "patches.yml", "entry": {"iv_id": "2026-04-30-001", "fields": {"ambit": "ciutat", "zones": []}}}
    accepted, rejected = V.verify_all([patch], DATA)
    assert rejected == [] and accepted[0]["op"] == "append"


@pytest.mark.slow
@pytest.mark.skipif(not (DATA / "raw/texts/2026-04-30.txt").exists(), reason="data/ not present")
def test_append_to_an_intervention_that_has_a_patch_becomes_replace():
    """The 20-pleno sample lost 5 proposals for 2024-09-16-1: 'an entry … already exists'.
    2026-04-30-005 already has a patch (its resum_cas)."""
    iv = next(i for i in json.loads((DATA / "intervencions.json").read_text()) if i["id"] == "2026-04-30-005")
    patch = {**MISSED, "fp": "TEST-append", "check": "C6", "subject": "2026-04-30-005", "op": "append",
             "file": "patches.yml", "entry": {"iv_id": "2026-04-30-005", "fields": {"temes_v2": iv["temes_v2"]}}}
    accepted, rejected = V.verify_all([patch], DATA)
    assert rejected == [] and accepted[0]["op"] == "replace"


@needs_data
@pytest.mark.slow
def test_cli_writes_accepted_and_never_touches_data(tmp_path, data_without_patches):
    data = data_without_patches(IV)
    good = prop("quan la zitzània -la cizaña, en castellano- infecta un espai s’acaba havent de votar")
    bad = prop("pero cuando la cizaña infecta un espacio se acaba teniendo que votar")
    (tmp_path / "in.json").write_text(json.dumps([good, bad]))
    corrections_before = {p.name: p.read_bytes() for p in (data / "corrections").glob("*.yml")}
    V.main(["--input", str(tmp_path / "in.json"), "--output", str(tmp_path / "out.json"), "--no-state",
            "--data-dir", str(data)])
    out = json.loads((tmp_path / "out.json").read_text())
    assert [p["fp"] for p in out] == [good["fp"]]
    assert {p.name: p.read_bytes() for p in (data / "corrections").glob("*.yml")} == corrections_before

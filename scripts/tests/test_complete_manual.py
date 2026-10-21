"""complete_manual.py: fill what script 05 would have produced, never the reviewed fields. No API."""

import json
import subprocess
import types
from pathlib import Path

import pytest
import yaml

from qa import complete_manual as CM
from qa import proposals as P

ENTRY = {"id": "2026-01-01-101", "pleno_id": "2026-01-01", "ordre": 101, "intervinient": "Joan Garcia",
         "entitat": "AV Nova", "tipus_entitat": "av", "idioma_original": "valenciano",
         "text_original": "Bon dia. Demanem que s'arregle la vorera del carrer major.",
         "reason": "missed speaker", "date": "2026-10-17"}
EXTRACTED = {"text_original": "TEXT REWRITTEN BY THE MODEL", "intervinient": "Other", "entitat": "Other",
             "text_cas": "Buenos días. Pedimos que se **arregle la acera**.",
             "text_val": "Bon dia. Demanem que s'**arregle la vorera**.",
             "resum_cas": "Pide arreglar la acera.", "resum_val": "Demana arreglar la vorera.",
             "temes_v2": {"urbanisme": ["espai_public"]}, "ambit": "ciutat", "zones": [], "districtes": [],
             "cap_major": [14], "cap_subtopics": [1400], "idioma_original": "castellano"}


@pytest.fixture
def wt(tmp_path, monkeypatch):
    root = tmp_path / "lcp-qa"
    (root / "data/corrections").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / "data/corrections/manual_interventions.yml").write_text(P.render_entry(ENTRY))
    (root / "data/raw/sessions_index.json").write_text(json.dumps([{"id": "2026-01-01"}]))
    (root / "data/raw/interventions_raw.json").write_text("[]")
    (root / "data/intervencions.json").write_text("[]")
    (root / "data/entitats.json").write_text("[]")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null", "-C", str(root)]
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    monkeypatch.setenv("LCP_QA_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"), ("GIT_COMMITTER_NAME", "t"),
                 ("GIT_COMMITTER_EMAIL", "t@t"), ("GIT_CONFIG_COUNT", "1"),
                 ("GIT_CONFIG_KEY_0", "core.hooksPath"), ("GIT_CONFIG_VALUE_0", "/dev/null")):
        monkeypatch.setenv(k, v)
    return root


def entries(wt):
    return yaml.safe_load((wt / "data/corrections/manual_interventions.yml").read_text())


def test_incomplete_and_block():
    assert CM.incomplete([ENTRY]) == [ENTRY]
    assert CM.incomplete([{**ENTRY, **{f: EXTRACTED[f] for f in CM.REQUIRED}}]) == []
    # enriched in interventions_raw.json already (the 22 older manual ones): never touched
    assert CM.incomplete([ENTRY], {ENTRY["id"]: {f: EXTRACTED[f] for f in CM.REQUIRED}}) == []
    assert CM.block_for(ENTRY) == "Joan Garcia (AV Nova):\n“Bon dia. Demanem que s'arregle la vorera del carrer major.”"


def test_complete_fills_only_missing_and_keeps_the_reviewed_fields():
    new = CM.complete(ENTRY, EXTRACTED)
    assert new["text_original"] == ENTRY["text_original"]
    assert (new["intervinient"], new["entitat"]) == ("Joan Garcia", "AV Nova")
    assert new["idioma_original"] == "valenciano"            # present: not overwritten
    assert new["text_cas"] == EXTRACTED["text_cas"] and new["cap_subtopics"] == [1400]
    assert new["reason"] == "missed speaker"


def test_published_values_are_never_replaced():
    """An older manual intervention with an empty translation but a published classification:
    only the translation is filled."""
    raw = {"temes_v2": {"cultura": ["festes"]}, "ambit": "barri", "zones": ["Russafa"], "text_cas": ""}
    new = CM.complete(ENTRY, EXTRACTED, raw)
    assert new["text_cas"] == EXTRACTED["text_cas"]
    assert "temes_v2" not in new and "ambit" not in new and "zones" not in new


def test_dry_run_calls_nothing(wt, monkeypatch, capsys):
    monkeypatch.setattr(CM, "load_script", lambda name: pytest.fail("no API call in a dry run"))
    assert CM.main(["--worktree", str(wt), "--dry-run"]) == 0
    assert "2026-01-01-101" in capsys.readouterr().out
    assert entries(wt) == [ENTRY]


def test_run_rewrites_the_entry_and_commits(wt, monkeypatch):
    calls = []
    fake = types.SimpleNamespace(parse_block_with_claude=lambda bloc, sid, idx: calls.append(bloc) or dict(EXTRACTED))
    monkeypatch.setattr(CM, "load_script", lambda name: fake)
    assert CM.main(["--worktree", str(wt), "--commit"]) == 0
    assert len(calls) == 1 and "Joan Garcia (AV Nova)" in calls[0]
    [e] = entries(wt)
    assert e["text_original"] == ENTRY["text_original"] and e["resum_val"] == EXTRACTED["resum_val"]
    assert e["temes_v2"] == {"urbanisme": ["espai_public"]}
    log = subprocess.run(["git", "-C", str(wt), "log", "--format=%s"], capture_output=True, text=True).stdout
    assert log.splitlines()[0] == "qa: complete manual intervention 2026-01-01-101 (script 05 extraction)"
    # a second run has nothing left to do
    assert CM.main(["--worktree", str(wt), "--commit"]) == 0 and len(calls) == 1


CAS_SPEECH = ("Buenos días. Venimos en representación de los vecinos del barrio para pedir que el "
              "Ayuntamiento arregle las aceras, porque están rotas y son un peligro para las personas "
              "mayores y para los niños. También queremos más árboles en la plaza. Muchas gracias.")
VAL_SPEECH = ("Bon dia. Venim en representació dels veïns del barri per a demanar que l'Ajuntament "
              "arregle les voreres, perquè estan trencades i són un perill per a les persones majors i "
              "per als xiquets. També volem més arbres a la plaça. Moltes gràcies.")


def test_language_rule_sets_idioma_empties_the_original_and_retranslates():
    calls = []

    def translate(text, target):
        calls.append(target)
        return VAL_SPEECH, [], {}
    # 2026-04-30-102: a castellano speech whose text_val came back in castellano
    entry = {**ENTRY, "idioma_original": "mixt", "text_original": CAS_SPEECH,
             "text_cas": CAS_SPEECH.replace("Buenos", "Buenas"), "text_val": CAS_SPEECH}
    new, why = CM.language_rule(entry, translate)
    assert why is None and calls == ["valenciano"]
    assert (new["idioma_original"], new["text_cas"], new["text_val"]) == ("castellano", "", VAL_SPEECH)
    # a good translation is kept: no API call
    new, why = CM.language_rule({**entry, "text_val": VAL_SPEECH}, translate)
    assert why is None and calls == ["valenciano"] and new["text_val"] == VAL_SPEECH


def test_language_rule_refuses_when_the_translation_stays_wrong():
    entry = {**ENTRY, "text_original": CAS_SPEECH, "text_val": CAS_SPEECH}
    new, why = CM.language_rule(entry, lambda text, target: ("", ["refused"], {}))
    assert "retranslation failed (refused)" in why


def test_run_does_not_write_an_entry_that_breaks_the_language_rule(wt, monkeypatch):
    entry = {**ENTRY, "text_original": CAS_SPEECH, "idioma_original": "castellano"}
    (wt / "data/corrections/manual_interventions.yml").write_text(P.render_entry(entry))
    untranslated = {**EXTRACTED, "text_cas": "", "text_val": CAS_SPEECH}   # script 05 left it in castellano
    fake = types.SimpleNamespace(parse_block_with_claude=lambda *a: dict(untranslated))
    monkeypatch.setattr(CM, "load_script", lambda name: fake)
    from qa import retranslate
    monkeypatch.setattr(retranslate, "_client", lambda: object())
    monkeypatch.setattr(retranslate, "translate", lambda client, text, target: ("", ["cut at max_tokens"], {}))
    assert CM.main(["--worktree", str(wt), "--commit"]) == 1
    assert entries(wt) == [entry]


# ── what script 05 got wrong on lone speeches (PRs #90, #95) ──

BARRIS = Path(__file__).resolve().parents[2] / "data/raw/barris_referencia.json"
needs_barris = pytest.mark.skipif(not BARRIS.exists(), reason="data/ not present")


@needs_barris
def test_geography_is_tidied_as_script_07_and_c3_expect():
    ref = json.loads(BARRIS.read_text())
    # 2023-01-26-101: district prefixes
    new, notes = CM.tidy_geography({"ambit": "multi_barri", "zones": ["L'Eixample > El Pla Del Remei",
                                    "L'Eixample > La Gran Via"], "districtes": ["L'Eixample"]}, ref)
    assert new["zones"] == ["El Pla del Remei", "La Gran Via"] and notes == []
    # 2014-03-28-102: ambit ciutat with zones, one of them not a barrio
    new, notes = CM.tidy_geography({"ambit": "ciutat", "zones": ["Horno de Alcedo", "Castellar-l'Oliveral"],
                                    "districtes": ["Poblats del Sud"]}, ref)
    assert (new["zones"], new["districtes"]) == ([], [])
    assert any("Horno de Alcedo" in n for n in notes) and any("ambit ciutat" in n for n in notes)
    # a barri ambit with nothing left is reported, not guessed
    new, notes = CM.tidy_geography({"ambit": "barri", "zones": ["Barri Inventat"]}, ref)
    assert new["zones"] == [] and any("without a barrio" in n for n in notes)


def test_censored_names_are_written_as_script_05_does():
    """PR #100: the acta's ****** read as three bold markers."""
    entry = {"intervinient": "[***]", "ordre": 2, "text_original": "Soy ****** y vengo por la **visita**.",
             "text_val": "Sóc ****** i vinc per la **visita**, amb [***].", "reason": "missed ******"}
    new = CM.anonymise(entry)
    assert new["text_original"] == "Soy [***] y vengo por la **visita**."
    assert new["text_val"] == "Sóc [***] i vinc per la **visita**, amb [***]."
    assert (new["intervinient"], new["ordre"], new["reason"]) == ("[***]", 2, "missed ******")


def test_a_paragraph_left_in_the_original_language_is_reported():
    """2012-12-28-101: the start of a paragraph of text_val stayed in castellano."""
    entry = {"idioma_original": "castellano",
             "text_original": "Muchas gracias.\n\nSimplemente queremos acompañarles en una visita guiada por un edificio.",
             "text_val": "Moltes gràcies.\n\nSimplemente queremos acompañarles en una **visita guiada** per un edifici."}
    assert CM.untranslated_starts(entry) == ["Simplemente queremos acompañarles en una **visita guiada** per un edifici."]
    entry["text_val"] = "Moltes gràcies.\n\nSimplement volem acompanyar-los en una **visita guiada** per un edifici."
    assert CM.untranslated_starts(entry) == []

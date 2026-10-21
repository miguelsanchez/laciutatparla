"""F2.3–F2.4 candidate checks on fixture data dirs: E1b, E2, E5, E6, N2, N4, C4.

The backtests against old data/ (git archive <sha>^ data/) are in the PR description; these
tests pin the behaviour on small fixtures, plus one real acta for E1b.
"""

import json
import shutil
from pathlib import Path

import pytest

from qa import run_checks as rc
from qa.model import REGISTRY, Context

rc.load_checks()

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    for sub in ("raw/texts", "corrections"):
        (d / sub).mkdir(parents=True)
    return d


def write(d, rel, obj):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))


def run(check_id, d):
    return list(REGISTRY[check_id].fn(Context(d, repo_root=d.parent)))


SPEECH = ("Bon dia a totes i tots. Venim en representació del veïnat del barri per demanar que "
          "l'Ajuntament arregle les voreres del carrer major, que fa anys que estan trencades i "
          "són un perill per a les persones majors i per als xiquets que van a l'escola cada dia. "
          "També demanem més arbres a la plaça. "
          "Moltes gràcies.")


# ── E1b ──

@pytest.mark.skipif(not (ROOT / "data/raw/texts/2026-06-30.txt").exists(), reason="data/ not present")
def test_e1b_flags_the_june_2026_splitter_bug(data):
    """2026-06-30 has 15 speakers; the buggy splitter (before ec7845b) extracted fewer."""
    shutil.copy(ROOT / "data/raw/texts/2026-06-30.txt", data / "raw/texts/2026-06-30.txt")
    real = [iv for iv in json.loads((ROOT / "data/raw/interventions_raw.json").read_text())
            if iv["pleno_id"] == "2026-06-30"]
    assert len(real) == 15
    write(data, "raw/interventions_raw.json", real)
    assert run("E1b", data) == []
    write(data, "raw/interventions_raw.json", real[:8])
    [f] = run("E1b", data)
    assert (f.subject, f.key) == ("2026-06-30", "8/15")


def test_e1b_ignores_officials_and_page_noise(data):
    acta = ("INTERVENCIONS CIUTADANES\n"
            "Intervé la Sra. Maria Pérez Soler, en representació de l'AV Benimaclet, qui diu:\n"
            "\"Bon dia\"\n"
            "         Joan Garcia Mira (Plataforma per l'Horta)\n"
            "\"Bon dia\"\n"
            "Sra. Presidenta (Alcaldessa de València)\n"
            "CÒPIA INFORMATIVA (NO VERIFICABLE EN SEU ELECTRÒNICA)\n")
    write(data, "raw/texts/2026-01-01.txt", acta)
    write(data, "raw/interventions_raw.json", [{"id": "2026-01-01-001", "pleno_id": "2026-01-01"}])
    [f] = run("E1b", data)
    assert f.key == "1/2" and f.details["speakers"] == ["joan garcia", "maria perez"]


# ── E2 ──

def test_e2_finds_a_truncated_copy_under_another_pleno_id(data):
    write(data, "raw/interventions_raw.json", [
        {"id": "2022-12-22-001", "pleno_id": "2022-12-22", "text_original": SPEECH},
        {"id": "2022-12-22-1-001", "pleno_id": "2022-12-22-1", "text_original": SPEECH[:250]},
        {"id": "2022-12-22-1-002", "pleno_id": "2022-12-22-1",
         "text_original": "Una altra intervenció completament diferent sobre el transport públic, "
                          "els autobusos de l'EMT, les freqüències de pas i les parades del barri. " * 2},
    ])
    [f] = run("E2", data)
    assert f.subject == "2022-12-22-001|2022-12-22-1-001" and "different plenos" in f.message


def test_e2_ignores_short_texts(data):
    write(data, "raw/interventions_raw.json", [
        {"id": "a", "pleno_id": "p", "text_original": "Moltes gràcies a tots per escoltar-nos."},
        {"id": "b", "pleno_id": "q", "text_original": "Moltes gràcies a tots per escoltar-nos."},
    ])
    assert run("E2", data) == []


# ── E5 ──

def test_e5_mayor_office_and_party(data):
    write(data, "mandats.json", [{"id": "2023-2027", "inici": "2023-06-17", "fi": None,
                                  "alcalde": "María José Catalá Verdet"}])
    write(data, "raw/interventions_raw.json", [
        {"id": "1", "pleno_id": "p", "fecha": "2024-01-01", "intervinient": "Mª José Catalá", "entitat": "x"},
        {"id": "2", "pleno_id": "p", "fecha": "2024-01-01", "intervinient": "María José Catalá Verdet", "entitat": "x"},
        {"id": "3", "pleno_id": "p", "fecha": "2024-01-01", "intervinient": "Sr. regidor Juan López", "entitat": "x"},
        {"id": "4", "pleno_id": "p", "fecha": "2024-01-01", "intervinient": "Ana Gil", "entitat": "Grup Municipal Vox"},
        {"id": "5", "pleno_id": "p", "fecha": "2024-01-01", "intervinient": "José Catalá", "entitat": "AV Russafa"},
    ])
    assert {f.subject for f in run("E5", data)} == {"2", "3", "4"}


# ── E6 ──

def test_e6_no_final_punctuation_but_thanks_is_fine(data):
    write(data, "raw/interventions_raw.json", [
        {"id": "a", "pleno_id": "p", "text_original": "Demanem que s'arregle la vorera del carrer"},
        {"id": "b", "pleno_id": "p", "text_original": "Demanem que s'arregle la vorera.\n\nGràcies"},
        {"id": "c", "pleno_id": "p", "text_original": "Demanem que s'arregle la **vorera**.**"},
    ])
    assert [(f.subject, f.key) for f in run("E6", data)] == [("a", "no-final-punctuation")]


# ── N2 / N4 ──

def _ent(id, cas, val=None, tipus="av"):
    return {"id": id, "nom_cas": cas, "nom_val": val or cas, "tipus": tipus, "variants": []}


def test_n2_merged_entity_and_spelling_variants(data):
    write(data, "entitats.json", [
        _ent("cear-cepaim", "Comisión Española de Ayuda al Refugiado (CEAR) i Fundación CEPAIM", tipus="ong"),
        _ent("fundacio-cepaim", "Fundación CEPAIM", "Fundació CEPAIM", tipus="ong"),
        _ent("av-torrefiel", "AV Torrefiel"),
        _ent("asociacion-vecinos-torrefiel", "Asociación de Vecinos de Torrefiel", "Associació de Veïns de Torrefiel"),
        _ent("av-benimaclet", "Asociación de Vecinos de Benimaclet", "Associació de Veïns de Benimaclet"),
        _ent("ampa-ceip-a", "AMPA CEIP Rafael Altamira", tipus="educacio"),
        _ent("ampa-ceip-b", "AMPA CEIP Cavite", tipus="educacio"),
    ])
    assert {f.subject for f in run("N2", data)} == {
        "cear-cepaim|fundacio-cepaim", "asociacion-vecinos-torrefiel|av-torrefiel"}


def test_n4_tipus_vs_name(data):
    write(data, "entitats.json", [
        _ent("ok", "Asociación de Vecinos de Patraix"),
        _ent("bad-av", "AV Malilla", tipus="cultural"),
        _ent("bad-ampa", "AMPA CEIP 103", tipus="av"),
        _ent("trans", "Chrysallis, Asociación de Familias de Infancia Trans", tipus="ong"),
    ])
    assert {f.subject for f in run("N4", data)} == {"bad-av", "bad-ampa"}


# ── C4 ──

CAS = ("Buenos días. Venimos en representación de los vecinos del barrio para pedir que el "
       "Ayuntamiento arregle las aceras, porque están rotas y son un peligro para las personas "
       "mayores y para los niños. También queremos más árboles en la plaza. Muchas gracias.")


def _iv(id, original, idioma="castellano", **kw):
    """A castellano record shaped like interventions_raw.json: text_cas empty, script 07 fills it."""
    return {"id": id, "pleno_id": "p", "idioma_original": idioma, "text_original": original,
            "text_cas": "", "text_val": "", **kw}


def c4(data, ivs):
    write(data, "raw/interventions_raw.json", ivs)
    return {(f.subject, f.key): f for f in run("C4", data)}


def test_c4_ratio_bold_and_paragraphs(data):
    got = c4(data, [
        _iv("ok", CAS, text_cas=CAS, text_val=SPEECH),
        _iv("cut", CAS, text_cas=CAS, text_val=SPEECH[:120]),
        _iv("bold", "**" + CAS + "**", text_cas="**" + CAS + "**", text_val=SPEECH),
        _iv("paras", CAS + "\n\nOtra cosa más.", text_cas=CAS + "\n\nOtra cosa más.", text_val=SPEECH),
    ])
    assert ("cut", "length-ratio") in got
    assert ("bold", "bold") in got
    assert ("paras", "paragraphs") in got
    assert not any(s == "ok" for s, _ in got)


def test_c4_paragraph_majority_weighted_by_length():
    from qa.checks.classification import language_profile, majority_language
    short_val = "Bon dia a totes i tots, moltes gràcies."
    assert majority_language(short_val + "\n" + CAS) == "castellano"
    assert majority_language(CAS + "\n" + SPEECH) == "valenciano"   # SPEECH is the longer one
    prof = language_profile(short_val + "\n" + CAS)
    assert prof["castellano"] == len(CAS) and prof["valenciano"] == len(short_val)
    assert majority_language("Gracias.") is None                   # too short to tell


def test_c4_a_long_block_is_measured_by_sentences():
    """A one-paragraph speech is cut at sentence boundaries, like script 07's paragraphize()."""
    from qa.checks.classification import majority_language, paragraphs
    block = " ".join([CAS] * 3 + [SPEECH] * 4)
    assert len(paragraphs(block)) > 1
    assert majority_language(block) == "valenciano"


def test_c4_idioma_follows_the_majority_and_mixt_goes(data):
    got = c4(data, [
        _iv("mixt-cas", CAS + "\nBon dia a totes i tots, moltes gràcies.", idioma="mixt",
            text_cas=CAS, text_val=SPEECH),
        _iv("wrong", SPEECH, idioma="castellano", text_val="", text_cas=CAS),
        _iv("ok-val", SPEECH, idioma="valenciano", text_cas=CAS),
    ])
    assert got["mixt-cas", "idioma"].details["idioma"] == "castellano"
    assert got["wrong", "idioma"].details == {"pleno_id": "p", "idioma": "valenciano",
                                              "was": "castellano", "share": 1.0}
    assert not any(s == "ok-val" for s, _ in got)


def test_c4_original_text_must_be_text_original_verbatim(data):
    mixed = CAS + "\nBon dia a totes i tots, moltes gràcies."
    got = c4(data, [
        # mixt → castellano: text_cas is a translation of the Valencian bit, not the original
        _iv("mixt", mixed, idioma="mixt", text_cas=CAS + "\nBuenos días a todos, muchas gracias.",
            text_val=SPEECH),
        _iv("condensed", CAS, text_cas=CAS[:90], text_val=SPEECH),
        _iv("same", mixed, text_cas=mixed.replace("\n", "\n\n"), text_val=SPEECH),  # spacing only
    ])
    assert ("mixt", "original-text_cas") in got
    assert ("condensed", "original-text_cas") in got
    assert ("same", "original-text_cas") not in got
    # the Valencian paragraph of a castellano speech stays in text_cas: it is the original
    assert ("same", "untranslated-text_cas") not in got


def test_c4_untranslated_paragraphs_in_the_translation(data):
    greeting = "Buenos días, alcaldesa. Buenos días a todos."
    long_val = "\n".join([SPEECH] * 4)
    got = c4(data, [
        _iv("whole", CAS, text_val=CAS),                                    # text_val never translated
        _iv("empty", CAS),                                                  # falls back to text_original
        _iv("greeting", greeting + "\n" + CAS * 4, text_val=greeting + "\n" + long_val),
        _iv("ok", CAS, text_val=SPEECH),
    ])
    assert got["whole", "untranslated-text_val"].severity == "P1"
    assert got["whole", "untranslated-text_val"].details["share"] == 1.0
    assert ("empty", "untranslated-text_val") in got
    g = got["greeting", "untranslated-text_val"]
    assert g.severity == "P2" and g.details["paragraphs"] == 1
    assert not any(s == "ok" for s, _ in got)

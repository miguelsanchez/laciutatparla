"""F0b checks on fixture data dirs: S2, E3, E4, N1, N7, C1, C3, C7, G4."""

import json

import pytest

from qa import run_checks as rc
from qa.model import REGISTRY, Context

rc.load_checks()


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    for sub in ("raw/texts", "raw/pdfs", "corrections", "plenos"):
        (d / sub).mkdir(parents=True)
    return d


def write(d, rel, obj):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def run(check_id, d, repo_root=None):
    return list(REGISTRY[check_id].fn(Context(d, repo_root=repo_root or d.parent)))


def test_e3_orphan_pleno_file_via_data_dir(data, tmp_path, monkeypatch):
    write(data, "plenos.json", [{"id": "2026-01-01"}])
    write(data, "plenos/2026-01-01.json", {})
    write(data, "plenos/fake.json", {})
    monkeypatch.setenv("LCP_QA_STATE", str(tmp_path / "state"))
    assert rc.main(["--only", "E3", "--data-dir", str(data), "--no-state", "--strict"]) == 1
    assert [f.subject for f in run("E3", data)] == ["fake"]


def test_e4_and_n1(data):
    write(data, "raw/sessions_metadata.json", [{"id": "2026-01-01"}])
    write(data, "entitats.json", [{"id": "av-x"}])
    write(data, "intervencions.json", [
        {"id": "a", "pleno_id": "2026-01-01", "entitat_id": "av-x"},
        {"id": "b", "pleno_id": "2099-01-01", "entitat_id": "ghost"},
    ])
    write(data, "raw/entity_variant_map.json", {"av x": "av-x"})
    write(data, "raw/interventions_raw.json", [{"id": "a", "entitat": "AV X"}, {"id": "b", "entitat": "Nova"}])
    assert [f.subject for f in run("E4", data)] == ["b"]
    assert {(f.subject, f.severity) for f in run("N1", data)} == {("b", "P0"), ("b", "P1")}


def test_s2(data):
    write(data, "raw/sessions_index.json", [{"id": "s1"}, {"id": "s2"}])
    write(data, "raw/sessions_metadata.json", [{"id": "s1", "acta_disponible": True},
                                               {"id": "s2", "acta_disponible": False}])
    write(data, "raw/pdfs/s3.pdf", "%PDF-")
    assert {(f.subject, f.key) for f in run("S2", data)} == {("s1", "no-pdf"), ("s3", "no-text")}


def test_s2_skips_a_checkout_without_pdfs(data):
    """propose.py --sparse makes a QA worktree without data/raw/pdfs: nothing is "not downloaded"."""
    write(data, "raw/sessions_index.json", [{"id": "s1"}])
    write(data, "raw/sessions_metadata.json", [{"id": "s1", "acta_disponible": True}])
    (data / "raw/pdfs").rmdir()
    assert run("S2", data) == []


def test_n7_new_entity_used_by_a_manual_intervention_is_pending_not_stale(data):
    """A new entity is not in entitats.json until apply_merges runs: it must not block the
    proposal that creates it (the F2.9 backtest's AFA CEIP Alejandra Soler)."""
    _n7_base(data)
    write(data, "corrections/manual_interventions.yml",
          "- id: '2026-01-01-101'\n  pleno_id: '2026-01-01'\n  entitat: AFA CEIP Nova\n  text_original: x\n"
          "  reason: missed\n  date: '2026-10-17'\n")
    write(data, "corrections/new_entities.yml",
          "- id: afa-ceip-nova\n  nom_cas: AFA CEIP Nova\n  nom_val: AFA CEIP Nova\n  tipus: educacio\n"
          "  reason: new\n  date: '2026-10-17'\n- id: nobody-uses-me\n  nom_cas: X\n  nom_val: X\n  tipus: altres\n"
          "  reason: new\n  date: '2026-10-17'\n")
    got = {(f.subject, f.key) for f in run("N7", data)}
    assert ("new_entities.yml|afa-ceip-nova", "stale:id") not in got
    assert ("new_entities.yml|nobody-uses-me", "stale:id") in got


def _n7_base(data):
    write(data, "raw/sessions_index.json", [{"id": "2026-01-01"}])
    write(data, "raw/interventions_raw.json", [{"id": "2026-01-01-001"}])
    write(data, "intervencions.json", [{"id": "2026-01-01-001"}])
    write(data, "entitats.json", [{"id": "av-x"}])


def test_n7_invented_iv_id_is_an_error(data):
    _n7_base(data)
    write(data, "corrections/patches.yml",
          "- iv_id: '2026-01-01-999'\n  fields: {entitat: X}\n  reason: test\n  date: '2026-10-17'\n")
    got = {(f.severity, f.key) for f in run("N7", data)}
    assert ("P1", "ref:iv_id") in got


def test_n7_unquoted_date_duplicate_and_missing_reason(data):
    _n7_base(data)
    write(data, "corrections/skip_plenos.yml",
          "- pleno_id: 2026-01-01\n  reason: x\n- pleno_id: '2026-01-01'\n  reason: ''\n")
    got = {f.key for f in run("N7", data)}
    assert {"type:pleno_id", "duplicate", "missing:reason", "date"} <= got


def test_n7_broken_yaml(data):
    _n7_base(data)
    write(data, "corrections/patches.yml", "- iv_id: [unclosed\n")
    assert [(f.severity, f.key) for f in run("N7", data)] == [("P0", "yaml")]


def test_n7_legacy_entries_exempt_from_reason(data):
    _n7_base(data)
    write(data, "corrections/patches.yml", "- iv_id: '2026-01-01-001'\n  fields: {entitat: X}\n  reason: ''\n")
    write(data.parent, "meta/qa/n7_legacy.json", {"patches.yml": ["2026-01-01-001"]})
    assert run("N7", data) == []


def test_n7_invalid_language_and_tipus_in_new_interventions(data):
    """PR #90: an agent wrote idioma_original 'valencià'; the rule allows only valenciano/castellano."""
    _n7_base(data)
    write(data, "corrections/manual_interventions.yml",
          "- id: '2026-01-01-101'\n  pleno_id: '2026-01-01'\n  entitat: X\n  text_original: x\n"
          "  idioma_original: valencià\n  tipus_entitat: joventut\n  reason: missed\n  date: '2026-10-19'\n"
          "- id: '2026-01-01-102'\n  pleno_id: '2026-01-01'\n  entitat: X\n  text_original: x\n"
          "  idioma_original: mixt\n  reason: missed\n  date: '2026-10-19'\n")
    write(data, "corrections/patches.yml",
          "- iv_id: '2026-01-01-102'\n  fields: {idioma_original: castellano}\n  reason: rule\n  date: '2026-10-19'\n")
    got = {(f.subject, f.key) for f in run("N7", data)}
    assert ("manual_interventions.yml|2026-01-01-101", "idioma") in got
    assert ("manual_interventions.yml|2026-01-01-101", "tipus") in got
    assert ("manual_interventions.yml|2026-01-01-102", "idioma") not in got   # its patch sets it


def test_n7_clean_new_entry(data):
    _n7_base(data)
    write(data, "corrections/reassignments.yml",
          "- iv_id: '2026-01-01-001'\n  entitat: X\n  entitat_id: av-x\n  reason: cesión\n  date: '2026-10-17'\n")
    assert run("N7", data) == []


def test_c3_and_c7(data):
    write(data, "raw/barris_referencia.json", [{"nom": "Russafa", "districte_nom": "L'Eixample"}])
    write(data, "mandats.json", [{"id": "2023-2027", "inici": "2023-06-17", "fi": None}])
    write(data, "intervencions.json", [
        {"id": "a", "ambit": "barri", "zones": [], "mandat_id": "2023-2027", "fecha": "2024-01-01"},
        {"id": "b", "ambit": "ciutat", "zones": ["Russafa"], "mandat_id": "desconegut", "fecha": "2011-01-01"},
        {"id": "c", "ambit": "barri", "zones": ["Inventat"], "mandat_id": "2023-2027", "fecha": "2020-01-01"},
    ])
    assert {(f.subject, f.key) for f in run("C3", data)} == {
        ("a", "barri-no-zones"), ("b", "ciutat-with-zones"), ("c", "zone:Inventat")}
    assert {f.subject for f in run("C7", data)} == {"b", "c"}


def test_c1_reports_validate_errors(data):
    write(data, "raw/interventions_raw.json", [
        {"id": "a", "ambit": "planeta", "text_original": "x" * 60},
        {"id": "b", "ambit": "ciutat", "text_original": "**una" + "x" * 60},
    ])
    got = {(f.subject, f.key.split(" ")[0]) for f in run("C1", data)}
    assert ("a", "ambit") in got and ("b", "número") in got


def test_c1_bold_count_skips_anonymised_names(data):
    """[***] is a censored name, not a bold marker; the acta's ****** still counts (PR #100)."""
    write(data, "raw/interventions_raw.json", [
        {"id": "a", "ambit": "ciutat", "text_original": "Soy [***] y vengo por la **visita**. " + "x" * 60},
        {"id": "b", "ambit": "ciutat", "text_original": "Soy ****** y vengo por la **visita**. " + "x" * 60},
    ])
    odd = {f.subject for f in run("C1", data) if f.key.startswith("número impar")}
    assert odd == {"b"}


def test_g4_counts(data, tmp_path):
    write(data, "intervencions.json", [{"id": "a"}, {"id": "b"}])
    write(data, "entitats.json", [{"id": "x"}])
    pub = tmp_path / "web/public/datos"
    write(pub, "intervencions.json", [{"id": "a"}])
    write(pub, "intervencions_light.json", [{"id": "a"}, {"id": "b"}])
    write(pub, "intervencions_metadata.csv", "id\na\nb\n")
    write(pub, "entitats.json", [{"id": "x"}])
    assert [f.subject for f in run("G4", data, repo_root=tmp_path)] == ["intervencions.json"]


# ── F3: G2 (figures typed into the source) and G3 (cas/val parity) on a fixture site ──

def _site(tmp_path, cas_src, cas_html, val_html=None):
    import os, time
    root = tmp_path / "site"
    data = root / "data"
    data.mkdir(parents=True)
    write(data, "intervencions.json", [])
    write(data, "entitats.json", [])
    page = root / "web/src/pages/[lang]/datos"
    page.mkdir(parents=True)
    (page / "index.astro").write_text(cas_src)
    for lang, body in (("cas", cas_html), ("val", val_html if val_html is not None else cas_html)):
        d = root / "web/dist" / lang / ("datos" if lang == "cas" else "dades")
        d.mkdir(parents=True)
        (d / "index.html").write_text(f"<html><body><p>{body}</p></body></html>")
        (root / "web/dist" / lang / "index.html").write_text("<html></html>")
    future = time.time() + 10  # the build is newer than data/
    for f in (root / "web/dist").rglob("*.html"):
        os.utime(f, (future, future))
    return data, root


def test_g2_flags_a_literal_figure(tmp_path):
    data, root = _site(tmp_path, "<p>Hay 581 intervenciones en total</p>", "Hay 581 intervenciones en total")
    got = list(REGISTRY["G2"].fn(Context(data, repo_root=root)))
    assert [f.key for f in got] == ["Hay 581 intervenciones"]


def test_g2_accepts_a_computed_figure(tmp_path):
    data, root = _site(tmp_path, "<p>Hay {stats.interventions} intervenciones en total</p>", "Hay 597 intervenciones en total")
    assert list(REGISTRY["G2"].fn(Context(data, repo_root=root))) == []


def test_g2_ignores_css_and_skips_a_stale_build(tmp_path):
    data, root = _site(tmp_path, '<p style="width: 21%">el {x}%</p>', "el 21 %")
    assert list(REGISTRY["G2"].fn(Context(data, repo_root=root))) == []
    (data / "intervencions.json").write_text("[]")  # data newer than the build: nothing to scan
    import os, time
    os.utime(data / "intervencions.json", (time.time() + 60, time.time() + 60))
    data2, root2 = _site(tmp_path / "b", "<p>Hay 581 intervenciones</p>", "Hay 581 intervenciones")
    os.utime(data2 / "intervencions.json", (time.time() + 60, time.time() + 60))
    assert list(REGISTRY["G2"].fn(Context(data2, repo_root=root2))) == []


def test_g3_flags_a_figure_in_one_language_only(tmp_path):
    data, root = _site(tmp_path, "", "597 intervenciones, 278 entidades", "597 intervencions, 276 entitats")
    got = {(f.subject, f.key) for f in REGISTRY["G3"].fn(Context(data, repo_root=root))}
    assert got == {("datos|278", "cas only"), ("datos|276", "val only")}

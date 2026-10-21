"""Each sentinel check fires on a small fixture data dir (--data-dir), and stays quiet on clean data."""

import json

import pytest

from qa import run_checks as rc
from qa.model import REGISTRY, Context

rc.load_checks()

HEADER = "INTERVENCIONS CIUTADANES\n"
ACTA = "ACTA - PLE\nSESSIÓ ORDINÀRIA PLE DEL DIA 1 DE GENER DE 2026\n" + "text " * 600


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    for sub in ("raw/texts", "raw/pdfs", "corrections"):
        (d / sub).mkdir(parents=True)
    (d / "corrections/skip_plenos.yml").write_text("- pleno_id: '2026-01-03'\n  reason: test\n")
    return d


def write(d, rel, content):
    p = d / rel
    p.write_text(content) if isinstance(content, str) else p.write_bytes(content)


def findings(check_id, d):
    return list(REGISTRY[check_id].fn(Context(d)))


def test_e1_fewer_extracted_than_blocks(data):
    write(data, "raw/texts/2026-01-01.txt", HEADER + "x" * 600 + HEADER + "y" * 600 + HEADER)
    write(data, "raw/interventions_raw.json", json.dumps([{"pleno_id": "2026-01-01"}] * 2))
    [f] = findings("E1", data)
    assert f.subject == "2026-01-01" and f.key == "2/3"


def test_e9_header_without_interventions(data):
    write(data, "raw/texts/2026-01-02.txt", ACTA + HEADER)
    write(data, "raw/texts/2026-01-03.txt", ACTA + HEADER)  # in skip_plenos
    write(data, "raw/texts/2026-01-04.txt", ACTA)  # no header
    write(data, "raw/interventions_raw.json", "[]")
    assert [f.subject for f in findings("E9", data)] == ["2026-01-02"]


def test_s7(data):
    write(data, "raw/pdfs/2026-01-01.pdf", b"<html>not a pdf")
    write(data, "raw/pdfs/2026-01-02.pdf", b"%PDF-1.4 fake")
    write(data, "raw/texts/2026-01-02.txt", "ORDRE DEL DIA\nPLE\n" + "x " * 2000)
    write(data, "raw/pdfs/2026-01-03.pdf", b"%PDF-1.4 fake")
    write(data, "raw/texts/2026-01-03.txt", "ACTA - PLE\nshort")
    got = {(f.subject, f.key) for f in findings("S7", data)}
    assert ("2026-01-01", "magic") in got
    assert ("2026-01-02", "wrong-doc") in got
    assert ("2026-01-03", "short") in got


def test_c5_empty_fields(data):
    iv = {"id": "2026-01-01-001", "pleno_id": "2026-01-01", "text_cas": "a", "text_val": " ",
          "resum_cas": "a", "resum_val": "a", "temes_v2": {}, "entitat": "X"}
    write(data, "intervencions.json", json.dumps([iv]))
    assert {f.key for f in findings("C5", data)} == {"text_val", "temes_v2"}


def test_clean_fixture_is_quiet(data):
    write(data, "raw/texts/2026-01-01.txt", ACTA + HEADER)
    write(data, "raw/interventions_raw.json", json.dumps([{"pleno_id": "2026-01-01"}]))
    for cid in ("E1", "E9", "C5"):
        assert findings(cid, data) == [], cid


def test_g1_hardcoded_and_external_figures(data, tmp_path):
    root = tmp_path
    page = root / "web/src/pages/[lang]/datos"
    page.mkdir(parents=True)
    (page / "index.astro").write_text(
        "{ n: '581', label: 'intervenciones' }\n581 intervenciones, {stats.entities} entidades\n"
        "Cabanyal lidera con 42 menciones · ×4.8\n<b>12 temas</b> (87.000 registros)")
    (root / "scripts/qa").mkdir(parents=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "data/q.json").write_text('{"total": 87528}')
    (root / "scripts/qa/figures.yml").write_text(
        "- id: q\n  value: 87528\n  check: {json: data/q.json, path: total}\n  where:\n"
        "    - {file: 'web/src/pages/[lang]/datos/index.astro', pattern: '\\((\\d[\\d.]*) registros'}\n")
    got = {(f.subject.split("|")[1], f.key) for f in REGISTRY["G1"].fn(Context(data, repo_root=root))}
    assert ("card", "581") in got and ("count", "581") in got
    assert ("barri", "42") in got and ("ratio", "×4") in got
    assert ("q", "87000") in got  # page drifted from figures.yml
    assert not any(k == "card" and v == "12" for k, v in got)


def test_s1_offline(data, monkeypatch):
    from qa.checks import extraction, sources

    class FakeCrawler:
        @staticmethod
        def crawl_recent_sessions(years_back=1):
            return {"2099-01-01": {"id": "2099-01-01", "tipo": "ordinaria", "url_web": "u"}}

        @staticmethod
        def fetch_html(url):
            return None

    class FakeSessions:
        @staticmethod
        def extract_pdf_urls(soup, sid):
            return {"url_acta": "https://example/acta.pdf"}

    monkeypatch.setattr(extraction, "_check_new_sessions", lambda: FakeCrawler)
    monkeypatch.setattr("qa.model.load_script", lambda name: FakeSessions)
    write(data, "raw/sessions_index.json", json.dumps([{"id": "2098-12-01"}]))
    ctx = Context(data, memory={"s1_index_size": 5})
    got = {(f.subject, f.key) for f in sources.s1_new_sessions(ctx)}
    assert ("sessions_index", "5->1") in got
    assert ("2099-01-01", "new-session") in got
    assert ("2099-01-01", "acta-published") in got

"""check_derived.py: derived data that does not reflect data/corrections/ turns red."""

import json
import shutil
from pathlib import Path

import pytest

from qa import check_derived as CD

DATA = Path(__file__).resolve().parents[2] / "data"
IV = {"id": "2026-01-01-001", "pleno_id": "2026-01-01", "ordre": 1, "intervinient": "Joan", "entitat": "AV Nova",
      "idioma_original": "valenciano", "resum_cas": "r", "resum_val": "r", "temes_v2": {"urbanisme": ["espai_public"]},
      "ambit": "ciutat", "cap_major": [14], "cap_subtopics": [1400], "text_cas": "a", "text_val": "b"}


def _write(d: Path, raw, final):
    (d / "raw").mkdir(parents=True)
    (d / "raw/interventions_raw.json").write_text(json.dumps(raw))
    (d / "intervencions.json").write_text(json.dumps(final))


def test_stale_final(tmp_path):
    # 07 transforms texts: only the verbatim fields count
    _write(tmp_path / "ok", [IV], [{**IV, "text_cas": "<p>a</p>", "entitat_id": "av-nova"}])
    assert CD.stale_final(tmp_path / "ok") == []
    _write(tmp_path / "behind", [IV, {**IV, "id": "2026-01-01-101"}], [{**IV, "ambit": "barri"}])
    problems = CD.stale_final(tmp_path / "behind")
    assert any("lacks 2026-01-01-101" in p for p in problems)
    assert any("differs" in p and "2026-01-01-001" in p for p in problems)


@pytest.fixture
def data_copy(tmp_path):
    dst = tmp_path / "data"
    shutil.copytree(DATA, dst, ignore=shutil.ignore_patterns("pdfs", "texts"))
    return dst


@pytest.mark.slow
def test_repo_data_reflects_its_corrections():
    assert CD.unapplied(DATA) + CD.stale_final(DATA) == []


@pytest.mark.slow
def test_a_correction_not_applied_is_caught(data_copy):
    iv_id = json.loads((data_copy / "raw/interventions_raw.json").read_text())[0]["id"]
    deletions = data_copy / "corrections/deletions.yml"
    text = deletions.read_text()
    assert "interventions:" in text
    deletions.write_text(text.replace("interventions:\n", f"interventions:\n- iv_id: {iv_id}\n  reason: test\n", 1))
    assert any(f"should be gone {iv_id}" in p for p in CD.unapplied(data_copy))
    assert CD.main(["--data-dir", str(data_copy)]) == 1

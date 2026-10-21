"""retranslate.py: the checks on a translation and the patches it proposes (no API)."""

from qa import retranslate as R
from qa.model import Finding

CAS = ("Buenos días. Venimos en representación de los **vecinos del barrio** para pedir que el "
       "Ayuntamiento arregle las aceras, porque están rotas y son un peligro para las personas mayores.")
VAL = ("Bon dia. Venim en representació dels **veïns del barri** per a demanar que l'Ajuntament "
       "arregle les voreres, perquè estan trencades i són un perill per a les persones majors.")


def test_problems_accepts_a_faithful_translation():
    assert R.problems(CAS, VAL, "valenciano") == []


def test_problems_catches_what_breaks_the_rule():
    assert any("not in Valencian" in p for p in R.problems(CAS, CAS, "valenciano"))
    assert any("** markers" in p for p in R.problems(CAS, VAL.replace("**", ""), "valenciano"))
    assert any("paragraphs" in p for p in R.problems(CAS, VAL + "\n\nBon dia a tots i totes.", "valenciano"))
    assert any("length" in p for p in R.problems(CAS, VAL[:60] + "**", "valenciano"))
    assert any("preface" in p for p in R.problems(CAS, "Here is the translation: " + VAL, "valenciano"))


def _item(iv_id, **kw):
    f = Finding(check="C4", severity="P1", subject=iv_id, key="idioma", message="m",
                details={"idioma": "castellano"})
    iv = {"id": iv_id, "pleno_id": "p", "idioma_original": "mixt", "text_original": CAS}
    return {"iv": iv, "findings": [f], "lang": "castellano", "idioma": True, "original": "text_cas",
            "translate": "text_val", **kw}


def test_proposals_merge_into_an_existing_patch_and_need_the_translation(tmp_path):
    R.cache_path(tmp_path, "a", "text_val").write_text(
        '{"source_sha256": "%s", "text": "%s", "problems": []}' % (R._sha(CAS), VAL.replace('"', '\\"')))
    patches = [{"iv_id": "a", "fields": {"intervinient": "X"}, "reason": "", "date": "2026-01-01"}]
    props, missing = R.proposals({"a": _item("a"), "b": _item("b")}, tmp_path, patches)
    assert missing == ["b"]                        # no cached translation: left out, not half-fixed
    (p,) = props
    assert p["op"] == "replace" and p["check"] == "C4"
    assert p["entry"]["fields"] == {"intervinient": "X", "idioma_original": "castellano",
                                    "text_cas": "", "text_val": VAL}
    assert "date" not in p["entry"] and p["entry"]["reason"].startswith("Language rule (C4)")


def test_a_changed_source_invalidates_the_cache(tmp_path):
    R.cache_path(tmp_path, "a", "text_val").write_text('{"source_sha256": "old", "text": "x", "problems": []}')
    assert R.cached(tmp_path, "a", "text_val", CAS) is None

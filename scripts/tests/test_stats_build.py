"""The figures in the built site (web/dist) match data/, in cas and val (F0b.8).

The expected values are recomputed here in Python, independently of web/src/utils/stats.ts,
so a wrong formula in stats.ts fails too. Skipped when web/dist does not exist or
is older than data/ (a stale build cannot be checked: rebuild it). /publish builds first.
"""

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
DIST = REPO / "web" / "dist"
MANDATS = ["2011-2015", "2015-2019", "2019-2023", "2023-2027"]
ENV_TERMS = ["medi_ambient", "contaminacio", "zones_verdes", "emergencies_climatiques",
             "dana_2024", "benestar_animal"]

def _dist_state() -> str | None:
    """Why the built site cannot be checked against data/, or None if it can."""
    index = DIST / "cas" / "index.html"
    if not index.exists():
        return "web/dist not built (cd web && npm run build)"
    newest_data = max(p.stat().st_mtime for p in (DATA / "intervencions.json", DATA / "entitats.json"))
    if index.stat().st_mtime < newest_data:
        return "web/dist is older than data/: rebuild it (cd web && npm run build)"
    return None


pytestmark = pytest.mark.skipif(_dist_state() is not None, reason=_dist_state() or "")


@pytest.fixture(scope="module")
def expected():
    ivs = json.loads((DATA / "intervencions.json").read_text())
    ents = json.loads((DATA / "entitats.json").read_text())
    meta = {m["id"]: m for m in json.loads((DATA / "mandats.json").read_text())}
    today = date.today()

    def years(mid):
        a = date.fromisoformat(meta[mid]["inici"])
        b = date.fromisoformat(meta[mid]["fi"]) if meta[mid]["fi"] else today
        return min(4, max((b - a).days / 365.25, 0.25))

    by = {m: [iv for iv in ivs if iv["mandat_id"] == m] for m in MANDATS}
    env = {m: sum(any(t in json.dumps(iv.get("temes_v2") or {}) for t in ENV_TERMS) for iv in by[m])
           for m in MANDATS}
    per_year = {m: len(by[m]) / years(m) for m in MANDATS}
    seen = defaultdict(set)
    for iv in ivs:
        if iv.get("entitat_id") and iv["mandat_id"] in MANDATS:
            seen[iv["entitat_id"]].add(iv["mandat_id"])
    zones = defaultdict(int)
    for iv in ivs:
        for z in set(iv.get("zones") or []):
            zones[z] += 1
    top_name, top_count = max(zones.items(), key=lambda kv: kv[1])
    yrs = [int(iv["fecha"][:4]) for iv in ivs]
    return {
        "interventions": len(ivs),
        "entities": len(ents),
        "all_mandats": sum(1 for s in seen.values() if len(s) == 4),
        "per_year_ratio": f"×{per_year['2023-2027'] / per_year['2011-2015']:.1f}",
        "env_ratio": f"×{env['2023-2027'] / env['2011-2015']:.1f}",
        "top_name": top_name,
        "top_count": top_count,
        "span": max(yrs) - min(yrs),
        "first_year": min(yrs),
        "last_year": max(yrs),
    }


def html_raw(rel: str) -> str:
    return (DIST / rel / "index.html").read_text(encoding="utf-8")


def page(rel: str) -> str:
    html = (DIST / rel / "index.html").read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", re.sub(r"<!--.*?-->", "", html, flags=re.S))


PAIRS = [("cas", "analisis", "intervenciones ciudadanas en", "mandatos y", "años"),
         ("val", "analisi", "intervencions ciutadanes en", "mandats i", "anys")]


@pytest.mark.parametrize("lang,slug,iv_words,mand_words,years_word", PAIRS)
def test_analisis_hero_and_cards(expected, lang, slug, iv_words, mand_words, years_word):
    html = page(f"{lang}/{slug}")
    e = expected
    assert f"{e['interventions']} {iv_words} 4 {mand_words} {e['span']} {years_word}" in html
    for value in (e["per_year_ratio"], e["env_ratio"]):
        assert value in html, value
    assert f">{e['all_mandats']}</span>" in html
    assert f">{e['top_count']}</span>" in html
    assert re.search(rf"{re.escape(e['top_name'])} lidera (con|amb) {e['top_count']} men", html)


@pytest.mark.parametrize("lang", ["cas", "val"])
def test_home_insights(expected, lang):
    html = page(lang)
    e = expected
    for value in (e["per_year_ratio"], e["env_ratio"]):
        assert value in html, value
    assert f">{e['all_mandats']}<" in html and f">{e['top_count']}<" in html


@pytest.mark.parametrize("lang,slug,iv,ent", [("cas", "datos", "intervenciones", "entidades"),
                                              ("val", "dades", "intervencions", "entitats")])
def test_datos_figures(expected, lang, slug, iv, ent):
    html = page(f"{lang}/{slug}")
    e = expected
    assert f"{e['interventions']} {iv}, {e['entities']} {ent}, 4" in html  # meta description
    assert f"{e['first_year']}–{e['last_year']}" in html
    assert f"de {e['entities']} {ent}" in html or f"les {e['entities']} {ent}" in html


@pytest.mark.parametrize("lang,slug,iv", [("cas", "otras-voces", "intervenciones"),
                                          ("val", "altres-veus", "intervencions")])
def test_otras_voces_channel(expected, lang, slug, iv):
    html = page(f"{lang}/{slug}")
    assert re.search(rf'<span class="tab-sub"[^>]*>{expected["interventions"]} {iv}</span>', html)
    assert f"{iv} · {expected['first_year']}-{expected['last_year']}" in html


@pytest.mark.parametrize("rel", ["cas", "val", "cas/analisis", "val/analisi", "cas/datos",
                                 "val/dades", "cas/otras-voces", "val/altres-veus"])
def test_cas_and_val_agree(expected, rel):
    """G3: the same figures in both languages (each page checked against data/)."""
    html = page(rel)
    assert str(expected["interventions"]) in html


# ── F3: components, metodologia and la-ciutat ────────────────────────────────

@pytest.fixture(scope="module")
def f3():
    pp = json.loads((DATA / "presupuestos_oficial.json").read_text())
    barris = json.loads((DATA / "raw/barris_referencia.json").read_text())
    b2d = {b["nom"]: b["districte_nom"] for b in barris}
    ivs = json.loads((DATA / "intervencions.json").read_text())
    quejas_years = [int(y) for y in json.loads((DATA / "quejas.json").read_text())["years"]]
    eds = list(pp["_meta"]["ediciones"].values())
    budgets = (int(eds[0][:4]), 2000 + int(eds[-1][-2:]))
    iv_years = (min(int(i["fecha"][:4]) for i in ivs), max(int(i["fecha"][:4]) for i in ivs))
    iv_budgets = (max(iv_years[0], budgets[0]), min(iv_years[1], budgets[1]))
    top, series = max(pp["participantes_por_distrito"].items(), key=lambda kv: kv[1]["pct_pob_16"])

    def mentions(district, period):
        """Local-scope interventions about the district (city-wide ones naming it in passing excluded)."""
        n = 0
        for i in ivs:
            if not period[0] <= int(i["fecha"][:4]) <= period[1]:
                continue
            if i.get("ambit") not in ("barri", "districte", "multi_barri"):
                continue
            ds = set(i.get("districtes") or []) | {b2d[z] for z in i.get("zones") or [] if z in b2d}
            n += district in ds
        return n

    tax = json.loads((REPO / "scripts/lib/taxonomy.json").read_text())["categories"]
    fu = pp["funnel_propuestas"]
    last = max(fu, key=int)
    return {
        "top": top, "top_pct": round(series["pct_pob_16"]),
        "ratio": f"{series['pct_pob_16'] / pp['headline']['pct_pob_16_mas']:.1f}".replace(".", ","),
        "top_ivs": mentions(top, iv_budgets), "iv_budgets": iv_budgets,
        "all_three_from": max(iv_years[0], budgets[0], min(quejas_years)),
        "top_barris": sum(1 for b in barris if b["districte_nom"] == top),
        "top_barris_data": sum(1 for b in pp["participantes_por_barri"] if b2d.get(b) == top),
        "sel_last": fu[last]["seleccionadas"]["total"],
        "categories": len(tax), "subcategories": sum(len(v) for v in tax.values()),
        "vuln": len(json.loads((DATA / "vulnerabilidad.json").read_text())),
    }


@pytest.mark.parametrize("lang,slug,phrase", [("cas", "otras-voces", "solo {n} intervenciones de ámbito local"),
                                              ("val", "altres-veus", "només {n} intervencions d'àmbit local")])
def test_poblats_del_nord_card(f3, lang, slug, phrase):
    html = page(f"{lang}/{slug}")
    assert f"{f3['top']} acumula un {f3['top_pct']}%" in html
    assert phrase.format(n=f3["top_ivs"]) in html
    assert "Pobles del Nord" not in html and "1 intervención en 7 años" not in html


def test_presupuestos_explorer_figures(f3):
    html = page("cas/otras-voces")
    assert f"→ {f3['sel_last']})" in html                      # ed. 8 selected (was a typed 248)
    assert f"Son {f3['top_barris']} barrios pequeños" in html   # was "7 barrios"
    if f3["top_barris_data"] < f3["top_barris"]:                # the budget data covers fewer: say so
        assert f"({f3['top_barris_data']} con datos de presupuestos)" in html
    assert f"{f3['ratio']} veces la media de la ciudad" in html


def test_cross_b_narrative_uses_its_overlap(f3):
    html = page("cas/otras-voces")
    assert f"solo {f3['top_ivs']} intervenciones de ámbito local tratan asuntos de sus barrios entre {f3['iv_budgets'][0]} y {f3['iv_budgets'][1]}" in html
    assert "por cada 10.000 habitantes, la" not in html
    # Table C renders only in the browser: check the period the page hands to the island
    assert re.search(rf'periodC&quot;:\[0,\{{&quot;from&quot;:\[0,{f3["all_three_from"]}\]', html_raw("cas/otras-voces"))


@pytest.mark.parametrize("lang,cat", [("cas", "categorías y"), ("val", "categories i")])
def test_metodologia_counts(f3, expected, lang, cat):
    html = page(f"{lang}/metodologia")
    assert f"({f3['categories']} {cat} {f3['subcategories']} subcategor" in html
    assert "30+ subcategor" not in html


def test_la_ciutat_counts(f3):
    html = page("cas/la-ciutat")
    assert f"({f3['vuln']} barrios)" in html
    assert "(2019-2026)" not in html

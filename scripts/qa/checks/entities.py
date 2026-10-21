"""Entity checks (§7)."""

from __future__ import annotations

from qa.model import Context, Finding, check


@check("N1", family="entities", title="entitat_id not in catalog, or resolved by the slugify() fallback",
       fast=True)
def n1_unresolved_entities(ctx: Context):
    catalog = {e["id"] for e in ctx.entitats}
    for iv in ctx.intervencions:
        if iv.get("entitat_id") not in catalog:
            yield Finding(check="N1", severity="P0", subject=iv["id"], key=str(iv.get("entitat_id")),
                          message=f"entitat_id {iv.get('entitat_id')!r} has no entity in entitats.json "
                                  "(broken link on the web)")
    # Script 07 falls back to slugify(entitat) when the text is not in the variant map (D10):
    # the id then looks fine but is a guess that nothing reviewed.
    variant_map = ctx._json("raw/entity_variant_map.json") or {}
    if not variant_map:
        return
    for iv in ctx.interventions_raw:
        text = (iv.get("entitat") or "").lower().strip()
        if text and text not in variant_map:
            yield Finding(check="N1", severity="P1", subject=str(iv.get("id")), key=text,
                          message=f"entitat {iv.get('entitat')!r} is not in entity_variant_map.json: "
                                  "script 07 will invent an id with slugify()")


# ── F2.4 (arquitectura-agentes §7). Their current results went to the baseline. ──

import re
import unicodedata
from collections import Counter

# Words that say what kind of organisation it is, not which one: two AVs of different barrios
# share "associació de veïns", and that must not make them look alike.
_GENERIC = {
    "associacio", "associació", "asociacion", "asociación", "associció", "av", "avv", "aavv", "aa.vv.",
    "veins", "veïns", "vecinos", "vecinal", "veinal", "veïnal", "veïnat", "vecinas", "veines",
    "federacio", "federació", "federacion", "federación", "plataforma", "fundacio", "fundació",
    "fundacion", "fundación", "colectivo", "col·lectiu", "club", "comissio", "comissió", "comision",
    "comisión", "de", "del", "dels", "la", "les", "el", "els", "los", "las", "i", "y", "d", "l", "en",
    "per", "por", "para", "a", "al", "barri", "barrio", "valencia", "valència", "comunitat",
    "comunidad", "valenciana", "pv", "cv", "país", "pais", "valencià", "valenciano", "espanya", "españa",
    "ampa", "afa", "fampa", "ceip", "cp", "ies", "escola", "colegio", "col·legi", "mares", "pares", "madres",
    "padres", "alumnes", "alumnos", "families", "familias", "cultural", "consumidors", "consumidores",
    "sense", "sin", "fronteres", "fronteras", "amics", "amigos", "veïnes", "vecinas", "i", "iii",
}
_TOKEN = re.compile(r"[\wÀ-ÿ·]+")


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


_GENERIC_FOLDED = {_fold(g) for g in _GENERIC}


def name_words(name: str) -> frozenset[str]:
    words = {_fold(w) for w in _TOKEN.findall(name.replace("’", "'").replace("'", " "))}
    return frozenset(w for w in words if w not in _GENERIC_FOLDED and len(w) > 1)


def entity_word_sets(e: dict) -> set[frozenset[str]]:
    # nom_cas/nom_val only: `variants` hold the raw texts of floor cessions ("X / Y"), which
    # would pair every entity that ever shared a turn.
    names = {e.get("nom_cas") or "", e.get("nom_val") or ""}
    return {w for w in map(name_words, names) if w}


def entity_similarity(a: dict, b: dict, _sets: dict | None = None, rare: set[str] = frozenset()) -> float:
    """Best score over the cas/val names (crossed) and variants of both entities.

    Max of Jaccard (script 06's _word_similarity, on distinctive words only) and containment: a
    merged "CEAR i CEPAIM" contains all of "Fundació CEPAIM", which Jaccard (0.2) would miss."""
    sa = _sets[a["id"]] if _sets else entity_word_sets(a)
    sb = _sets[b["id"]] if _sets else entity_word_sets(b)
    best = 0.0
    for wx in sa:
        for wy in sb:
            inter = len(wx & wy)
            if not inter:
                continue
            jac = inter / len(wx | wy)
            small = min(len(wx), len(wy))
            # One shared word is not enough, unless it is rare (at most 2 entities): "cepaim"
            # in the merged "CEAR i CEPAIM" and in "Fundació CEPAIM"
            enough = small >= 2 or (wx & wy) <= rare
            cont = inter / small if enough else 0.0
            best = max(best, jac, cont)
    return best


N2_THRESHOLD = 0.6


@check("N2", family="entities", title="near-duplicate entities in the catalog (candidates for a judge)")
def n2_near_duplicates(ctx: Context):
    ents = sorted(ctx.entitats, key=lambda e: e["id"])
    sets = {e["id"]: entity_word_sets(e) for e in ents}
    freq = Counter(w for ws in sets.values() for w in set().union(*ws) if ws)
    rare = {w for w, n in freq.items() if n <= 2 and len(w) >= 4}
    for i, a in enumerate(ents):
        for b in ents[i + 1:]:
            sim = entity_similarity(a, b, sets, rare)
            if sim >= N2_THRESHOLD:
                yield Finding(check="N2", severity="P3", subject=f"{a['id']}|{b['id']}",
                              message=f"{a['nom_val']!r} and {b['nom_val']!r} look alike ({sim:.2f}): "
                                      "same entity, or one is a merge of two?",
                              details={"similarity": round(sim, 2), "tipus": [a.get("tipus"), b.get("tipus")]})


# ── N4: tipus consistent with what the name says ──

N4_RULES = (
    (re.compile(r"\b(a\.?\s?a\.?\s?vv\.?|avv|av|associaci[óo] (?:de )?ve[iï]ns|asociaci[óo]n (?:de )?vecin[ao]s|"
                r"associaci[óo] veïnal|plataforma ve[iï]nal|veïnat)\b", re.I), {"av", "plataforma"}),
    (re.compile(r"\b(ampa|afa|fampa|associaci[óo] de (?:mares|pares)|asociaci[óo]n de (?:madres|padres))\b", re.I),
     {"educacio"}),
    (re.compile(r"\b(sindicat|sindicato|intersindical|ccoo|ugt|cgt|stepv|cnt)\b", re.I), {"sindical"}),
    (re.compile(r"\b(club (?:de )?(?:futbol|fútbol|esportiu|deportivo|bàsquet|basket|atletisme|atletismo)|"
                r"club deportiu|penya (?:esportiva|ciclista)|federaci[óo]n? (?:de )?(?:nataci[óo]n?|futbol|fútbol|atletisme))\b",
                re.I), {"esportiu"}),
)


@check("N4", family="entities", title="tipus inconsistent with the entity name (AV → av, AMPA → educacio…)")
def n4_tipus_vs_name(ctx: Context):
    for e in ctx.entitats:
        name = f"{e.get('nom_cas') or ''} | {e.get('nom_val') or ''}"
        for pat, allowed in N4_RULES:
            m = pat.search(name)
            if m and e.get("tipus") not in allowed:
                yield Finding(check="N4", severity="P3", subject=e["id"], key=f"{e.get('tipus')}≠{'/'.join(sorted(allowed))}",
                              message=f"name says {m.group(0)!r} but tipus is {e.get('tipus')!r} "
                                      f"(expected {' or '.join(sorted(allowed))})")
                break

"""Classification and translation checks (§7)."""

from __future__ import annotations

from qa.model import Context, Finding, check

C5_FIELDS = ("text_cas", "text_val", "resum_cas", "resum_val", "temes_v2", "entitat")


def _empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


@check("C5", family="classification", title="empty text, summary, temes_v2 or entitat", fast=True)
def c5_empty_fields(ctx: Context):
    for iv in ctx.intervencions:
        for field in C5_FIELDS:
            if _empty(iv.get(field)):
                yield Finding(
                    check="C5", severity="P1", subject=iv["id"], key=field,
                    message=f"{field} is empty",
                    details={"pleno_id": iv.get("pleno_id"), "field": field},
                )


# ── C1: validate_interventions.validate(), with zones normalised as script 07 does ──

def _validator():
    from qa.model import load_script
    return load_script("validate_interventions.py")


def validation_errors(ctx: Context, ivs: list[dict]) -> list[str]:
    """validate() errors ("iv_id: problem") for `ivs`, with zones normalised as script 07 does.
    Also used by verify_proposals on the interventions a proposal changes."""
    import json

    from qa.model import load_script

    v = _validator()
    ref = ctx.raw_dir / "barris_referencia.json"
    barri_names, districte_names, normalize = set(), set(), None
    if ref.exists():
        barris = json.loads(ref.read_text())
        barri_names = {b["nom"].lower() for b in barris}
        districte_names = {b["districte_nom"].lower() for b in barris}
        build = load_script("07_build_final_json.py")
        lookup = build._build_barri_lookup(barris)
        normalize = lambda z, d: build.normalize_zones(z, d, lookup)  # noqa: E731
    errors, _warnings = v.validate(ivs, barri_names, districte_names, normalize)
    return errors


@check("C1", family="classification", title="taxonomy, CAP, ambit, tipus, idioma, odd ** (validate())", fast=True)
def c1_validate(ctx: Context):
    for err in validation_errors(ctx, ctx.interventions_raw):
        iv_id, _, problem = err.partition(": ")
        yield Finding(check="C1", severity="P2", subject=iv_id, key=problem, message=problem)


# ── C3: geographic scope coherent with zones ─────────────────────────────────

@check("C3", family="classification", title="ambit=barri without zones; ciutat with zones; zones outside reference",
       fast=True)
def c3_ambit_vs_zones(ctx: Context):
    import json

    ref = ctx.raw_dir / "barris_referencia.json"
    barris = {b["nom"] for b in json.loads(ref.read_text())} if ref.exists() else set()
    for iv in ctx.intervencions:
        ambit, zones = iv.get("ambit"), iv.get("zones") or []
        if ambit == "barri" and not zones:
            yield Finding(check="C3", severity="P2", subject=iv["id"], key="barri-no-zones",
                          message="ambit=barri but no zones")
        if ambit == "ciutat" and zones:
            yield Finding(check="C3", severity="P2", subject=iv["id"], key="ciutat-with-zones",
                          message=f"ambit=ciutat but zones {zones}")
        for z in zones:
            if barris and z not in barris:
                yield Finding(check="C3", severity="P2", subject=iv["id"], key=f"zone:{z}",
                              message=f"zone {z!r} is not one of the 88 official barrios")


# ── C7: mandate ──────────────────────────────────────────────────────────────

@check("C7", family="classification", title="mandat_id desconegut, or date outside its mandate", fast=True)
def c7_mandat(ctx: Context):
    mandats = {m["id"]: m for m in (ctx._json("mandats.json") or [])}
    for iv in ctx.intervencions:
        mid, fecha = iv.get("mandat_id"), iv.get("fecha") or ""
        m = mandats.get(mid)
        if m is None:
            yield Finding(check="C7", severity="P2", subject=iv["id"], key=str(mid),
                          message=f"mandat_id {mid!r} (fecha {fecha}) is not a known mandate")
        elif not (m["inici"] <= fecha and (m.get("fi") is None or fecha <= m["fi"])):
            yield Finding(check="C7", severity="P2", subject=iv["id"], key=f"{mid}:{fecha}",
                          message=f"fecha {fecha} is outside mandate {mid} ({m['inici']}–{m.get('fi') or '…'})")


# ── C2: one source for taxonomy and CAP codebook ─────────────────────────────

C2_CONSUMERS = (
    "scripts/05_parse_interventions.py", "scripts/validate_interventions.py",
    "scripts/backfill_classify_bold.py", "scripts/reclassify_interventions.py",
    "scripts/cap_classify.py", "scripts/tests/test_dataset.py", "scripts/tests/test_taxonomy.py",
)
C2_COPY = __import__("re").compile(
    r'^\s*(VALID_TAXONOMY|CAP_CODEBOOK|VALID_CAP_CODES|VALID_AMBITS|VALID_TIPUS)\s*=\s*(\{|\[|"""|set\()', __import__("re").M)


@check("C2", family="classification", title="taxonomy and CAP codebook come only from scripts/lib/taxonomy.json",
       fast=True)
def c2_single_taxonomy(ctx: Context):
    import json

    root = ctx.repo_root
    for rel in C2_CONSUMERS:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for m in C2_COPY.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            yield Finding(check="C2", severity="P1", subject=rel, key=m.group(1),
                          message=f"defines its own {m.group(1)} (line {line}): import it from lib.taxonomy")
        if "taxonomy" not in text:
            yield Finding(check="C2", severity="P1", subject=rel, key="no-import",
                          message="does not use lib.taxonomy")
    labels = root / "web/src/utils/labels.ts"
    if labels.exists() and "scripts/lib/taxonomy.json" not in labels.read_text(encoding="utf-8"):
        yield Finding(check="C2", severity="P1", subject="web/src/utils/labels.ts", key="no-import",
                      message="labels.ts does not read scripts/lib/taxonomy.json")
    tax_file = root / "scripts/lib/taxonomy.json"
    if not tax_file.exists():
        return
    tax = json.loads(tax_file.read_text(encoding="utf-8"))
    ids = ([f"cat_{c}" for c in tax["categories"]]
           + [f"sub_{s}" for subs in tax["categories"].values() for s in subs]
           + [f"ambit_{a}" for a in tax["ambits"]])
    for lang in ("cas", "val"):
        p = root / f"web/src/i18n/{lang}.json"
        if p.exists():
            strings = json.loads(p.read_text(encoding="utf-8"))
            for k in ids:
                if k not in strings:
                    yield Finding(check="C2", severity="P0", subject=f"i18n/{lang}.json", key=k,
                                  message=f"no label for {k}: the web would show the raw id")


# ── C4: cas/val coherence (F2.4), paragraph by paragraph ──
#
# The language rule: idioma_original is the language of more than 50 % of the speech, measured in
# characters paragraph by paragraph. The text in that language is text_original verbatim (bold
# included), so it may hold paragraphs in the other language; the other text is a full
# translation, with no paragraph left untranslated. There is no "mixt".

import functools
import re

# Function words that only one of the two languages uses: words both share ("el", "del", "este",
# "esta", "que", "una"…) are left out, since Valencian uses them too.
_CAS_WORDS = {
    "los", "las", "y", "por", "para", "con", "muy", "pero", "también", "está", "están", "esto", "estos",
    "ciudad", "barrio", "barrios", "hemos", "nosotros", "nosotras", "hay", "porque", "como", "vecinos",
    "vecinas", "gracias", "señora", "señor", "queremos", "sido", "su", "sus", "cuando", "donde", "aquí",
    "ahora", "años", "año", "mucho", "mucha", "muchos", "muchas", "tiene", "tienen", "tenemos", "puede",
    "pueden", "desde", "hacer", "hace", "todo", "todos", "todas", "sin", "nuestro", "nuestra", "nuestros",
    "nuestras", "ellos", "usted", "ustedes", "ayuntamiento", "alcaldesa", "personas", "gente", "bien",
    "solo", "sólo", "ya", "hoy", "eso", "ese", "esa", "esos", "esas", "le", "fue", "pues", "días",
    "buenos", "buenas", "nada", "entonces", "siempre", "otro", "otra", "otros", "otras",
}
_VAL_WORDS = {
    "els", "i", "amb", "per", "perquè", "però", "també", "aquest", "aquesta", "aquests", "aquestes",
    "això", "açò", "ací", "ciutat", "barri", "barris", "hem", "nosaltres", "hi", "molt", "molta", "molts",
    "moltes", "dels", "pel", "pels", "veïns", "veïnes", "veïnat", "gràcies", "senyora", "senyor", "volem",
    "són", "és", "ara", "anys", "any", "quan", "on", "fer", "fa", "tot", "tots", "totes", "sense", "nostre",
    "nostra", "nostres", "vostés", "vosté", "ajuntament", "alcaldessa", "persones", "gent", "bé", "només",
    "sols", "tenen", "tenim", "pot", "poden", "des", "fins", "hui", "eixe", "eixa", "eixos", "eixes",
    "seua", "seues", "seus", "meua", "ja", "ho", "van", "dia", "bon", "bona", "res", "aleshores",
    "sempre", "altre", "altra", "altres", "doncs", "estan", "està", "sigut", "sobretot",
}
_WORDS = re.compile(r"[a-zà-ÿ·]+")
_ELISION = re.compile(r"(?<![a-zà-ÿ])[ldsmn]['’][a-zà-ÿh]")  # l'ajuntament, d'això: Valencian only
LANGS = ("castellano", "valenciano")
TEXT_FIELD = {"castellano": "text_cas", "valenciano": "text_val"}
C4_MIN_HITS = 8           # a whole summary
C4_PARA_MIN_HITS = 3      # one paragraph: "Buenos días, alcaldesa." is enough
C4_UNTRANSLATED_P1 = 0.10  # share of a translation left in the other language that makes it P1
C4_RATIO = (0.7, 1.4)


def _counts(text: str) -> tuple[int, int]:
    low = (text or "").lower()
    words = _WORDS.findall(low)
    return (sum(w in _CAS_WORDS for w in words),
            sum(w in _VAL_WORDS for w in words) + len(_ELISION.findall(low)))


def detect_language(text: str, min_hits: int = C4_MIN_HITS) -> str | None:
    """'castellano', 'valenciano', or None when the text is too short or too mixed to tell."""
    cas, val = _counts(text)
    if cas + val < min_hits:
        return None
    if cas >= 2 * val:
        return "castellano"
    if val >= 2 * cas:
        return "valenciano"
    return None


@functools.lru_cache(maxsize=1)
def _split_long_block():
    from qa.model import load_script
    return load_script("07_build_final_json.py")._split_long_block


def paragraphs(text: str) -> list[str]:
    """The units the rule is measured on: the published paragraphs, with a long block cut at
    sentence boundaries as script 07's paragraphize() does, so one paragraph = one language."""
    split = _split_long_block()
    return [u for p in re.split(r"\n+", text or "") if p.strip() for u in split(p.strip()) if u.strip()]


def language_profile(text: str) -> dict:
    """Characters (without ** markers) per paragraph language: castellano, valenciano, None."""
    out = {"castellano": 0, "valenciano": 0, None: 0}
    for p in paragraphs(text):
        out[detect_language(p, C4_PARA_MIN_HITS)] += len(p.replace("**", ""))
    return out


def majority_language(text: str) -> str | None:
    """The language of more than 50 % of the paragraphs that can be told apart, by characters."""
    prof = language_profile(text)
    cas, val = prof["castellano"], prof["valenciano"]
    if cas > val:
        return "castellano"
    if val > cas:
        return "valenciano"
    return None


def foreign_paragraphs(text: str, want: str) -> list[str]:
    """The paragraphs of `text` that read as the other language."""
    return [p for p in paragraphs(text)
            if (got := detect_language(p, C4_PARA_MIN_HITS)) and got != want]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def language_findings(iv: dict, check_id: str = "C4"):
    """Findings of the language rule for one intervention record (interventions_raw.json shape:
    the text in the original language may be empty, script 07 fills it with text_original).
    Also used by complete_manual.py before it commits."""
    iv_id, pleno_id = str(iv.get("id")), iv.get("pleno_id")
    original = iv.get("text_original") or ""
    declared = iv.get("idioma_original")
    lang = majority_language(original)
    if lang and lang != declared:
        prof = language_profile(original)
        share = prof[lang] / (prof["castellano"] + prof["valenciano"])
        yield Finding(check=check_id, severity="P1", subject=iv_id, key="idioma",
                      message=f"idioma_original is {declared}, but {share:.0%} of text_original "
                              f"(by paragraph) is {lang}",
                      details={"pleno_id": pleno_id, "idioma": lang, "was": declared,
                               "share": round(share, 3)})
    lang = lang or (declared if declared in LANGS else None)
    if not lang:
        return  # too short to tell and no usable label: nothing to measure against
    other = LANGS[1 - LANGS.index(lang)]
    same_field, other_field = TEXT_FIELD[lang], TEXT_FIELD[other]
    same = iv.get(same_field) or original
    if _norm(same) != _norm(original):
        yield Finding(check=check_id, severity="P2", subject=iv_id, key=f"original-{same_field}",
                      message=f"{same_field} should be text_original verbatim (the speech is in {lang})",
                      details={"pleno_id": pleno_id, "field": same_field, "idioma": lang})
    translation = iv.get(other_field) or original
    bad = foreign_paragraphs(translation, other)
    if bad:
        total = sum(len(p.replace("**", "")) for p in paragraphs(translation)) or 1
        share = sum(len(p.replace("**", "")) for p in bad) / total
        yield Finding(check=check_id, severity="P1" if share >= C4_UNTRANSLATED_P1 else "P2",
                      subject=iv_id, key=f"untranslated-{other_field}",
                      message=f"{len(bad)} paragraph(s) of {other_field} ({share:.0%}) are in {lang}, "
                              f"not translated: «{bad[0][:80]}»",
                      details={"pleno_id": pleno_id, "field": other_field, "idioma": lang,
                               "share": round(share, 3), "paragraphs": len(bad)})


def _paragraphs(text: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", text or "") if p.strip()])


@check("C4", family="classification",
       title="cas/val coherence: idioma by paragraph, untranslated paragraphs, ratio, ** and paragraphs")
def c4_cas_val(ctx: Context):
    for iv in ctx.interventions_raw:
        iv_id = str(iv.get("id"))
        yield from language_findings(iv)
        cas, val = iv.get("text_cas") or "", iv.get("text_val") or ""
        for field, text, want in (("resum_cas", iv.get("resum_cas"), "castellano"),
                                  ("resum_val", iv.get("resum_val"), "valenciano")):
            got = detect_language(text)
            if got and got != want:
                yield Finding(check="C4", severity="P1", subject=iv_id, key=f"lang-{field}",
                              message=f"{field} reads as {got}, not {want}",
                              details={"pleno_id": iv.get("pleno_id"), "field": field})
        if not cas or not val:
            continue  # empty text is C5
        ratio = len(val) / len(cas)
        if not C4_RATIO[0] <= ratio <= C4_RATIO[1]:
            yield Finding(check="C4", severity="P3", subject=iv_id, key="length-ratio",
                          message=f"text_val is {ratio:.2f}× the length of text_cas: one may be cut or condensed",
                          details={"pleno_id": iv.get("pleno_id"), "cas": len(cas), "val": len(val)})
        if cas.count("**") != val.count("**"):
            yield Finding(check="C4", severity="P3", subject=iv_id, key="bold",
                          message=f"{cas.count('**') // 2} bold phrases in text_cas, {val.count('**') // 2} in text_val",
                          details={"pleno_id": iv.get("pleno_id")})
        if _paragraphs(cas) != _paragraphs(val):
            yield Finding(check="C4", severity="P3", subject=iv_id, key="paragraphs",
                          message=f"{_paragraphs(cas)} paragraphs in text_cas, {_paragraphs(val)} in text_val",
                          details={"pleno_id": iv.get("pleno_id")})

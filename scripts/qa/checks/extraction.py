"""Extraction checks (§7): is everything in the actas extracted, and nothing looping?"""

from __future__ import annotations

import functools
from collections import Counter

from qa.model import Context, Finding, check, load_script


@functools.cache
def _detect_missed():
    return load_script("detect_missed_interventions.py")


@functools.cache
def _check_new_sessions():
    return load_script("check_new_sessions.py")


def load_skip_plenos(ctx: Context) -> dict:
    """skip_plenos.yml through script 05's own loader, pointed at ctx.data_dir."""
    mod = load_script("05_parse_interventions.py")
    mod.SKIP_PLENOS_FILE = ctx.corrections_dir / "skip_plenos.yml"
    return mod.load_skip_plenos()


def extracted_counts(ctx: Context) -> Counter:
    return Counter(iv["pleno_id"] for iv in ctx.interventions_raw)


@check("E1", family="extraction", title="header blocks vs extracted interventions")
def e1_headers_vs_extracted(ctx: Context):
    count_header_blocks = _detect_missed().count_header_blocks
    counts = extracted_counts(ctx)
    for path in sorted(ctx.texts_dir.glob("*.txt")):
        pleno_id = path.stem
        blocks = count_header_blocks(path.read_text(errors="replace"))
        n = counts.get(pleno_id, 0)
        if blocks and 0 < n < blocks:  # n == 0 is E9
            yield Finding(
                check="E1", severity="P1", subject=pleno_id, key=f"{n}/{blocks}",
                message=f"{blocks} header blocks but {n} interventions extracted",
                details={"blocks": blocks, "extracted": n,
                         "file": f"data/raw/texts/{pleno_id}.txt"},
            )


@check("E9", family="extraction", title="header but 0 interventions and not in skip_plenos (re-parse loop)")
def e9_reparse_loop(ctx: Context):
    has_header = _check_new_sessions().has_intervention_header
    counts = extracted_counts(ctx)
    skip = load_skip_plenos(ctx)
    for path in sorted(ctx.texts_dir.glob("*.txt")):
        pleno_id = path.stem
        if counts.get(pleno_id) or pleno_id in skip:
            continue
        if has_header(path):
            yield Finding(
                check="E9", severity="P1", subject=pleno_id,
                message="acta has a citizen-intervention header, 0 interventions and is not in "
                        "skip_plenos.yml: script 05 will re-parse (and pay for) it on every run",
                details={"file": f"data/raw/texts/{pleno_id}.txt"},
            )


@check("E3", family="extraction", title="data/plenos/*.json not listed in plenos.json (orphan)", fast=True)
def e3_orphan_pleno_files(ctx: Context):
    listed = {p["id"] for p in (ctx._json("plenos.json") or [])}
    for path in sorted((ctx.data_dir / "plenos").glob("*.json")):
        if path.stem not in listed:
            yield Finding(check="E3", severity="P0", subject=path.stem,
                          message="data/plenos file not in plenos.json: script 07 does not delete "
                                  "orphans, and the web may still build a page for it (D10)",
                          details={"file": f"data/plenos/{path.name}"})


@check("E4", family="extraction", title="intervention pleno_id missing from sessions_metadata", fast=True)
def e4_unknown_pleno(ctx: Context):
    known = {m["id"] for m in ctx.sessions_metadata}
    for iv in ctx.intervencions:
        if iv.get("pleno_id") not in known:
            yield Finding(check="E4", severity="P1", subject=iv["id"], key=str(iv.get("pleno_id")),
                          message=f"pleno_id {iv.get('pleno_id')!r} is not a known session")


# ── F2.3: candidate checks (arquitectura-agentes §7). Their current results went to the baseline. ──

import re
import unicodedata

from qa.model import load_script as _load


@functools.cache
def _parser():
    return _load("05_parse_interventions.py")


def _fold(s: str) -> str:
    """Lowercase without accents: only to compare person names, never quotes."""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# E1b counts speakers with its own patterns, independent from script 05's block splitter: if it
# reused that splitter it could never see what the splitter misses (the June–July 2026 bug).
_NAME = r"[A-ZÀ-Ú][\wÀ-ÿ’'\-]+(?:[ \t]+(?:de[ \t]+|del[ \t]+|la[ \t]+|i[ \t]+|y[ \t]+)?[A-ZÀ-Ú][\wÀ-ÿ’'\-]+){1,4}"
_SPEAKER_PATTERNS = (
    # "Sra. Maria Pérez, en representació de / en representación de"
    re.compile(r"(?:\bSra?\.?|\bD\.|\bDª|\bDña\.?)[ \t]*(" + _NAME + r")[ \t]*,[ \t]*en[ \t]+representaci",
               re.MULTILINE),
    # "Maria Pérez (Associació …)" alone on its line, optional colon; the parenthesis may wrap
    # (each run of spaces can match one way only: pdftotext indents lines by 100+ spaces, and
    # `[ \t]*[–-]?[ \t]*` in a row backtracks cubically on every line that does not match)
    re.compile(r"^[ \t]*(?:[–\-][ \t]*)?(?:(?:Sra?\.?|D\.|Dª)[ \t]*)?(" + _NAME + r")[ \t]*\((?=[^)]{4,160}\))"
               r"[^)]*\)[ \t]*:?[ \t]*$", re.MULTILINE),
)
_SPEAKER_NOISE = re.compile(r"NO VERIFICABLE|CÒPIA INFORMATIVA|ACCV|PROFESIONALES|Grup Municipal|"
                            r"Grupo Municipal|Presidenta|Alcaldessa|Alcaldesa|Regidor|Concejal",
                            re.IGNORECASE)


def acta_speakers(text: str) -> set[str]:
    """Distinct speaker names introduced in the citizen sections of an acta."""
    names = set()
    for section in _parser().split_intervention_sections(text):
        for pat in _SPEAKER_PATTERNS:
            for m in pat.finditer(section):
                line = section[max(0, m.start() - 5):m.end()]
                if _SPEAKER_NOISE.search(line):
                    continue
                words = _fold(m.group(1)).split()
                names.add(" ".join(words[:2]))
    return names


@check("E1b", family="extraction", title="speakers introduced in the acta vs extracted interventions")
def e1b_speakers_vs_extracted(ctx: Context):
    counts = extracted_counts(ctx)
    skip = load_skip_plenos(ctx)
    for path in sorted(ctx.texts_dir.glob("*.txt")):
        pleno_id = path.stem
        n = counts.get(pleno_id, 0)
        if n == 0 and pleno_id in skip:
            continue
        speakers = acta_speakers(path.read_text(errors="replace"))
        if len(speakers) > n:
            yield Finding(
                check="E1b", severity="P1", subject=pleno_id, key=f"{n}/{len(speakers)}",
                message=f"{len(speakers)} speakers introduced in the citizen sections, {n} extracted",
                details={"speakers": sorted(speakers), "extracted": n,
                         "file": f"data/raw/texts/{pleno_id}.txt"},
            )


# ── E2: duplicates by word shingles, within a pleno or across plenos ──

SHINGLE = 5
# §7 says "similarity > 0.8", meant as Jaccard. With containment, 0.6 catches all 8 duplicate
# pairs of the pre-990a980 data (the two re-extracted copies of 2023-04-27 share 0.65 and 0.69),
# while no two distinct interventions of the current data share more than 0.46.
E2_THRESHOLD = 0.6
E2_MIN_SHINGLES = 30   # a text of fewer than ~35 words is too short to call a duplicate
_WORD = re.compile(r"[\wÀ-ÿ’']+")


def _text(iv: dict) -> str:
    return (iv.get("text_original") or iv.get("text_cas") or iv.get("text_val") or "").replace("**", "")


def shingles(text: str, k: int = SHINGLE) -> set[int]:
    words = _WORD.findall(text.lower())
    return {hash(" ".join(words[i:i + k])) for i in range(max(0, len(words) - k + 1))}


def near_duplicates(ivs: list[dict], threshold: float = E2_THRESHOLD) -> list[tuple[float, dict, dict]]:
    sets = [shingles(_text(iv)) for iv in ivs]
    postings: dict[int, list[int]] = {}
    for i, s in enumerate(sets):
        for h in s:
            postings.setdefault(h, []).append(i)
    shared: Counter = Counter()
    for plist in postings.values():
        if 1 < len(plist) <= 50:  # a shingle in 50+ texts is boilerplate ("moltes gràcies…")
            for a in range(len(plist)):
                for b in range(a + 1, len(plist)):
                    shared[(plist[a], plist[b])] += 1
    out = []
    for (a, b), n in shared.items():
        # Containment, not Jaccard: a duplicate is often a truncated copy of the other (CD Apolo:
        # 916 vs 4,726 characters before 990a980), and Jaccard punishes the length difference.
        smaller = min(len(sets[a]), len(sets[b]))
        sim = n / smaller if smaller >= E2_MIN_SHINGLES else 0.0
        if sim > threshold:
            out.append((sim, ivs[a], ivs[b]))
    return sorted(out, key=lambda t: (-t[0], t[1].get("id", ""), t[2].get("id", "")))


@check("E2", family="extraction", title="duplicate interventions (shingle containment > 0.6), same or other pleno")
def e2_duplicates(ctx: Context):
    for sim, a, b in near_duplicates(ctx.interventions_raw):
        ida, idb = sorted((str(a.get("id")), str(b.get("id"))))
        same = a.get("pleno_id") == b.get("pleno_id")
        yield Finding(
            check="E2", severity="P1", subject=f"{ida}|{idb}",
            message=f"{sim:.0%} of the shorter text is in the other, {'same pleno' if same else 'different plenos'} "
                    f"({a.get('pleno_id')} / {b.get('pleno_id')}): one is probably a duplicate",
            details={"similarity": round(sim, 3), "pleno_ids": [a.get("pleno_id"), b.get("pleno_id")],
                     "lengths": [len(_text(a)), len(_text(b))]},
        )


# ── E5: politicians extracted as citizens ──

_OFFICE = re.compile(
    r"\b(regidora?|concejala?|alcalde(?:ssa|sa)?|tinent[ae]? d['’]alcalde|teniente de alcalde|"
    r"secretari[oa]? general del ple|secretari[oa]? del pleno|portaveu|portavoz)\b", re.IGNORECASE)
_PARTY = re.compile(
    r"^\s*(?:grup(?:o)? municipal\b.*|grupo pol[ií]tico\b.*|PP|PSPV(?:-PSOE)?|PSOE|Compromís|Vox|"
    r"Ciudadanos|Ciutadans|Cs|Podem|Podemos|Val[eè]ncia en Com[uú]|Esquerra Unida.*)\s*$", re.IGNORECASE)


def _mandate_of(ctx: Context, fecha: str | None) -> dict | None:
    for m in ctx._json("mandats.json") or []:
        if fecha and m.get("inici", "") <= fecha and (not m.get("fi") or fecha <= m["fi"]):
            return m
    return None


def _is_mayor(intervinient: str, mayor: str | None) -> bool:
    if not mayor or not intervinient:
        return False
    parts = _fold(mayor).split()
    who = set(_fold(intervinient).split())
    # first name + first surname ("maria jose catala verdet" → "maria", "catala")
    surnames = [p for p in parts[1:] if len(p) > 3]
    return parts[0] in who and bool(surnames) and surnames[-2 if len(surnames) > 1 else -1] in who


@check("E5", family="extraction", title="politician extracted as a citizen (mayor, office, party)")
def e5_politicians(ctx: Context):
    for iv in ctx.interventions_raw:
        who, ent = iv.get("intervinient") or "", iv.get("entitat") or ""
        mandate = _mandate_of(ctx, iv.get("fecha") or iv.get("data"))
        reason = None
        if _is_mayor(who, (mandate or {}).get("alcalde")):
            reason = f"intervinient is the mayor of mandate {mandate['id']}"
        elif _OFFICE.search(who):
            reason = f"intervinient has a municipal office: {_OFFICE.search(who).group(0)!r}"
        elif _PARTY.match(ent):
            reason = f"entitat is a political group: {ent!r}"
        if reason:
            yield Finding(check="E5", severity="P1", subject=str(iv.get("id")), key=reason.split(":")[0],
                          message=reason, details={"intervinient": who, "entitat": ent,
                                                   "pleno_id": iv.get("pleno_id")})


# ── E6: truncated text ──

E6_MIN_RATIO = 0.4
_END = re.compile(r"(?:[.!?…»”\"')\]]|\b(?:gr[àa]cies|gracias|merc[ée]s?))\s*$", re.IGNORECASE)


def _source_blocks(text: str) -> list[str]:
    p = _parser()
    return [b for s in p.split_intervention_sections(text) for b in p.extract_intervention_blocks(s)]


def _block_for(iv: dict, blocks: list[str]) -> str | None:
    """The source block whose header names the speaker (by a surname of 4+ letters)."""
    names = [w for w in _fold(iv.get("intervinient") or "").split() if len(w) >= 4]
    if not names:
        return None
    hits = [b for b in blocks if names[-1] in _fold(b[:300])]
    return hits[0] if len(hits) == 1 else None


@check("E6", family="extraction", title="truncated text (no final punctuation, or < 40 % of its source block)")
def e6_truncated(ctx: Context):
    by_pleno: dict[str, list[dict]] = {}
    for iv in ctx.interventions_raw:
        by_pleno.setdefault(str(iv.get("pleno_id")), []).append(iv)
    for pleno_id, ivs in sorted(by_pleno.items()):
        text = ctx.text(pleno_id)
        blocks = _source_blocks(text) if text else []
        for iv in ivs:
            original = (iv.get("text_original") or "").replace("**", "").strip()
            if not original:
                continue  # empty text is C5
            if not _END.search(original):
                yield Finding(check="E6", severity="P2", subject=str(iv.get("id")), key="no-final-punctuation",
                              message=f"text_original ends without punctuation: …{original[-60:]!r}",
                              details={"length": len(original), "pleno_id": pleno_id})
                continue
            block = _block_for(iv, blocks)
            if block and len(original) < E6_MIN_RATIO * len(block):
                yield Finding(check="E6", severity="P2", subject=str(iv.get("id")), key="short-vs-block",
                              message=f"text_original has {len(original)} characters, its source block "
                                      f"{len(block)} ({len(original) / len(block):.0%})",
                              details={"length": len(original), "block": len(block), "pleno_id": pleno_id,
                                       "file": f"data/raw/texts/{pleno_id}.txt"})


# ── E7: floor-cession candidates (F2.5). Deterministic filter; the extraction-reviewer judges. ──

_CESSION = re.compile(
    r"(?:cedei(?:x|xo|xen)\s+(?:el\s+seu|la\s+seua|el\s+meu|la\s+meua)\s+(?:torn|paraula)\s+a"
    r"|ced(?:e|o|en)\s+(?:su|mi|el)\s+turno\s+a"
    r"|en\s+nom\s+de|en\s+nombre\s+de|en\s+representaci[óo]n?\s+de"
    r"|com\s+a\s+(?:president|presidenta|portaveu|secretari|secretària|membre|representant)\s+de"
    r"|como\s+(?:presidente|presidenta|portavoz|secretari[oa]|miembro|representante)\s+de)"
    r"\s+((?:l['’]|la\s+|el\s+|les\s+|els\s+|los\s+|las\s+)?[A-ZÀ-Ú][^.;:\n]{3,110}?)"
    r"(?=[,.;:)\n]|\s(?:i|y|que|per|para|a|en|amb|con|qui|quien)\s)",
)


def cession_mentions(text: str) -> list[tuple[str, str]]:
    """(quote, organisation) for every self-presentation on behalf of a named organisation."""
    out = []
    for m in _CESSION.finditer(text or ""):
        start = max(0, text.rfind("\n", 0, m.start()) + 1, m.start() - 80)
        out.append((" ".join(text[start:m.end() + 1].split()), m.group(1).strip()))
    return out


def _same_org(mention: str, names: list[str]) -> bool:
    from qa.checks.entities import name_words
    words = name_words(mention)
    if not words:
        return True  # "en nombre de los vecinos": no organisation named
    known = set().union(*(name_words(n) for n in names if n)) if names else set()
    return len(words & known) / len(words) >= 0.5


@check("E7", family="extraction", title="floor-cession candidates: speaks on behalf of another organisation")
def e7_cession_candidates(ctx: Context):
    entities = {e["id"]: e for e in ctx.entitats}
    variant_map = ctx._json("raw/entity_variant_map.json") or {}
    with_cessio = {str(r.get("iv_id")) for r in ctx.corrections("reassignments.yml") or []
                   if isinstance(r, dict) and r.get("entitat_cessio")}
    blocks_cache: dict[str, list[str]] = {}
    for iv in ctx.interventions_raw:
        iv_id = str(iv.get("id"))
        if iv.get("entitat_cessio") or iv_id in with_cessio:
            continue
        ent_text = iv.get("entitat") or ""
        ent = entities.get(variant_map.get(ent_text.lower().strip(), ""), {})
        names = [ent_text, ent.get("nom_cas"), ent.get("nom_val")]
        pleno = str(iv.get("pleno_id"))
        if pleno not in blocks_cache:
            acta = ctx.text(pleno)
            blocks_cache[pleno] = _source_blocks(acta) if acta else []
        block = _block_for(iv, blocks_cache[pleno]) or ""
        body = block.split("\n", 1)[1] if "\n" in block else ""   # without the registered header
        # One finding per intervention: the acta wraps lines, so the block and text_original
        # often name the same organisation with a different cut ("…29 d'octubre" / "…2024").
        mentions = [{"source": source, "quote": quote, "org": org}
                    for source, text in (("acta", body), ("text_original", iv.get("text_original") or ""))
                    for quote, org in cession_mentions(text) if not _same_org(org, names)]
        if mentions:
            org = mentions[0]["org"]
            yield Finding(check="E7", severity="P2", subject=iv_id,
                          message=f"speaks for {org!r}, registered as {ent_text!r}: floor cession?",
                          details={"pleno_id": pleno, "quote": mentions[0]["quote"], "mentions": mentions,
                                   "file": f"data/raw/texts/{pleno}.txt"})

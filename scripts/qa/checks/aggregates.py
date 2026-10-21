"""Aggregate checks (§7): G1 (web figures) and G4 (public dataset counts)."""

from __future__ import annotations

import csv
import json
import re

import yaml

from qa.model import Context, Finding, check

PUBLIC_DIR = "web/public/datos"
FIGURES_FILE = "scripts/qa/figures.yml"

# Pages whose figures come from web/src/utils/stats.ts (F0b.7–F0b.8). Others migrate in F3.
STATS_PAGES = (
    "web/src/pages/[lang]/index.astro",
    "web/src/pages/[lang]/analisis/index.astro",
    "web/src/pages/[lang]/analisi/index.astro",
    "web/src/pages/[lang]/datos/index.astro",
    "web/src/pages/[lang]/dades/index.astro",
    "web/src/pages/[lang]/otras-voces/index.astro",
    "web/src/pages/[lang]/altres-veus/index.astro",
)
# A literal figure where stats.ts has one: the shapes that drifted before (581, 276/277, 42, ×4.8…)
HARDCODED = (
    ("count", re.compile(r"(?<![\w{$.])(\d{3,}|\d{1,3}(?:\.\d{3})+)\s+(?:intervenc|entidad|entitat)")),
    ("card", re.compile(r"\bn:\s*'([^']*\d[^']*)'")),
    ("barri", re.compile(r"lidera (?:con|amb) (\d+)")),
    ("years", re.compile(r"(?<![\w{$])(\d+) (?:años|anys) de (?:datos|dades)|revelen?<br/>(\d+)")),
    ("ratio", re.compile(r"×\d")),
)


def _number(text: str) -> int:
    return int(text.replace(".", ""))


def _source_value(ctx: Context, chk: dict):
    if "json" in chk:
        value = json.loads((ctx.repo_root / chk["json"]).read_text(encoding="utf-8"))
        for part in str(chk["path"]).split("."):
            value = value[part]
        return value
    if "csv_rows" in chk:
        with open(ctx.repo_root / chk["csv_rows"], newline="", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in csv.reader(fh)) - 1
    raise ValueError(f"unknown check {chk}")


@check("G1", family="aggregates", title="web figures: none hardcoded where stats.ts has them; figures.yml matches its sources and pages",
       fast=True)
def g1_figures(ctx: Context):
    # 1. No migrated page writes a figure by hand
    for rel in STATS_PAGES:
        path = ctx.repo_root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for kind, rx in HARDCODED:
            for m in rx.finditer(text):
                written = next((g for g in m.groups() if g), m.group(0)) if m.groups() else m.group(0)
                line = text.count("\n", 0, m.start()) + 1
                yield Finding(check="G1", severity="P0", subject=f"{rel}|{kind}", key=written,
                              message=f"hardcoded figure {written!r} (line {line}): read it from "
                                      "web/src/utils/stats.ts",
                              details={"file": rel, "line": line, "kind": kind})

    # 2. External figures: manifest value == source file == every page that writes it
    manifest = ctx.repo_root / FIGURES_FILE
    if not manifest.exists():
        return
    for fig in yaml.safe_load(manifest.read_text(encoding="utf-8")) or []:
        fid, value = fig["id"], fig["value"]
        if fig.get("check"):
            try:
                actual = _source_value(ctx, fig["check"])
            except (OSError, KeyError, ValueError) as e:
                yield Finding(check="G1", severity="P1", subject=f"figures.yml|{fid}", key="source",
                              message=f"cannot read the source of {fid}: {type(e).__name__}: {e}")
            else:
                if actual != value:
                    yield Finding(check="G1", severity="P0", subject=f"figures.yml|{fid}", key=f"{value}!={actual}",
                                  message=f"{fid}: figures.yml says {value}, its source now says {actual} "
                                          "(update value, as_of and the pages)")
        for w in fig.get("where") or []:
            path = ctx.repo_root / w["file"]
            written = {_number(x) for x in re.findall(w["pattern"], path.read_text(encoding="utf-8"))} \
                if path.exists() else set()
            if written != {value}:
                yield Finding(check="G1", severity="P0", subject=f"{w['file']}|{fid}",
                              key=",".join(map(str, sorted(written))) or "missing",
                              message=f"{fid}: page writes {sorted(written) or 'nothing'}, figures.yml says {value}")


@check("G4", family="aggregates", title="public dataset (web/public/datos) has the same counts as data/", fast=True)
def g4_public_dataset(ctx: Context):
    pub = ctx.repo_root / PUBLIC_DIR
    expected = {"interventions": len(ctx.intervencions), "entities": len(ctx.entitats)}
    files = {
        "intervencions.json": "interventions",
        "intervencions_light.json": "interventions",
        "intervencions_metadata.csv": "interventions",
        "entitats.json": "entities",
    }
    for name, what in files.items():
        path = pub / name
        if not path.exists():
            yield Finding(check="G4", severity="P0", subject=name, key="missing",
                          message=f"{PUBLIC_DIR}/{name} is missing (run export_dataset.py)")
            continue
        if name.endswith(".csv"):
            with open(path, newline="", encoding="utf-8") as fh:
                n = sum(1 for _ in csv.DictReader(fh))
        else:
            n = len(json.loads(path.read_text(encoding="utf-8")))
        if n != expected[what]:
            yield Finding(check="G4", severity="P0", subject=name, key=f"{n}!={expected[what]}",
                          message=f"{n} {what} in the public download, {expected[what]} in data/ "
                                  "(run export_dataset.py)")


# ── G2 / G3: the built site (web/dist) ───────────────────────────────────────

import html as _html
from pathlib import Path as _Path

# Editorial pages: their text is written by us. Detail pages (one per pleno, intervention or entity)
# render data records, whose numbers come from the data by construction.
G2_PAGES = ("", "analisis", "analisi", "datos", "dades", "otras-voces", "altres-veus", "la-ciutat",
            "metodologia", "mapa", "plens", "intervencions", "entitats", "legal")
PAIRS = {"datos": "dades", "analisis": "analisi", "otras-voces": "altres-veus"}
NUMBER = r"(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)"
KEYWORD = (r"(?:%|intervenc\w*|entidad\w*|entitat\w*|barri\w*|distrit\w*|districte\w*|mandat\w*|plen(?:os|s)?\b|"
           r"propuestas?|propostes?|quejas?|queixes|participantes?|participants|personas|persones|habitant\w*)")
FIGURE = re.compile(r"(?:([\wÀ-ÿ'’]+)\s+)?" + NUMBER + r"(?:\s|&nbsp;)*" + KEYWORD, re.I)
G2_ALLOWLIST = "scripts/qa/g2_allowlist.yml"


def _dist_fresh(ctx: Context) -> bool:
    from qa.checks.web import dist_fresh
    return dist_fresh(ctx)


def _visible_text(path: _Path) -> str:
    """Rendered text of a page: no scripts, styles, island props or tags."""
    t = path.read_text(encoding="utf-8")
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r'\s(props|data-[\w-]+)="[^"]*"', " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t))


def _figures(text: str) -> list[tuple[str, str, str]]:
    """(previous word, number, keyword), e.g. ("suma", "597", "intervenciones")."""
    out = []
    for m in FIGURE.finditer(text):
        prev, number = m.group(1) or "", m.group(2)
        kw = m.group(0)[m.group(0).index(number) + len(number):].strip().lower()
        out.append((prev, number, kw))
    return out


def _manifest_values(ctx: Context) -> set[str]:
    """Values of scripts/qa/figures.yml, in the formats a page writes them (87528 → 87.528)."""
    path = ctx.repo_root / FIGURES_FILE
    vals = set()
    for f in (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or []:
        v = f["value"]
        vals |= {str(v), f"{v:,}".replace(",", ".")} if isinstance(v, int) else {str(v)}
    return vals


def _page_source(ctx: Context, slug: str) -> str:
    """Source of one page: its .astro plus the components it imports (stats.ts computes: excluded)."""
    pages = ctx.repo_root / "web/src/pages/[lang]"
    page = pages / slug / "index.astro" if slug else pages / "index.astro"
    if not page.exists():
        return ""
    parts, text = [], page.read_text(encoding="utf-8")
    parts.append(text)
    for m in re.finditer(r"from ['\"](\.\.?/[^'\"]+)['\"]", text):
        dep = (page.parent / m.group(1)).resolve()
        if dep.suffix in (".tsx", ".ts", ".astro") and dep.name != "stats.ts" and dep.exists():
            parts.append(dep.read_text(encoding="utf-8"))
    src = "\n".join(parts)
    # Styles and comments are not text a visitor reads ("margin-left: 4%", "// 48% is the outlier")
    src = re.sub(r"<style\b.*?</style>", " ", src, flags=re.S | re.I)
    src = re.sub(r"style=(\"[^\"]*\"|\{`[^`]*`\}|\{\{[^}]*\}\})", " ", src)
    src = re.sub(r"/\*.*?\*/|<!--.*?-->", " ", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", " ", src)
    return re.sub(r"\s+", " ", _html.unescape(src))


def _page_paths(ctx: Context, lang: str):
    for slug in G2_PAGES:
        path = ctx.repo_root / "web/dist" / lang / slug / "index.html" if slug else \
            ctx.repo_root / "web/dist" / lang / "index.html"
        if path.exists():
            yield slug, path


@check("G2", family="aggregates", title="built pages: no figure next to a data keyword typed by hand (outside stats.ts)",
       fast=True)
def g2_hardcoded_in_dist(ctx: Context):
    if not _dist_fresh(ctx):
        return  # no build, or older than data/: nothing reliable to scan (cd web && npm run build)
    allow = yaml.safe_load(((ctx.repo_root / G2_ALLOWLIST).read_text(encoding="utf-8"))
                           if (ctx.repo_root / G2_ALLOWLIST).exists() else "") or []
    allow_rx = [re.compile(a["pattern"], re.I) for a in allow]
    manifest = _manifest_values(ctx)
    for lang in ("cas", "val"):
        for slug, path in _page_paths(ctx, lang):
            corpus = _page_source(ctx, slug)
            seen = set()
            for prev, number, kw in _figures(_visible_text(path)):
                phrase = f"{prev} {number} {kw}".strip()
                if phrase in seen or number in manifest or any(r.search(phrase) for r in allow_rx):
                    continue
                seen.add(phrase)
                # Typed into the source with the same words around it ("con 48%", "581 intervenciones")?
                # A computed figure is an expression there ("con ${…}%"), so it never matches.
                lead = rf"{re.escape(prev)}(?:\s|&nbsp;)+" if prev else r"(?<![\d.,${])"
                if re.search(lead + rf"{re.escape(number)}(?:\s|&nbsp;)*{re.escape(kw[:6])}", corpus, re.I):
                    rel = f"web/dist/{lang}/{slug + '/' if slug else ''}index.html"
                    yield Finding(check="G2", severity="P1", subject=f"{rel}|{number} {kw}", key=phrase,
                                  message=f"'{phrase}' is typed into the web source: compute it in "
                                          f"web/src/utils/stats.ts, or list it in {G2_ALLOWLIST} with a reason",
                                  details={"page": rel, "phrase": phrase})


@check("G3", family="aggregates", title="the same figures in each cas page and its val pair", fast=True)
def g3_cas_val_parity(ctx: Context):
    if not _dist_fresh(ctx):
        return
    for slug in G2_PAGES:
        if slug in PAIRS.values():
            continue
        cas = ctx.repo_root / "web/dist/cas" / slug / "index.html" if slug else ctx.repo_root / "web/dist/cas/index.html"
        vslug = PAIRS.get(slug, slug)
        val = ctx.repo_root / "web/dist/val" / vslug / "index.html" if vslug else ctx.repo_root / "web/dist/val/index.html"
        if not (cas.exists() and val.exists()):
            continue
        norm = lambda n: n.replace(".", "").replace(",", ".") if re.fullmatch(r"\d{1,3}(\.\d{3})+", n) is None else n.replace(".", "")
        nums_cas = {norm(n) for _, n, _ in _figures(_visible_text(cas))}
        nums_val = {norm(n) for _, n, _ in _figures(_visible_text(val))}
        for n in sorted(nums_cas ^ nums_val, key=lambda x: (len(x), x)):
            where = "cas only" if n in nums_cas else "val only"
            yield Finding(check="G3", severity="P1", subject=f"{slug or 'home'}|{n}", key=where,
                          message=f"figure {n} appears in the {where.replace(' only', '')} page but not in its pair "
                                  f"(cas/{slug or ''} ↔ val/{vslug or ''})",
                          details={"cas": str(cas.relative_to(ctx.repo_root)), "val": str(val.relative_to(ctx.repo_root))})

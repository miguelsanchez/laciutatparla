"""Web checks (§7, arquitectura-agentes.md F4.7): W6 page weight, W7 i18n parity, W8 internal links.

W6 and W8 read the production build (web/dist) and skip when it is missing or older than data/ or
the web's sources; W7 reads the sources and runs in the pre-commit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

from qa.model import Context, Finding, check

BUDGET_FILE = "meta/qa/web_budget.json"
DIST = "web/dist"
LANGS = ("cas", "val")


# ── W6: page weight ──────────────────────────────────────────────────────────

def dist_fresh(ctx: Context) -> bool:
    """True when web/dist was built after the last change to the data and to the web's code.

    The daily run pulls main but never builds, so a dist from before a merged web change
    would otherwise be checked as if current (git pull gives the changed files a new mtime).
    """
    index = ctx.repo_root / DIST / "cas/index.html"
    if not index.exists():
        return False
    web = ctx.repo_root / "web"
    sources = [ctx.data_dir / "intervencions.json", ctx.data_dir / "entitats.json",
               web / "astro.config.mjs", web / "package.json",
               *(p for d in ("src", "public") for p in (web / d).rglob("*") if p.is_file())]
    newest = max((p.stat().st_mtime for p in sources if p.exists()), default=0)
    return index.stat().st_mtime >= newest


def html_sizes(dist: Path) -> dict[str, int]:
    """Size in bytes of every HTML page, keyed by its path under dist/."""
    return {str(p.relative_to(dist)): p.stat().st_size for p in dist.rglob("*.html")}


def n_interventions(ctx: Context) -> int:
    path = ctx.data_dir / "intervencions.json"
    return len(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else 0


def allowed(budget: dict, bytes_: int, n_now: int) -> int:
    """A budget grows with the data (the heavy pages embed every intervention) and a small tolerance."""
    growth = max(1.0, n_now / budget["interventions"]) if budget.get("interventions") else 1.0
    return int(bytes_ * growth * (1 + budget.get("tolerance", 0.01)))


def budget_findings(ctx: Context, budget: dict, sizes: dict[str, int], n_now: int):
    for page, limit in budget["pages"].items():
        size = sizes.get(page)
        if size is None:
            continue
        cap = allowed(budget, limit, n_now)
        if size > cap:
            yield Finding(check="W6", severity="P2", subject=page, key="page",
                          message=f"{page} weighs {size / 1e6:.2f} MB, over its budget of {cap / 1e6:.2f} MB "
                                  f"(ratchet in {BUDGET_FILE}: it can only shrink, except as the data grows)",
                          details={"bytes": size, "budget": cap})
    cap = allowed(budget, budget["max_other_page"], n_now)
    for page, size in sizes.items():
        if page not in budget["pages"] and size > cap:
            yield Finding(check="W6", severity="P2", subject=page, key="new-heavy",
                          message=f"{page} weighs {size / 1e6:.2f} MB, more than any page without its own budget "
                                  f"({cap / 1e6:.2f} MB): slim it, or budget it with scripts/qa/web_budget.py --add",
                          details={"bytes": size, "budget": cap})
    total, cap = sum(sizes.values()), allowed(budget, budget["total_html"], n_now)
    if total > cap:
        yield Finding(check="W6", severity="P2", subject="web/dist", key="total",
                      message=f"the site's HTML weighs {total / 1e6:.1f} MB, over its budget of {cap / 1e6:.1f} MB",
                      details={"bytes": total, "budget": cap})


@check("W6", family="web", title="page weight budget (ratchet): the heavy pages cannot grow beyond the data")
def w6_page_weight(ctx: Context):
    path = ctx.repo_root / BUDGET_FILE
    if not path.exists() or not dist_fresh(ctx):
        return
    budget = json.loads(path.read_text(encoding="utf-8"))
    yield from budget_findings(ctx, budget, html_sizes(ctx.repo_root / DIST), n_interventions(ctx))


# ── W7: i18n parity and default language ─────────────────────────────────────

def default_langs(root: Path) -> dict[str, str | None]:
    """Where the default language is declared, and what each place says."""
    config = (root / "web/astro.config.mjs").read_text(encoding="utf-8")
    redirects = root / "web/public/_redirects"
    found = {
        "astro.config.mjs redirect": re.search(r"['\"]/['\"]\s*:\s*['\"]/(\w+)/['\"]", config),
        "astro.config.mjs defaultLocale": re.search(r"defaultLocale\s*:\s*['\"](\w+)['\"]", config),
        "public/_redirects": re.search(r"(?m)^/\s+/(\w+)/", redirects.read_text(encoding="utf-8"))
        if redirects.exists() else None,
    }
    return {k: (m.group(1) if m else None) for k, m in found.items()}


@check("W7", family="web", title="i18n: cas.json and val.json have the same keys; one default language everywhere",
       fast=True)
def w7_i18n(ctx: Context):
    root = ctx.repo_root
    strings = {lang: json.loads((root / f"web/src/i18n/{lang}.json").read_text(encoding="utf-8")) for lang in LANGS}
    for lang, other in (("cas", "val"), ("val", "cas")):
        for key in sorted(set(strings[other]) - set(strings[lang])):
            yield Finding(check="W7", severity="P1", subject=f"i18n/{lang}.json|{key}", key="missing",
                          message=f"'{key}' is in {other}.json but not in {lang}.json: that page shows the raw key")
        for key in sorted(k for k, v in strings[lang].items() if isinstance(v, str) and not v.strip()):
            yield Finding(check="W7", severity="P1", subject=f"i18n/{lang}.json|{key}", key="empty",
                          message=f"'{key}' is empty in {lang}.json")

    langs = default_langs(root)
    if len(set(langs.values())) != 1 or None in langs.values():
        yield Finding(check="W7", severity="P1", subject="default-language", key=json.dumps(langs, sort_keys=True),
                      message="the default language is not declared the same everywhere: "
                              + ", ".join(f"{k} → {v}" for k, v in langs.items()), details=langs)
        return
    default = next(iter(langs.values()))
    # x-default in the build points to the default language's version of each page
    if dist_fresh(ctx):
        for page in ("cas/index.html", "cas/otras-voces/index.html", "val/plens/index.html"):
            path = root / DIST / page
            if not path.exists():
                continue
            m = re.search(r'hreflang="x-default" href="https?://[^/"]+(/[^"]*)"', path.read_text(encoding="utf-8"))
            if not m or not m.group(1).startswith(f"/{default}/"):
                yield Finding(check="W7", severity="P1", subject=f"web/dist/{page}|x-default", key=m.group(1) if m else "",
                              message=f"x-default on {page} is {m.group(1) if m else 'missing'}, "
                                      f"not a /{default}/ page (the default language)")


# ── W8: internal links ───────────────────────────────────────────────────────

LINK = re.compile(r'\s(?:href|src)="(/(?!/)[^"#?]*)')


def resolves(dist: Path, target: str, redirects: set[str]) -> bool:
    if target in redirects:
        return True
    rel = unquote(target).lstrip("/")
    if target.endswith("/"):
        return (dist / rel / "index.html").exists()
    return (dist / rel).is_file() or (dist / rel / "index.html").exists()


def broken_links(dist: Path) -> dict[str, list[str]]:
    """Internal links of every page that point to nothing in the build: target → pages linking it."""
    redirects_file = dist / "_redirects"
    redirects = {line.split()[0] for line in redirects_file.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")} if redirects_file.exists() else set()
    seen: dict[str, bool] = {}
    broken: dict[str, list[str]] = {}
    for page in sorted(dist.rglob("*.html")):
        for target in set(LINK.findall(page.read_text(encoding="utf-8", errors="replace"))):
            if target not in seen:
                seen[target] = resolves(dist, target, redirects)
            if not seen[target]:
                broken.setdefault(target, []).append(str(page.relative_to(dist)))
    return broken


@check("W8", family="web", title="internal links in the build point to existing pages and files")
def w8_internal_links(ctx: Context):
    if not dist_fresh(ctx):
        return
    for target, pages in sorted(broken_links(ctx.repo_root / DIST).items()):
        yield Finding(check="W8", severity="P0", subject=target, key="broken",
                      message=f"{target} does not exist in the build; linked from {len(pages)} page(s), "
                              f"e.g. {pages[0]}", details={"pages": pages[:10], "count": len(pages)})

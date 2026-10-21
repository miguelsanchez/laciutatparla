"""W6 page weight, W7 i18n parity and default language, W8 internal links (F4.7), on tiny sites."""

import json
import os
import time

import pytest

from qa import web_budget as WB
from qa.checks import web as W
from qa.model import Context


@pytest.fixture
def site(tmp_path):
    """A repo with data/, the i18n files, the default-language config and a small build."""
    root = tmp_path
    (root / "data").mkdir()
    (root / "data/intervencions.json").write_text(json.dumps([{"id": str(i)} for i in range(100)]))
    (root / "data/entitats.json").write_text("[]")
    i18n = root / "web/src/i18n"
    i18n.mkdir(parents=True)
    (i18n / "cas.json").write_text(json.dumps({"nav": "Plenos", "title": "Hola"}))
    (i18n / "val.json").write_text(json.dumps({"nav": "Plens", "title": "Hola"}))
    (root / "web/public").mkdir()
    (root / "web/public/_redirects").write_text("/  /val/  301\n")
    (root / "web/astro.config.mjs").write_text("redirects: { '/': '/val/' },\ni18n: { defaultLocale: \"val\" }\n")
    pages = {
        "cas/index.html": '<link rel="alternate" hreflang="x-default" href="https://x.es/val/">'
                          '<a href="/cas/plens/">p</a><a href="/val/">v</a><img src="/favicon.svg">',
        "val/index.html": '<a href="/val/plens/">p</a><a href="/">home</a>',
        "cas/plens/index.html": '<a href="/cas/entitats/fam%C3%ADlies/">e</a>' + "x" * 5000,
        "val/plens/index.html": '<link rel="alternate" hreflang="x-default" href="https://x.es/val/plens/">',
        "cas/entitats/famílies/index.html": "ok",
    }
    dist = root / "web/dist"
    for rel, html in pages.items():
        (dist / rel).parent.mkdir(parents=True, exist_ok=True)
        (dist / rel).write_text(html)
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "_redirects").write_text("/  /val/  301\n")
    future = time.time() + 60          # the build is newer than data/
    for p in dist.rglob("*.html"):
        os.utime(p, (future, future))
    return root


def run(check, root):
    return list(check(Context(root / "data", repo_root=root)))


def test_clean_site_has_no_findings(site):
    assert run(W.w7_i18n, site) == []
    assert run(W.w8_internal_links, site) == []      # percent-encoded accents resolve


def test_w8_broken_link(site):
    page = site / "web/dist/val/index.html"
    page.write_text(page.read_text() + '<a href="/val/nowhere/">x</a>')
    os.utime(page, (time.time() + 60,) * 2)
    [f] = run(W.w8_internal_links, site)
    assert (f.subject, f.severity) == ("/val/nowhere/", "P0")


def test_w8_skips_a_stale_build(site):
    (site / "data/intervencions.json").write_text("[]")      # data newer than the build
    os.utime(site / "data/intervencions.json", (time.time() + 120,) * 2)
    page = site / "web/dist/val/index.html"
    page.write_text('<a href="/val/nowhere/">x</a>')
    assert run(W.w8_internal_links, site) == []


def test_w7_missing_key_and_default_language(site):
    (site / "web/src/i18n/val.json").write_text(json.dumps({"nav": "Plens", "title": ""}))
    (site / "web/src/i18n/cas.json").write_text(json.dumps({"nav": "Plenos", "title": "Hola", "extra": "x"}))
    found = {(f.subject, f.key) for f in run(W.w7_i18n, site)}
    assert ("i18n/val.json|extra", "missing") in found and ("i18n/val.json|title", "empty") in found
    (site / "web/public/_redirects").write_text("/  /cas/  301\n")
    assert any(f.subject == "default-language" for f in run(W.w7_i18n, site))


def test_w7_x_default_must_be_the_default_language(site):
    page = site / "web/dist/cas/index.html"
    page.write_text('<link rel="alternate" hreflang="x-default" href="https://x.es/cas/">')
    os.utime(page, (time.time() + 60,) * 2)
    [f] = run(W.w7_i18n, site)
    assert f.subject == "web/dist/cas/index.html|x-default"


def test_w6_budget_grows_with_the_data_and_ratchets(site, monkeypatch):
    monkeypatch.setattr(WB, "REPO_ROOT", site)
    budget_path = site / W.BUDGET_FILE
    budget_path.parent.mkdir(parents=True)
    ctx = Context(site / "data", repo_root=site)
    sizes = W.html_sizes(site / "web/dist")
    budget = WB.initial(sizes, 100)
    budget_path.write_text(json.dumps(budget))
    assert run(W.w6_page_weight, site) == []

    heavy = "cas/plens/index.html"
    assert heavy in budget["pages"]
    grown = sizes[heavy] * 1.2
    assert list(W.budget_findings(ctx, budget, {**sizes, heavy: int(grown)}, 100))          # 20 % heavier: over
    assert not list(W.budget_findings(ctx, budget, {**sizes, heavy: int(grown)}, 125))      # but 25 % more data

    # --update lowers a limit a page now beats, and never raises one
    lighter = {**sizes, heavy: sizes[heavy] // 2}
    new, changes = WB.tightened(budget, lighter, 100)
    assert new["pages"][heavy] == sizes[heavy] // 2 and changes
    new2, _ = WB.tightened(new, sizes, 100)
    assert new2["pages"][heavy] == sizes[heavy] // 2


def test_build_older_than_web_code_is_not_checked(site):
    """A dist built before a merged web change (git pull gives it a new mtime) is stale: no findings."""
    page = site / "web/dist/cas/index.html"
    page.write_text(page.read_text().replace("https://x.es/val/", "https://x.es/cas/"))
    os.utime(page, (time.time() + 60,) * 2)
    assert any(f.subject.endswith("|x-default") for f in run(W.w7_i18n, site))
    layout = site / "web/src/layouts/Base.astro"
    layout.parent.mkdir(parents=True)
    layout.write_text("<html/>")
    os.utime(layout, (time.time() + 120,) * 2)        # the code changed after that build
    assert not W.dist_fresh(Context(site / "data", repo_root=site))
    assert run(W.w7_i18n, site) == []

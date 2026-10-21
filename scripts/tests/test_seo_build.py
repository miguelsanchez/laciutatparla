"""Tests for SEO outputs in the built web (web/dist/).

These tests require a prior `npm run build` in web/. They are skipped
automatically when the dist/ directory does not exist.

Covers:
- sitemap-index.xml and sitemap-0.xml generated and non-empty
- sitemap URL count matches expected page count
- OG/Twitter meta tags present in built HTML
- canonical link present
- JSON-LD script tag present
- robots.txt references the correct sitemap URL
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
DIST = ROOT / "web" / "dist"
PUBLIC = ROOT / "web" / "public"


def require_dist():
    if not DIST.exists():
        pytest.skip("web/dist/ not found — run: cd web && npm run build")


# ── Sitemap ───────────────────────────────────────────────────────────────────

def test_sitemap_index_exists():
    require_dist()
    assert (DIST / "sitemap-index.xml").exists()


def test_sitemap_0_exists_and_nonempty():
    require_dist()
    f = DIST / "sitemap-0.xml"
    assert f.exists()
    assert f.stat().st_size > 1000, "sitemap-0.xml appears empty"


def test_sitemap_url_count():
    require_dist()
    content = (DIST / "sitemap-0.xml").read_text()
    count = content.count("<url>")
    # Expect at least 2000 URLs (1140 intervention pages + plens × 2 langs + entitats + static pages)
    assert count >= 2000, f"Sitemap has only {count} URLs, expected ≥2000"


def test_sitemap_intervention_pages_present():
    require_dist()
    content = (DIST / "sitemap-0.xml").read_text()
    # Check for intervention detail pages in both langs
    assert "/cas/intervencions/" in content
    assert "/val/intervencions/" in content


def test_robots_references_sitemap_index():
    robots = PUBLIC / "robots.txt"
    assert robots.exists()
    text = robots.read_text()
    assert "sitemap-index.xml" in text, (
        f"robots.txt does not reference sitemap-index.xml: {text!r}"
    )


# ── Open Graph & Twitter ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def home_html():
    require_dist()
    path = DIST / "cas" / "index.html"
    if not path.exists():
        pytest.skip("cas/index.html not found in dist/")
    return path.read_text()


@pytest.fixture(scope="module")
def intervention_html():
    require_dist()
    # Find any intervention detail page
    pages = list((DIST / "cas" / "intervencions").glob("*/index.html"))
    pages = [p for p in pages if p.parent.name != "intervencions"]
    if not pages:
        pytest.skip("No intervention detail pages in dist/")
    return pages[0].read_text()


def test_og_title_present(home_html):
    assert 'property="og:title"' in home_html


def test_og_description_present(home_html):
    assert 'property="og:description"' in home_html


def test_og_image_present(home_html):
    assert 'property="og:image"' in home_html


def test_twitter_card_present(home_html):
    assert 'name="twitter:card"' in home_html


def test_canonical_link_present(home_html):
    assert 'rel="canonical"' in home_html


def test_json_ld_website_present(home_html):
    assert 'application/ld+json' in home_html
    assert '"WebSite"' in home_html


def test_intervention_page_og_type_article(intervention_html):
    assert 'content="article"' in intervention_html


def test_intervention_page_json_ld_article(intervention_html):
    assert '"Article"' in intervention_html


def test_intervention_page_canonical(intervention_html):
    assert 'rel="canonical"' in intervention_html

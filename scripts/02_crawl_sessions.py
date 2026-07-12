#!/usr/bin/env python3
"""
Script 02: Crawl each individual plenary session page.
Extracts PDF URLs (acta, orden del día) and video URL.
Output: data/raw/sessions_metadata.json
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.valencia.es"
VIDEO_ARCHIVE = "https://aytovlc.web.enetres.net/"

INPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "sessions_index.json"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "sessions_metadata.json"


def fetch_session_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def alternate_urls(url: str) -> list[str]:
    """When a URL ends with -N (N > 1), return variants with lower suffixes to try.

    The index page sometimes links to -2 or -3 but the actual content
    (with PDFs) lives at -1. We also try without any suffix.
    Example: .../2023-10-24-2 → [.../2023-10-24-1, .../2023-10-24]
    """
    m = re.search(r"-(\d+)$", url)
    if not m:
        return []
    n = int(m.group(1))
    base = url[: m.start()]
    candidates = [f"{base}-{i}" for i in range(1, n)]
    candidates.append(base)
    return candidates


def _is_plenary_acta(href: str) -> bool:
    """Check that a PDF URL is a plenary acta (not a junta municipal or other body).

    Plenary actas use code 00001 (e.g. A_00001_20260224_...).
    Other bodies use different codes: 00002 (junta de gobierno), CDI07 (consell de districte), etc.
    """
    for part in href.split("/"):
        if part.lower().endswith(".pdf"):
            return bool(re.match(r"a_00001_", part, re.IGNORECASE))
    return True  # If we can't parse the pattern, don't reject


def extract_pdf_urls(soup: BeautifulSoup, session_id: str) -> dict:
    """Extract acta and orden del día PDF URLs from session page."""
    result = {"url_acta": None, "url_orden_dia": None, "url_video": None}

    # Find all PDF links
    for a_tag in soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE)):
        href = a_tag["href"]
        full_url = BASE_URL + href if href.startswith("/") else href
        text = a_tag.get_text(strip=True).lower()

        # Classify by filename pattern or link text
        filename = href.split("/")[-1].split("?")[0].lower()

        if filename.startswith("a_") or "acta" in text or filename.startswith("acta"):
            if _is_plenary_acta(href):
                result["url_acta"] = full_url
        elif filename.startswith("od_") or "orden" in text or "orde" in text or filename.startswith("od"):
            result["url_orden_dia"] = full_url
        elif result["url_acta"] is None and filename.endswith(".pdf"):
            # Fallback: first PDF is usually the acta or OD
            result["url_orden_dia"] = full_url

    # Find video link
    for a_tag in soup.find_all("a", href=re.compile(r"enetres\.net|youtube|vimeo", re.IGNORECASE)):
        result["url_video"] = a_tag["href"]
        break

    # If no direct video link, link to the archive search
    if not result["url_video"]:
        result["url_video"] = VIDEO_ARCHIVE

    return result


def main():
    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found. Run 01_crawl_index.py first.")
        raise SystemExit(1)

    sessions = json.loads(INPUT_FILE.read_text())
    print(f"Processing {len(sessions)} sessions...")

    # Load existing metadata to allow resuming
    existing = {}
    if OUTPUT_FILE.exists():
        for s in json.loads(OUTPUT_FILE.read_text()):
            existing[s["id"]] = s

    results = []
    for i, session in enumerate(sessions):
        sid = session["id"]

        if sid in existing and existing[sid].get("acta_disponible"):
            print(f"  [{i+1}/{len(sessions)}] {sid} — already cached, skipping")
            results.append(existing[sid])
            continue
        if sid in existing:
            print(f"  [{i+1}/{len(sessions)}] {sid} — re-fetching (no acta cached)")

        print(f"  [{i+1}/{len(sessions)}] {sid} — fetching...")
        try:
            url = session["url_web"]
            soup = fetch_session_page(url)
            urls = extract_pdf_urls(soup, sid)

            # If no acta found, try alternate URL suffixes (e.g. -2 → -1)
            if not urls["url_acta"]:
                for alt_url in alternate_urls(url):
                    try:
                        alt_soup = fetch_session_page(alt_url)
                        alt_urls = extract_pdf_urls(alt_soup, sid)
                        if alt_urls["url_acta"]:
                            print(f"    → found acta at alternate URL: {alt_url}")
                            urls = alt_urls
                            session = {**session, "url_web": alt_url}
                            sid_new = alt_url.rstrip("/").split("/")[-1]
                            if sid_new != sid:
                                session["id"] = sid_new
                                sid = sid_new
                            break
                    except Exception:
                        pass

            metadata = {**session, **urls}
            metadata["acta_disponible"] = urls["url_acta"] is not None
            results.append(metadata)

            time.sleep(0.5)  # Be polite to the server
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({**session, "url_acta": None, "url_orden_dia": None,
                            "url_video": None, "acta_disponible": False, "error": str(e)})

    OUTPUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nSaved {len(results)} sessions to {OUTPUT_FILE}")

    with_acta = sum(1 for r in results if r.get("acta_disponible"))
    print(f"  Sessions with acta: {with_acta}/{len(results)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Script 01: Crawl the Valencia city council plenary sessions index.
Extracts all session links from 2011 onwards using year-category pages.
Output: data/raw/sessions_index.json
"""

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.valencia.es"

# Year category pages — each lists all sessions for that year
YEAR_CATEGORIES = {
    2011: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122583",
    2012: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122580",
    2013: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122577",
    2014: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122574",
    2015: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122571",
    2016: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122568",
    2017: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122565",
    2018: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122562",
    2019: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122559",
    2020: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122556",
    2021: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122553",
    2022: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122550",
    2023: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122547",
    2024: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122544",
    2025: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/32122541",
    2026: "/web/guest/cas/ayuntamiento/plenodelayuntamiento/-/categories/36871053",
}

# Crawl sessions from this date onwards
MANDATE_START = date(2011, 1, 1)

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "sessions_index.json"


def fetch_page(url: str) -> BeautifulSoup:
    """Fetch a page and return parsed HTML."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_date_from_url(url: str) -> "date | None":
    """Extract date from URL like /content/2025-01-28 or /content/2025-01-28-1"""
    match = re.search(r"/content/(\d{4}-\d{2}-\d{2})", url)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def extract_sessions(soup: BeautifulSoup) -> list[dict]:
    sessions = []
    seen_urls = set()

    # Find all links that match the asset_publisher pattern for plenary sessions
    pattern = re.compile(r"/asset_publisher/0VsIJqf3efBH/content/\d{4}-\d{2}-\d{2}")

    for a_tag in soup.find_all("a", href=pattern):
        href = a_tag["href"]
        if href in seen_urls:
            continue
        seen_urls.add(href)

        full_url = BASE_URL + href if href.startswith("/") else href
        session_date = extract_date_from_url(href)

        if session_date is None or session_date < MANDATE_START:
            continue

        # Extract type from link text (Ordinaria, Extraordinaria, Urgent)
        text = a_tag.get_text(strip=True)
        tipo = "ordinaria"
        if "extraordinari" in text.lower():
            tipo = "extraordinaria"
        elif "urgent" in text.lower():
            tipo = "urgent"

        sessions.append({
            "id": re.search(r"/content/(.+)$", href).group(1),
            "fecha": session_date.isoformat(),
            "tipo": tipo,
            "url_web": full_url,
            "texto_enlace": text,
        })

    return sessions


def main():
    all_sessions = {}
    current_year = date.today().year

    for year in range(MANDATE_START.year, current_year + 1):
        if year not in YEAR_CATEGORIES:
            print(f"  {year}: no category URL known, skipping")
            continue

        url = BASE_URL + YEAR_CATEGORIES[year]
        print(f"  Fetching {year}...")
        try:
            soup = fetch_page(url)
            page_sessions = extract_sessions(soup)

            new = 0
            for s in page_sessions:
                if s["id"] not in all_sessions:
                    all_sessions[s["id"]] = s
                    new += 1

            print(f"  {year}: {len(page_sessions)} sessions found, {new} new")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {year}: ERROR — {e}")

    sessions = sorted(all_sessions.values(), key=lambda s: s["fecha"], reverse=True)
    print(f"\nFound {len(sessions)} sessions since {MANDATE_START}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(sessions, ensure_ascii=False, indent=2))
    print(f"Saved to {OUTPUT_FILE}")

    for s in sessions[:5]:
        print(f"  {s['fecha']} ({s['tipo']}) → {s['id']}")
    if len(sessions) > 5:
        print(f"  ... and {len(sessions) - 5} more")


if __name__ == "__main__":
    main()

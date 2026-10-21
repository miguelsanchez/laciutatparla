#!/usr/bin/env python3
"""
Check for new plenary sessions not yet processed through the pipeline.

Crawls the current-year (and optionally previous-year) category pages on
valencia.es and compares with the local sessions_index.json. Reports:
  - New sessions on the website not yet in the local index
  - Sessions in the index missing PDF / text / interventions

Exit code:
  0 — everything up to date
  1 — new sessions discovered or pipeline gaps found
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from lib.http import fetch_html

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "raw"
SESSION_INDEX = DATA_DIR / "sessions_index.json"
PDFS_DIR = DATA_DIR / "pdfs"
TEXTS_DIR = DATA_DIR / "texts"
INTERVENTIONS_FILE = DATA_DIR / "interventions_raw.json"

BASE_URL = "https://www.valencia.es"
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


def extract_sessions_from_page(soup) -> list[dict]:
    """Extract session entries from a category page."""
    sessions = []
    seen = set()
    pattern = re.compile(r"/asset_publisher/0VsIJqf3efBH/content/(\d{4}-\d{2}-\d{2}(?:-\d+)?)")
    for a in soup.find_all("a", href=pattern):
        m = pattern.search(a["href"])
        if not m:
            continue
        session_id = m.group(1)
        if session_id in seen:
            continue
        seen.add(session_id)
        full_url = BASE_URL + a["href"] if a["href"].startswith("/") else a["href"]
        text = a.get_text(strip=True)
        tipo = "ordinaria"
        if "extraordinari" in text.lower():
            tipo = "extraordinaria"
        elif "urgent" in text.lower():
            tipo = "urgent"
        fecha = session_id[:10]
        sessions.append({"id": session_id, "fecha": fecha, "tipo": tipo, "url_web": full_url})
    return sessions


def crawl_recent_sessions(years_back: int = 1) -> dict[str, dict]:
    """Crawl the current year (and optionally prior years) and return id → session."""
    today = date.today()
    results = {}
    for year in range(today.year - years_back, today.year + 1):
        if year not in YEAR_CATEGORIES:
            print(f"  {year}: no category URL known, skipping")
            continue
        url = BASE_URL + YEAR_CATEGORIES[year]
        print(f"  Crawling {year}...")
        try:
            soup = fetch_html(url)
            sessions = extract_sessions_from_page(soup)
            for s in sessions:
                results[s["id"]] = s
            print(f"  {year}: {len(sessions)} sessions found on website")
        except Exception as exc:
            print(f"  {year}: ERROR — {exc}")
    return results


def load_local_index() -> dict[str, dict]:
    if not SESSION_INDEX.exists():
        return {}
    return {s["id"]: s for s in json.loads(SESSION_INDEX.read_text())}


def load_processed_plenos() -> set[str]:
    if not INTERVENTIONS_FILE.exists():
        return set()
    ivs = json.loads(INTERVENTIONS_FILE.read_text())
    return {iv["pleno_id"] for iv in ivs}


HEADER_PATTERN = re.compile(
    r"INTERVENCI[OÓ]N?S? CIUTADAN[AE]S?", re.IGNORECASE
)
DEDUP_WINDOW = 500


def has_intervention_header(text_path: Path) -> bool:
    """Return True if the text contains any citizen intervention section header."""
    if not text_path.exists():
        return False
    text = text_path.read_text(errors="replace")
    positions = [m.start() for m in HEADER_PATTERN.finditer(text)]
    if not positions:
        return False
    # Deduplicate repeated page-header copies
    deduped = [positions[0]]
    for pos in positions[1:]:
        if pos - deduped[-1] > DEDUP_WINDOW:
            deduped.append(pos)
    return len(deduped) > 0


def pipeline_status(session_id: str, processed_plenos: set[str]) -> dict:
    """Check which pipeline stages have been completed for a session."""
    text_path = TEXTS_DIR / f"{session_id}.txt"
    text_exists = text_path.exists()
    header = has_intervention_header(text_path) if text_exists else None
    extracted = session_id in processed_plenos

    stages = {}
    stages["pdf"] = (PDFS_DIR / f"{session_id}.pdf").exists()
    stages["text"] = text_exists
    # Only flag "interventions" as missing if there are headers but nothing extracted
    if text_exists and header and not extracted:
        stages["interventions (headers found, none extracted)"] = False
    elif text_exists and not header:
        stages["interventions (no headers — normal)"] = True
    else:
        stages["interventions"] = extracted
    return stages


def main():
    print("=== check_new_sessions.py ===\n")

    local = load_local_index()
    processed = load_processed_plenos()
    print(f"Local index: {len(local)} sessions")
    print(f"Processed plenos: {len(processed)}")
    print()

    # ── Crawl recent years ────────────────────────────────────────────────────
    print("Crawling recent years on valencia.es...")
    live = crawl_recent_sessions(years_back=1)
    print()

    # ── New sessions not yet in local index ───────────────────────────────────
    new_sessions = {sid: s for sid, s in live.items() if sid not in local}
    if new_sessions:
        print(f"⚠️  {len(new_sessions)} NEW session(s) not in local index:")
        for sid, s in sorted(new_sessions.items(), reverse=True):
            print(f"  {sid}  ({s['tipo']})")
        print()
    else:
        print("✓  No new sessions discovered.")
        print()

    # ── Pipeline gaps in local index ─────────────────────────────────────────
    gaps = []
    for sid, s in sorted(local.items(), reverse=True):
        st = pipeline_status(sid, processed)
        missing = [k for k, v in st.items() if not v and k != "in_index"]
        if missing:
            gaps.append((sid, missing, s["fecha"]))

    if gaps:
        print(f"⚠️  {len(gaps)} session(s) with pipeline gaps:")
        print(f"  {'Session':20s}  Missing stages")
        print(f"  {'-'*20}  {'-'*30}")
        for sid, missing, fecha in sorted(gaps, reverse=True)[:20]:
            print(f"  {sid:20s}  {', '.join(missing)}")
        if len(gaps) > 20:
            print(f"  ... and {len(gaps) - 20} more")
        print()
    else:
        print("✓  All indexed sessions are fully processed.")
        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    issues = len(new_sessions) + len(gaps)
    if issues:
        print(f"Action needed: {issues} issue(s) found.")
        sys.exit(1)
    else:
        print("All up to date.")
        sys.exit(0)


if __name__ == "__main__":
    main()

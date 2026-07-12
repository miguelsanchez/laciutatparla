#!/usr/bin/env python3
"""
Script 03: Download PDFs for each plenary session.
Prioritizes acta over orden del día.
Output: data/raw/pdfs/{session_id}.pdf
"""

import json
import time
from pathlib import Path

import requests

INPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "sessions_metadata.json"
PDF_DIR = Path(__file__).parent.parent / "data" / "raw" / "pdfs"


def download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF file. Returns True on success."""
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        # Verify it's actually a PDF
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            # Check first bytes
            chunk = next(resp.iter_content(8))
            if not chunk.startswith(b"%PDF"):
                print(f"    WARNING: Not a PDF ({content_type})")
                return False
            dest.write_bytes(chunk + b"".join(resp.iter_content(8192)))
            return True

        with dest.open("wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ERROR downloading: {e}")
        return False


def main():
    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found. Run 02_crawl_sessions.py first.")
        raise SystemExit(1)

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    sessions = json.loads(INPUT_FILE.read_text())
    print(f"Processing {len(sessions)} sessions...")

    downloaded = 0
    skipped = 0
    failed = 0

    for i, session in enumerate(sessions):
        sid = session["id"]
        dest = PDF_DIR / f"{sid}.pdf"

        if dest.exists():
            print(f"  [{i+1}/{len(sessions)}] {sid} — already downloaded")
            skipped += 1
            continue

        url = session.get("url_acta")
        if not url:
            print(f"  [{i+1}/{len(sessions)}] {sid} — no acta available, skipping")
            skipped += 1
            continue

        print(f"  [{i+1}/{len(sessions)}] {sid} — downloading acta...")

        if download_pdf(url, dest):
            size_kb = dest.stat().st_size // 1024
            print(f"    OK ({size_kb} KB)")
            downloaded += 1
        else:
            dest.unlink(missing_ok=True)
            failed += 1

        time.sleep(0.5)

    print(f"\nDone: {downloaded} downloaded, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()

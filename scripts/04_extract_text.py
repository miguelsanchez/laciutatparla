#!/usr/bin/env python3
"""
Script 04: Extract and clean text from downloaded PDFs.
Uses pdftotext (poppler). Removes digital signature noise.
Output: data/raw/texts/{session_id}.txt
"""

import re
import subprocess
from pathlib import Path

PDF_DIR = Path(__file__).parent.parent / "data" / "raw" / "pdfs"
TEXT_DIR = Path(__file__).parent.parent / "data" / "raw" / "texts"

# Patterns to strip (digital signature noise repeated on every page)
NOISE_PATTERNS = [
    # Page header/footer lines
    re.compile(r"^PLE - ACTA DE LA SESS[IÓ].*$", re.MULTILINE),
    re.compile(r"^PLENO - ACTA DE LA SESI[ÓO]N.*$", re.MULTILINE),
    re.compile(r"^CÒPIA INFORMATIVA.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Id\. document:.*$", re.MULTILINE),
    re.compile(r"^En aquest document.*\n.*omesos.*\n.*\(UE\) 2016/679\.", re.MULTILINE),
    re.compile(r"^En este documento.*\n.*omitidos.*\n.*\(UE\) 2016/679\.", re.MULTILINE),
    # Digital signature block (various formats)
    re.compile(
        r"Signat electrònicament per:.*?(?=\n\n|\Z)",
        re.DOTALL
    ),
    re.compile(r"^Firmado electr[oó]nicamente.*?(?=\n\n|\Z)", re.MULTILINE | re.DOTALL),
    # Page numbers (standalone number on a line)
    re.compile(r"^\s*\d+\s*$", re.MULTILINE),
    # Certificate metadata lines
    re.compile(r"^(Antefirma|Nom|Data|Emissor cert|Núm\. sèrie cert)\s*$", re.MULTILINE),
    re.compile(r"^(SECRETARI GENERAL|HILARIO LLAVADOR|ACCVCA-120|16898817|29885324).*$", re.MULTILINE),
    # Tabular signature block: "- SECRETARIA GENERAL I DEL   HILARIO LLAVADOR   date   cert   number"
    re.compile(r"^[–\-]\s*SECRETAR[IÀ]A?\s+GENERAL.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^PLE\s{5,}\d[\d\s]*$", re.MULTILINE),
    # ACCV certificate references with long numbers
    re.compile(r"\bACCV(?:CA)?[-\s]?\d+\b.*\d{10,}.*$", re.MULTILINE),
    re.compile(r"^\d{17,}\s*$", re.MULTILINE),  # Long certificate serial numbers
    # Page form feed characters
    re.compile(r"\f"),
]


def extract_text(pdf_path: Path) -> str:
    """Run pdftotext and return raw text."""
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout


def clean_text(raw: str) -> str:
    """Remove digital signature noise and normalize whitespace."""
    text = raw

    for pattern in NOISE_PATTERNS:
        text = pattern.sub("", text)

    # Collapse multiple blank lines into at most two
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)

    return text.strip()


def has_interventions(text: str) -> bool:
    return "INTERVENCIONS CIUTADANES" in text or "INTERVENCIONES CIUDADANAS" in text


def main():
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {PDF_DIR}. Run 03_download_pdfs.py first.")
        raise SystemExit(1)

    print(f"Processing {len(pdfs)} PDFs...")
    processed = 0
    skipped = 0
    with_interventions = 0

    for i, pdf_path in enumerate(pdfs):
        sid = pdf_path.stem
        dest = TEXT_DIR / f"{sid}.txt"

        if dest.exists():
            print(f"  [{i+1}/{len(pdfs)}] {sid} — already extracted")
            skipped += 1
            if has_interventions(dest.read_text()):
                with_interventions += 1
            continue

        print(f"  [{i+1}/{len(pdfs)}] {sid} — extracting...", end=" ")
        try:
            raw = extract_text(pdf_path)
            cleaned = clean_text(raw)
            dest.write_text(cleaned, encoding="utf-8")

            has_iv = has_interventions(cleaned)
            if has_iv:
                with_interventions += 1
            print(f"OK ({len(cleaned)} chars{'  ✓ interventions' if has_iv else ''})")
            processed += 1
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone: {processed} extracted, {skipped} skipped")
    print(f"Sessions with citizen interventions: {with_interventions}")


if __name__ == "__main__":
    main()

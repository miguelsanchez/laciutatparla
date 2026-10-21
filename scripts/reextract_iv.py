#!/usr/bin/env python3
"""One-off: re-extract a specific intervention block via script 05's prompt+pipeline.

Usage: REEXTRACT_ID=2017-04-27-004 BLOCK_INDEX=4 python3 reextract_iv.py
"""
from __future__ import annotations
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data" / "raw" / "interventions_raw.json"
TEXT_DIR = ROOT / "data" / "raw" / "texts"

# Import script 05 as a module
spec = importlib.util.spec_from_file_location("s5", Path(__file__).parent / "05_parse_interventions.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main():
    iv_id = os.environ.get("REEXTRACT_ID")
    block_idx_str = os.environ.get("BLOCK_INDEX")
    if not iv_id or not block_idx_str:
        print("Usage: REEXTRACT_ID=<id> BLOCK_INDEX=<n> python3 reextract_iv.py")
        sys.exit(1)
    block_idx = int(block_idx_str)
    pleno_id = iv_id.rsplit("-", 1)[0]
    text_path = TEXT_DIR / f"{pleno_id}.txt"
    text = text_path.read_text(encoding="utf-8")

    secs = m.split_intervention_sections(text)
    all_blocks = []
    for s in secs:
        all_blocks.extend(m.extract_intervention_blocks(s))
    print(f"Found {len(all_blocks)} blocks in {pleno_id}")
    if block_idx > len(all_blocks):
        print(f"BLOCK_INDEX {block_idx} out of range")
        sys.exit(1)
    block = all_blocks[block_idx - 1]
    print(f"Block {block_idx}: {len(block)} chars")
    print(f"Head: {block[:200]!r}")
    print()

    print(f"Calling Claude to extract...")
    result = m.parse_block_with_claude(block, pleno_id, block_idx)
    if not result:
        print("FAILED")
        sys.exit(1)
    print(f"OK: {result.get('intervinient')} ({result.get('entitat')}) — idioma={result.get('idioma_original')}")
    print(f"   text_original: {len(result.get('text_original') or '')}c")
    print(f"   text_cas: {len(result.get('text_cas') or '')}c")
    print(f"   text_val: {len(result.get('text_val') or '')}c")

    # Ensure ID matches target
    result["id"] = iv_id

    # Replace in raw data
    raw = json.loads(DATA.read_text())
    found = False
    for i, iv in enumerate(raw):
        if iv["id"] == iv_id:
            raw[i] = result
            found = True
            break
    if not found:
        print(f"WARNING: {iv_id} not found in raw data; appending")
        raw.append(result)
    DATA.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"\nSaved.")


if __name__ == "__main__":
    main()

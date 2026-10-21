#!/usr/bin/env python3
"""
Classify interventions with Comparative Agendas Project (CAP) codes.
Adds cap_major (list of major topic codes) and cap_subtopics (list of
4-digit subtopic codes) to each intervention.

Uses Claude Haiku. Idempotent: skips already-processed.
"""
import json
import os
import re
import time
from pathlib import Path

import anthropic

for p in [Path(".env"), Path(__file__).parent.parent / ".env"]:
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
        break

os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC", "")
client = anthropic.Anthropic()

INTERVENTIONS_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"

# CAP codebook subset relevant for municipal politics (single source: scripts/lib/taxonomy.json)
from lib import taxonomy  # noqa: E402

CAP_CODEBOOK = taxonomy.cap_codebook_full()

PROMPT = """Analitza el text d'esta intervenció ciutadana d'un ple de l'Ajuntament de València i classifica-la usant la taxonomia CAP (Comparative Agendas Project).

""" + CAP_CODEBOOK + """

Assigna entre 1 i 4 subtopic codes (codis de 3-4 dígits) que millor descriuen el contingut de la intervenció. Pot ser d'un sol major topic o de diversos.

Respon ÚNICAMENT amb els codis numèrics separats per coma, sense explicacions. Exemple: "1001, 1002, 705" o "1401, 201"

Intervinient: {intervinient}
Entitat: {entitat}
Text:
{text}"""


def classify(text, intervinient, entitat):
    clean = text.replace("**", "")[:8000]
    for attempt in range(5):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                messages=[{"role": "user", "content": PROMPT.format(
                    text=clean, intervinient=intervinient, entitat=entitat
                )}],
            )
            result = msg.content[0].text.strip()
            # Extract numbers
            codes = [int(c) for c in re.findall(r'\b\d{3,4}\b', result)]
            # Deduplicate, keep order
            seen = set()
            deduped = []
            for c in codes:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)
            return deduped
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f" [rate limit, {wait}s]", end="", flush=True)
                time.sleep(wait)
            else:
                raise
    return []


def main():
    ivs = json.loads(INTERVENTIONS_FILE.read_text())

    targets = []
    for i, iv in enumerate(ivs):
        if "cap_subtopics" in iv and iv["cap_subtopics"]:
            continue
        text = iv.get("text_original") or iv.get("text_cas") or iv.get("text_val") or ""
        if len(text) < 30:
            continue
        targets.append((i, iv))

    print(f"Classifying {len(targets)} interventions with CAP codes")

    for idx, (i, iv) in enumerate(targets):
        text = iv.get("text_original") or iv.get("text_cas") or iv.get("text_val") or ""
        print(f"[{idx+1}/{len(targets)}] {iv['id']} — {iv.get('intervinient','')[:35]}", end="", flush=True)

        codes = classify(text, iv.get("intervinient", ""), iv.get("entitat", ""))
        iv["cap_subtopics"] = codes
        # Derive major topics: first 1-2 digits
        majors = sorted(set(c // 100 if c < 1000 else c // 100 for c in codes))
        iv["cap_major"] = majors

        print(f" — subtopics: {codes}, majors: {majors}")

        time.sleep(0.2)
        INTERVENTIONS_FILE.write_text(json.dumps(ivs, ensure_ascii=False, indent=2))

    print(f"\nDone. Processed: {len(targets)}")


if __name__ == "__main__":
    main()

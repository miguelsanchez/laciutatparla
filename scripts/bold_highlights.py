#!/usr/bin/env python3
"""
Add bold highlights to intervention texts using Claude Haiku.
Processes text_cas and text_val for each intervention, marking key phrases
with **double asterisks**. Saves progress after each intervention.
"""
import json
import os
import time
from pathlib import Path

import anthropic
import httpx

# Load .env
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC", "")
client = anthropic.Anthropic(http_client=httpx.Client(trust_env=False))

INTERVENTIONS_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"

PROMPT = """Dado el siguiente texto de una intervención ciudadana en un pleno municipal, devuelve EXACTAMENTE el mismo texto pero marcando con **doble asterisco** (negrita markdown) las palabras o frases cortas que representan las ideas clave, reivindicaciones principales, datos relevantes (cifras, fechas, nombres de lugares) o conceptos centrales del discurso.

Reglas:
- Marca entre 8 y 15 fragmentos por cada 1000 caracteres de texto
- Cada fragmento marcado debe ser corto: entre 1 y 6 palabras
- NO cambies ni una sola palabra del texto original
- NO añadas ni elimines texto
- Mantén los saltos de línea exactamente igual
- Devuelve SOLO el texto modificado, sin explicaciones

TEXTO:
{text}"""


def add_bolds(text: str) -> str:
    """Send text to Haiku and return with bold markers."""
    if not text or len(text) < 50:
        return text
    for attempt in range(5):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8096,
                messages=[{"role": "user", "content": PROMPT.format(text=text)}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f" [rate limit, waiting {wait}s]", end="", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Rate limit exceeded after 5 retries")


def main():
    ivs = json.loads(INTERVENTIONS_FILE.read_text())
    total = len(ivs)
    processed = 0
    skipped = 0

    for i, iv in enumerate(ivs):
        iv_id = iv["id"]
        original = iv.get("text_original", "") or ""
        cas = iv.get("text_cas", "") or ""
        val = iv.get("text_val", "") or ""
        needs_orig = original and "**" not in original
        needs_cas = cas and "**" not in cas
        needs_val = val and "**" not in val

        if not needs_orig and not needs_cas and not needs_val:
            skipped += 1
            continue

        processed += 1
        print(f"[{i+1}/{total}] {iv_id} — {iv.get('intervinient','')[:35]}", end="")

        try:
            if needs_orig:
                iv["text_original"] = add_bolds(original)
                print(f" — orig OK", end="")
                time.sleep(0.2)

            if needs_cas:
                iv["text_cas"] = add_bolds(cas)
                print(f" — cas OK", end="")
                time.sleep(0.2)

            if needs_val:
                iv["text_val"] = add_bolds(val)
                print(f" — val OK", end="")
                time.sleep(0.2)

            print()

            # Save after each intervention
            INTERVENTIONS_FILE.write_text(json.dumps(ivs, ensure_ascii=False, indent=2))

        except Exception as e:
            print(f" — ERROR: {e}")
            # Save what we have so far
            INTERVENTIONS_FILE.write_text(json.dumps(ivs, ensure_ascii=False, indent=2))
            print(f"\nSaved progress. Re-run to continue from where we left off.")
            raise

    print(f"\nDone. Processed: {processed}, Skipped (already done): {skipped}")


if __name__ == "__main__":
    main()

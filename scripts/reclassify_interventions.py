#!/usr/bin/env python3
"""
Reclassify all interventions with:
1. Two-level thematic taxonomy (category > subcategory)
2. Geographic scope (ambit + normalized zones + districtes)

Uses Claude Haiku. Idempotent: skips already-processed entries.
Saves progress after each intervention.
"""
import json
import os
import re
import time
from pathlib import Path

import anthropic

# Load .env
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC", "")
client = anthropic.Anthropic()

INTERVENTIONS_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"
BARRIS_FILE = Path(__file__).parent.parent / "data" / "raw" / "barris_referencia.json"

# Load barri reference for the prompt
barris_ref = json.loads(BARRIS_FILE.read_text())
barris_list = "\n".join(
    f"  {b['districte_nom']} > {b['nom']}" for b in barris_ref
)

# Taxonomy (single source: scripts/lib/taxonomy.json). Until F1.1 this prompt carried its own,
# outdated copy (bici_vianants, feminisme, cultura_i_participacio…), so a re-run wrote
# categories the rest of the pipeline rejects.
from lib import taxonomy  # noqa: E402

PROMPT = """Ets un expert en política municipal valenciana. Analitza el text d'esta intervenció ciutadana en un ple de l'Ajuntament de València i classifica-la en DOS eixos:

## 1. TEMES (taxonomia a dos nivells)

Assigna UNA O MÉS categories principals, cadascuna amb 1-3 subcategories. Màxim 3 categories principals per intervenció.

Categories i subcategories disponibles:

""" + taxonomy.taxonomy_text_described() + """

## 2. ÀMBIT GEOGRÀFIC

Determina a quin àmbit territorial es refereix la intervenció.

Valors possibles per a "ambit":
  barri — parla d'un sol barri concret
  districte — parla d'un districte sencer
  multi_barri — parla de diversos barris concrets
  multi_districte — parla de diversos districtes
  ciutat — parla de València en general, sense referència territorial específica
  area_metropolitana — fa referència a zones fora del terme municipal
  no_especificat — no hi ha referència geogràfica clara

Per a "zones", usa els noms oficials d'esta llista de barris de València:
""" + barris_list + """

Si el barri mencionat no està en la llista (pedanies, zones informals), usa el nom tal com apareix al text.

## FORMAT DE RESPOSTA

Respon ÚNICAMENT amb un JSON amb esta estructura exacta:
{{
  "temes": {{
    "categoria_principal": ["subcategoria1", "subcategoria2"]
  }},
  "ambit": "barri|districte|multi_barri|multi_districte|ciutat|area_metropolitana|no_especificat",
  "zones": ["nom oficial del barri"],
  "districtes": ["nom oficial del districte"]
}}

Exemples:
- Intervenció sobre supermanzana de la Petxina: {{"temes": {{"urbanisme": ["espai_public"], "mobilitat": ["transit", "mobilitat_activa"]}}, "ambit": "barri", "zones": ["La Petxina"], "districtes": ["Extramurs"]}}
- Intervenció sobre ZBE a tota la ciutat: {{"temes": {{"mobilitat": ["zbe"], "medi_ambient": ["contaminacio"]}}, "ambit": "ciutat", "zones": [], "districtes": []}}

## TEXT DE LA INTERVENCIÓ

Intervinient: {intervinient}
Entitat: {entitat}
Text:
{text}"""


def classify(iv: dict) -> dict:
    """Send intervention to Haiku for classification."""
    text = iv.get("text_original") or iv.get("text_cas") or iv.get("text_val") or ""
    if not text or len(text) < 30:
        return {"temes": {}, "ambit": "no_especificat", "zones": [], "districtes": []}

    # Strip bold markers for cleaner classification
    clean_text = text.replace("**", "")

    prompt = PROMPT.format(
        intervinient=iv.get("intervinient", ""),
        entitat=iv.get("entitat", ""),
        text=clean_text[:15000],
    )

    for attempt in range(5):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            response = msg.content[0].text.strip()
            response = re.sub(r"^```(?:json)?\n?", "", response)
            response = re.sub(r"\n?```$", "", response)
            data = json.loads(response)
            return data
        except json.JSONDecodeError as e:
            print(f" [JSON error: {e}]", end="", flush=True)
            return None
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f" [rate limit, waiting {wait}s]", end="", flush=True)
                time.sleep(wait)
            else:
                raise
    return None


def main():
    ivs = json.loads(INTERVENTIONS_FILE.read_text())
    total = len(ivs)
    processed = 0
    skipped = 0

    for i, iv in enumerate(ivs):
        # Skip if already reclassified
        if isinstance(iv.get("temes_v2"), dict) and iv.get("ambit"):
            skipped += 1
            continue

        processed += 1
        print(f"[{i+1}/{total}] {iv.get('id','')} — {iv.get('intervinient','')[:35]}", end="", flush=True)

        result = classify(iv)
        if result:
            iv["temes_v2"] = result.get("temes", {})
            iv["ambit"] = result.get("ambit", "no_especificat")
            iv["zones"] = result.get("zones", [])
            iv["districtes"] = result.get("districtes", [])
            print(f" — {len(iv['temes_v2'])} cats, ambit={iv['ambit']}", flush=True)
        else:
            print(" — FAILED", flush=True)

        time.sleep(0.3)

        # Save after each intervention
        INTERVENTIONS_FILE.write_text(json.dumps(ivs, ensure_ascii=False, indent=2))

    print(f"\nDone. Processed: {processed}, Skipped (already done): {skipped}")


if __name__ == "__main__":
    main()

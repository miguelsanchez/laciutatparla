#!/usr/bin/env python3
"""
Backfill script: classify + CAP codes + bold highlights in ONE API call.
Processes interventions that are missing temes_v2, cap_subtopics, or bold markers.
Idempotent: skips already-complete entries. Saves after each intervention.

Taxonomy source of truth: web/src/utils/labels.ts
"""
import json
import os
import re
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
BARRIS_FILE = Path(__file__).parent.parent / "data" / "raw" / "barris_referencia.json"

barris_ref = json.loads(BARRIS_FILE.read_text()) if BARRIS_FILE.exists() else []
BARRIS_LIST = "\n".join(f"  {b['districte_nom']} > {b['nom']}" for b in barris_ref)

# ── Canonical taxonomy (source: web/src/utils/labels.ts) ───────────────────

VALID_TAXONOMY = {
    "urbanisme": ["espai_public", "habitatge", "patrimoni", "usos_turistics"],
    "mobilitat": ["transit", "transport_public", "zbe", "mobilitat_activa", "aparcament"],
    "medi_ambient": ["contaminacio", "zones_verdes", "emergencies_climatiques", "dana_2024", "benestar_animal"],
    "serveis_publics": ["educacio", "salut", "serveis_socials", "seguretat", "esports"],
    "economia": ["pressupostos", "comerc_ocupacio", "agricultura"],
    "drets_i_igualtat": ["diversitat", "interculturalitat_i_antiracisme", "igualtat_de_genere", "drets_humans", "drets_linguistics"],
    "persones": ["joventut", "gent_major"],
    "cultura": ["festes", "patrimoni_cultural", "associacionisme"],
    "participacio": ["participacio", "processos_participatius", "transparencia", "consells_sectorials"],
}

VALID_CATS = set(VALID_TAXONOMY.keys())
VALID_SUBS = {}
for cat, subs in VALID_TAXONOMY.items():
    for s in subs:
        VALID_SUBS[s] = cat

VALID_AMBITS = {"barri", "districte", "multi_barri", "multi_districte", "ciutat", "area_metropolitana", "no_especificat"}

# Build taxonomy text for prompt
TAXONOMY_TEXT = "\n".join(
    f"{cat}: {', '.join(subs)}" for cat, subs in VALID_TAXONOMY.items()
)

CAP_CODEBOOK = """2 Civil Rights: 201 Minority, 202 Gender, 204 Age, 205 Handicap, 207 Speech
3 Health: 300 General, 301 Reform, 322 Facilities, 331 Prevention, 332 Children, 334 Long-term
4 Agriculture: 400 General, 402 Subsidies, 403 Food Safety, 405 Animal Welfare
5 Labor: 500 General, 501 Safety, 502 Training, 506 Youth Employment
6 Education: 600 General, 601 Higher, 602 Primary/Secondary, 603 Underprivileged, 606 Special
7 Environment: 700 General, 701 Water, 703 Waste, 705 Air/Noise, 707 Recycling, 709 Parks/Trees, 711 Climate/Flooding
9 Immigration: 900 General
10 Transport: 1000 General, 1001 Mass Transit, 1002 Traffic/Roads, 1010 Bike/Pedestrian
12 Law/Crime: 1200 General, 1201 Police, 1203 Drugs, 1206 Juvenile, 1208 Family
13 Social Welfare: 1300 General, 1302 Low-Income, 1303 Elderly, 1304 Disabled, 1305 Volunteering, 1308 Childcare
14 Housing: 1400 General, 1401 Public Space, 1403 Urban Dev, 1406 Low-Income Housing, 1409 Homeless
15 Commerce: 1500 General, 1521 Small Business, 1525 Consumer, 1526 Sports/Tourism
19 International: 1906 Human Rights, 1925 Peace/Solidarity
20 Government: 2000 General, 2001 Intergovernmental, 2004 Employees, 2015 Transparency
21 Public Lands: 2100 General, 2104 Water Resources
23 Culture: 2300 Heritage/Arts/Language/Festivals/Sports"""

PROMPT = """Analitza esta intervenció ciutadana d'un ple de l'Ajuntament de València. Has de fer TRES tasques en una sola resposta JSON:

## 1. CLASSIFICACIÓ TEMÀTICA (temes_v2) — Màxim 3 categories

IMPORTANT: Usa ÚNICAMENT les categories i subcategories d'esta llista tancada. NO inventes categories ni subcategories noves.

{taxonomy}

Cada subcategoria pertany ÚNICAMENT a la seua categoria. Per exemple, "educacio" només pot anar dins "serveis_publics", "agricultura" dins "economia", "esports" dins "serveis_publics".

## 2. ÀMBIT GEOGRÀFIC

Valors (ÚNICAMENT un d'estos): barri | districte | multi_barri | multi_districte | ciutat | area_metropolitana | no_especificat

Barris oficials:
{barris}

## 3. CODIS CAP (1-4 subtopic codes numèrics)
{cap}

## 4. NEGRETES (bold highlights)

Marca amb **doble asterisc** les paraules o frases curtes (1-6 paraules) que representen idees clau, reivindicacions, dades rellevants o conceptes centrals. Entre 8 i 15 fragments per cada 1000 caràcters. NO canvies ni una paraula del text original.

## RESPOSTA — JSON exacte:
{{
  "temes_v2": {{"categoria": ["subcategoria1"]}},
  "ambit": "valor",
  "zones": ["barri oficial"],
  "districtes": ["districte oficial"],
  "cap_subtopics": [1001, 705],
  "text_original_bold": "text original amb **negretes**",
  "text_translation_bold": "text traducció amb **negretes**"
}}

## INTERVENCIÓ
Intervinient: {intervinient}
Entitat: {entitat}

Text original ({idioma}):
{text_original}

Traducció ({trad_lang}):
{text_translation}

Respon ÚNICAMENT amb el JSON."""


def validate_temes(raw: dict) -> dict:
    """Force temes_v2 into the canonical taxonomy. Drop invalid keys."""
    result = {}
    if not isinstance(raw, dict):
        return result
    for cat, subs in raw.items():
        # Normalize category name
        cat_clean = cat.strip().lower()
        if cat_clean not in VALID_CATS:
            # Try to salvage: maybe it's a subcategory used as category
            if cat_clean in VALID_SUBS:
                real_cat = VALID_SUBS[cat_clean]
                if real_cat not in result:
                    result[real_cat] = []
                result[real_cat].append(cat_clean)
            continue
        if cat_clean not in result:
            result[cat_clean] = []
        valid_subs = set(VALID_TAXONOMY[cat_clean])
        if isinstance(subs, list):
            for s in subs:
                s_clean = s.strip().lower()
                if s_clean in valid_subs and s_clean not in result[cat_clean]:
                    result[cat_clean].append(s_clean)
    # Remove categories with no valid subcategories
    return {k: v for k, v in result.items() if v}


def needs_processing(iv: dict) -> bool:
    """Check if intervention needs backfill."""
    has_v2 = isinstance(iv.get("temes_v2"), dict) and iv["temes_v2"]
    has_cap = iv.get("cap_subtopics") and len(iv["cap_subtopics"]) > 0
    orig = iv.get("text_original", "") or ""
    cas = iv.get("text_cas", "") or ""
    val = iv.get("text_val", "") or ""
    has_bold = "**" in orig or "**" in cas or "**" in val
    return not (has_v2 and has_cap and has_bold)


def process(iv: dict) -> bool:
    """Run combined classification + bold in one API call."""
    text_orig = (iv.get("text_original") or "").replace("**", "")
    text_cas = (iv.get("text_cas") or "").replace("**", "")
    text_val = (iv.get("text_val") or "").replace("**", "")
    idioma = iv.get("idioma_original", "castellano")

    if not text_orig and not text_cas and not text_val:
        return False

    if not text_orig:
        text_orig = text_cas or text_val
    translation = text_cas if text_cas else text_val
    trad_lang = "castellano" if text_cas else "valenciano"
    if not translation:
        translation = "(sense traducció)"
        trad_lang = "cap"

    prompt = PROMPT.format(
        taxonomy=TAXONOMY_TEXT,
        barris=BARRIS_LIST,
        cap=CAP_CODEBOOK,
        intervinient=iv.get("intervinient", ""),
        entitat=iv.get("entitat", ""),
        idioma=idioma,
        text_original=text_orig[:12000],
        trad_lang=trad_lang,
        text_translation=translation[:12000],
    )

    for attempt in range(5):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=16000,
                messages=[{"role": "user", "content": prompt}],
            )
            response = msg.content[0].text.strip()
            response = re.sub(r"^```(?:json)?\n?", "", response)
            response = re.sub(r"\n?```$", "", response)
            data = json.loads(response)

            # Validate and apply classification
            iv["temes_v2"] = validate_temes(data.get("temes_v2", {}))

            ambit = data.get("ambit", "no_especificat")
            iv["ambit"] = ambit if ambit in VALID_AMBITS else "no_especificat"

            iv["zones"] = data.get("zones", []) if isinstance(data.get("zones"), list) else []
            iv["districtes"] = data.get("districtes", []) if isinstance(data.get("districtes"), list) else []

            # CAP codes
            cap_raw = data.get("cap_subtopics", [])
            if isinstance(cap_raw, list):
                cap_codes = [int(c) for c in cap_raw if isinstance(c, (int, float, str)) and str(c).isdigit()]
            else:
                cap_codes = [int(c) for c in re.findall(r'\b\d{3,4}\b', str(cap_raw))]
            iv["cap_subtopics"] = cap_codes
            iv["cap_major"] = sorted(set(c // 100 for c in cap_codes))

            # Bold highlights
            bold_orig = data.get("text_original_bold", "")
            bold_trad = data.get("text_translation_bold", "")

            if bold_orig and "**" in bold_orig:
                iv["text_original"] = bold_orig
            if bold_trad and "**" in bold_trad:
                if text_cas:
                    iv["text_cas"] = bold_trad
                elif text_val:
                    iv["text_val"] = bold_trad

            return True

        except json.JSONDecodeError as e:
            print(f" [JSON error: {e}]", end="", flush=True)
            return False
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f" [rate limit, {wait}s]", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" [error: {e}]", end="", flush=True)
                return False
    return False


def main():
    ivs = json.loads(INTERVENTIONS_FILE.read_text())
    targets = [(i, iv) for i, iv in enumerate(ivs) if needs_processing(iv)]

    print(f"Total: {len(ivs)} interventions, {len(targets)} need backfill")
    print(f"Valid categories: {sorted(VALID_CATS)}")

    for idx, (i, iv) in enumerate(targets):
        print(f"[{idx+1}/{len(targets)}] {iv['id']} — {iv.get('intervinient','')[:30]}", end="", flush=True)

        ok = process(iv)
        if ok:
            temes = ",".join(iv.get("temes_v2", {}).keys())
            cap = iv.get("cap_subtopics", [])
            has_bold = "**" in (iv.get("text_original", "") or "")
            print(f" — [{temes}] cap={cap} bold={'Y' if has_bold else 'N'}")
        else:
            print(" — FAILED")

        time.sleep(0.3)
        INTERVENTIONS_FILE.write_text(json.dumps(ivs, ensure_ascii=False, indent=2))

    print(f"\nDone. Processed: {len(targets)}")


if __name__ == "__main__":
    main()

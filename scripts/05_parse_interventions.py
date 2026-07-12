#!/usr/bin/env python3
from __future__ import annotations
"""
Script 05: Parse citizen interventions from extracted text files.
Uses Claude API to extract structured data, classify themes (two-level
taxonomy + CAP codes), geographic scope, and add bold highlights.

All processing in a SINGLE API call per intervention.

Output: data/raw/interventions_raw.json
"""

import json
import os
import re
import time
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv

# Load .env from project root if present
load_dotenv(Path(__file__).parent.parent / ".env")

# Support both ANTHROPIC_API_KEY and ANTHROPIC variable names
_api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC")
if _api_key:
    os.environ["ANTHROPIC_API_KEY"] = _api_key

INPUT_METADATA = Path(__file__).parent.parent / "data" / "raw" / "sessions_metadata.json"
TEXT_DIR = Path(__file__).parent.parent / "data" / "raw" / "texts"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"
BARRIS_FILE = Path(__file__).parent.parent / "data" / "raw" / "barris_referencia.json"

client = anthropic.Anthropic(http_client=httpx.Client(trust_env=False))

# ── Canonical taxonomy (source of truth: web/src/utils/labels.ts) ───────────

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
for _cat, _subs in VALID_TAXONOMY.items():
    for _s in _subs:
        VALID_SUBS[_s] = _cat

VALID_AMBITS = {"barri", "districte", "multi_barri", "multi_districte", "ciutat", "area_metropolitana", "no_especificat"}
VALID_TIPUS = {"av", "plataforma", "ong", "sindical", "cultural", "educacio", "esportiu", "empresa", "particular", "altres"}

TAXONOMY_TEXT = "\n".join(
    f"{cat}: {', '.join(subs)}" for cat, subs in VALID_TAXONOMY.items()
)

# ── Reference data ──────────────────────────────────────────────────────────

barris_ref = json.loads(BARRIS_FILE.read_text()) if BARRIS_FILE.exists() else []
BARRIS_LIST = "\n".join(f"  {b['districte_nom']} > {b['nom']}" for b in barris_ref)

# ── CAP codebook ────────────────────────────────────────────────────────────

CAP_CODEBOOK = """2 Civil Rights: 201 Minority Discrimination, 202 Gender Discrimination, 204 Age Discrimination, 205 Handicap Discrimination, 207 Freedom of Speech
3 Health: 300 General, 301 Reform, 322 Facilities, 331 Prevention, 332 Children, 334 Long-term Care
4 Agriculture: 400 General, 402 Subsidies, 403 Food Safety, 405 Animal Welfare
5 Labor: 500 General, 501 Safety, 502 Training, 506 Youth Employment
6 Education: 600 General, 601 Higher, 602 Primary/Secondary, 603 Underprivileged, 606 Special
7 Environment: 700 General, 701 Water, 703 Waste, 705 Air/Noise Pollution, 707 Recycling, 709 Parks/Trees, 711 Climate/Flooding
9 Immigration: 900 General
10 Transport: 1000 General, 1001 Mass Transit, 1002 Traffic/Roads/Parking, 1010 Bike/Pedestrian
12 Law/Crime: 1200 General, 1201 Police, 1203 Drugs, 1206 Juvenile, 1208 Family
13 Social Welfare: 1300 General, 1302 Low-Income, 1303 Elderly, 1304 Disabled, 1305 Volunteering, 1308 Childcare
14 Housing: 1400 General, 1401 Public Space/Urban Planning, 1403 Urban Development, 1406 Low-Income Housing, 1409 Homeless
15 Commerce: 1500 General, 1521 Small Business, 1525 Consumer Safety, 1526 Sports/Tourism
19 International: 1906 Human Rights, 1925 Peace/Solidarity
20 Government: 2000 General, 2001 Intergovernmental, 2004 Employees, 2015 Transparency/Accountability
21 Public Lands: 2100 General, 2104 Water Resources
23 Culture: 2300 Heritage/Arts/Language/Festivals/Sports"""

# Build set of valid CAP codes for validation
VALID_CAP_CODES = set()
for _code in re.findall(r'\b(\d{3,4})\b', CAP_CODEBOOK):
    VALID_CAP_CODES.add(int(_code))

# ── Extraction + classification + bold prompt (single call) ─────────────────

EXTRACTION_PROMPT = """Ets un expert en actes de plens municipals valencians.
Analitza el següent bloc d'intervenció ciutadana extret d'una acta del Ple de l'Ajuntament de València.

Extreu la informació en format JSON amb EXACTAMENT esta estructura:
{{
  "intervinient": "Nom complet de la persona que intervé",
  "entitat": "Nom de l'entitat que representa (tal com apareix al text)",
  "tipus_entitat": "un de: av | plataforma | ong | sindical | cultural | educacio | esportiu | empresa | particular | altres",
  "barri_o_zona": "barri, pedania o zona de la ciutat a la que fa referència (null si no s'especifica)",
  "punts_ordre_dia": "descripció dels punts del orde del dia als que fa referència",
  "idioma_original": "un de: valenciano | castellano | mixt",
  "text_original": "transcripció literal del discurs ÚNICAMENT de l'intervinient (sense el preàmbul de la presidència, sense cometes). Divideix el text en paràgrafs separats per \\n quan hi haja un canvi de tema. Marca amb **doble asterisc** les paraules o frases curtes (1-6 paraules) que representen idees clau, reivindicacions, dades rellevants o conceptes centrals del discurs (entre 8 i 15 fragments per cada 1000 caràcters). NO canvies cap paraula del text original. IMPORTANT: si el text conté noms censurats amb asteriscs (******, *****, etc.) substitueix-los per [***] però MAI els elimines.",
  "resum_cas": "resum de 1-2 frases en castellano",
  "resum_val": "resum de 1-2 frases en valencià",
  "text_cas": "NOMÉS si idioma_original és valenciano o mixt: traducció al castellano amb **negretes** en les mateixes frases clau que text_original. Si ja és castellano: cadena buida",
  "text_val": "NOMÉS si idioma_original és castellano o mixt: traducció al valencià amb **negretes** en les mateixes frases clau que text_original. Si ja és valenciano: cadena buida",
  "temes_v2": {{
    "categoria": ["subcategoria1", "subcategoria2"]
  }},
  "ambit": "un de: barri | districte | multi_barri | multi_districte | ciutat | area_metropolitana | no_especificat",
  "zones": ["nom oficial del barri afectat"],
  "districtes": ["nom oficial del districte"],
  "cap_subtopics": [1001, 705]
}}

## TAXONOMIA TEMÀTICA (temes_v2) — Màxim 3 categories principals

IMPORTANT: Usa ÚNICAMENT les categories i subcategories d'esta llista tancada. NO inventes categories ni subcategories noves.

""" + TAXONOMY_TEXT + """

Cada subcategoria pertany ÚNICAMENT a la seua categoria. Per exemple, "educacio" només pot anar dins "serveis_publics", "agricultura" dins "economia", "esports" dins "serveis_publics".

## ÀMBIT GEOGRÀFIC — Barris oficials de València:
""" + BARRIS_LIST + """

Si el barri no està en la llista, usa el nom tal com apareix al text.

## CODIS CAP (Comparative Agendas Project) — Assigna 1-4 subtopic codes:
""" + CAP_CODEBOOK + """

Usa ÚNICAMENT codis d'esta llista. Si cap subtopic encaixa bé, usa el codi general (acabat en 00) de la major topic més propera.

BLOC D'INTERVENCIÓ:
---
{bloc}
---

Respon ÚNICAMENT amb el JSON, sense cap altra explicació."""

# ── Section / block extraction ──────────────────────────────────────────────


def _has_citizen_interventions(text: str) -> bool:
    """Quick check: does this text contain citizen intervention sections?"""
    # Formal header (post-2014 actas) — uppercase only to avoid matching generic prose
    if re.search(r"INTERVENCI(?:ONS\s+CIUTADANES|Ó\s+CIUTADANA|ONES\s+CIUDADANAS|ÓN\s+CIUDADANA)", text):
        return True
    # Boilerplate without formal header (pre-2015 Barberá era)
    if re.search(r"concede\s+(?:el\s+uso\s+de\s+la\s+palabra|l'ús\s+de\s+la\s+paraula).{0,300}?Reglamento\s+de\s+Participación\s+Ciudadana", text, re.IGNORECASE | re.DOTALL):
        return True
    return False


def split_intervention_sections(text: str) -> list[str]:
    """Split text into sections by intervention markers.

    Supports two formats:
    1. Formal header: INTERVENCIONS CIUTADANES / INTERVENCIONES CIUDADANAS / INTERVENCIÓ CIUTADANA / INTERVENCIÓN CIUDADANA
    2. Boilerplate (pre-2015): "concede el uso de la palabra...en cumplimiento...Reglamento de Participación Ciudadana"
    """
    # Try formal headers first (uppercase only — lowercase variants are generic prose)
    header_pattern = re.compile(
        r"INTERVENCI(?:ONS\s+CIUTADANES|Ó\s+CIUTADANA|ONES\s+CIUDADANAS|ÓN\s+CIUDADANA)",
    )
    matches = list(header_pattern.finditer(text))

    # If no formal headers, try boilerplate pattern (Barberá era)
    if not matches:
        boilerplate_pattern = re.compile(
            r"concede\s+(?:el\s+uso\s+de\s+la\s+palabra|l'ús\s+de\s+la\s+paraula).{0,300}?"
            r"(?:Reglamento\s+de\s+Participación\s+Ciudadana|Reglament\s+de\s+Participació\s+Ciutadana)",
            re.IGNORECASE | re.DOTALL,
        )
        matches = list(boilerplate_pattern.finditer(text))

    if not matches:
        return []

    sections = []
    for i, match in enumerate(matches):
        pos = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[pos:end]

        # Find where DEBAT starts (that's where the section ends)
        debate_match = re.search(r"\n\s*DEBAT(?:E|/DEBATE)?\s*$", section_text, re.MULTILINE)
        if debate_match:
            section_text = section_text[:debate_match.start()]

        # Trim at separator after the citizen's closing quote
        # For boilerplate sections (singular by nature) and singular header sections
        is_singular = "INTERVENCIONS" not in match.group().upper() and "INTERVENCIONES" not in match.group().upper()
        if is_singular:
            quote_close = re.search(r'["\u201d]\n', section_text)
            if quote_close:
                post_quote = section_text[quote_close.end():]
                outro = re.search(r'\n(?:Sra?\.?\s*(?:Presidenta|Alcaldessa|Alcaldesa)|_{5,}|\nACORD|\nVOTACIÓ)', post_quote)
                if outro:
                    section_text = section_text[:quote_close.end() + outro.start()]

        sections.append(section_text.strip())

    return sections


def extract_intervention_blocks(section: str) -> list[str]:
    """Extract individual intervention blocks from a section."""
    blocks = []

    # Pattern 1: "Name (Entity):" headers
    multi_pattern = re.compile(
        r"((?:[–\-]\s+|(?:Sr\.|Sra\.|Sr |Sra |D\.\s*|Dª\s*)\s*)[\wÀ-ÿ][\wÀ-ÿ ,\.'\-]{2,}\([^)]+\)[ \t]*:"
        r"|^[\wÀ-ÿ][\wÀ-ÿ ,\.'\-]{2,}\([^)]+\)[ \t]*:)",
        re.IGNORECASE | re.MULTILINE,
    )
    multi_matches = list(multi_pattern.finditer(section))

    if len(multi_matches) > 0:
        for i, match in enumerate(multi_matches):
            start = match.start()
            end = multi_matches[i + 1].start() if i + 1 < len(multi_matches) else len(section)
            blocks.append(section[start:end].strip())
        return blocks

    # Pattern 2: Bilingual intro format
    bilingual_pat = re.compile(
        r"(?:(?:En\s+(?:primer|segon|tercer|quart|cinquè|sisè|setè|vuitè)\s+lloc"
        r"|A\s+continuació|Primer\s+lloc|Seguidament|Per\s+últim|Finalment)[,\s]+(?:intervé\w*|intervenen)\s"
        r"|^(?:Intervé\w*|Intervenen)\s)",
        re.IGNORECASE | re.MULTILINE,
    )
    bilingual_matches = list(bilingual_pat.finditer(section))

    if len(bilingual_matches) >= 2:
        for i, match in enumerate(bilingual_matches):
            start = match.start()
            end = bilingual_matches[i + 1].start() if i + 1 < len(bilingual_matches) else len(section)
            blocks.append(section[start:end].strip())
        return blocks

    # Pattern 3: Sra. Presidenta format (debate-de-la-ciudad)
    presidenta_pat = re.compile(r"^Sra\.?\s*Presidenta\s*$", re.IGNORECASE | re.MULTILINE)
    presidenta_matches = list(presidenta_pat.finditer(section))

    if len(presidenta_matches) >= 2:
        boilerplate_m = re.search(r"Abans de donar\s+come[nN]çament", section, re.IGNORECASE)
        if boilerplate_m:
            window = section[boilerplate_m.start(): boilerplate_m.start() + 800]
            is_single_entity = bool(re.search(r"en representaci", window, re.IGNORECASE))
        else:
            is_single_entity = False

        if not is_single_entity:
            for i, match in enumerate(presidenta_matches):
                start = match.start()
                end = presidenta_matches[i + 1].start() if i + 1 < len(presidenta_matches) else len(section)
                block = section[start:end].strip()
                if block:
                    blocks.append(block)
            return blocks

    # Pattern 4: Single entity with quoted speech
    quote_match = re.search(r'[\u201c"][^\u201d"]{20,}', section, re.DOTALL)
    if quote_match:
        blocks.append(section.strip())
        return blocks

    # Pattern 5: Sra. Presidenta introduces a single speaker
    if presidenta_matches:
        blocks.append(section.strip())

    return blocks


# ── Validation ──────────────────────────────────────────────────────────────


def validate_temes(raw: dict) -> dict:
    """Force temes_v2 into the canonical taxonomy. Drop invalid keys."""
    result = {}
    if not isinstance(raw, dict):
        return result
    for cat, subs in raw.items():
        cat_clean = cat.strip().lower()
        if cat_clean not in VALID_CATS:
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
    return {k: v for k, v in result.items() if v}


def validate_response(data: dict) -> list[str]:
    """Validate extracted data against canonical values. Returns error messages."""
    errors = []
    temes = data.get("temes_v2", {})
    if isinstance(temes, dict):
        for cat, subs in temes.items():
            if cat not in VALID_CATS:
                errors.append(f"temes_v2: categoria '{cat}' no vàlida. Vàlides: {', '.join(sorted(VALID_CATS))}")
            elif isinstance(subs, list):
                valid = set(VALID_TAXONOMY[cat])
                for s in subs:
                    if s not in valid:
                        errors.append(f"temes_v2: subcategoria '{s}' no vàlida per a '{cat}'. Vàlides: {', '.join(sorted(valid))}")
    ambit = data.get("ambit", "")
    if ambit not in VALID_AMBITS:
        errors.append(f"ambit '{ambit}' no vàlid. Vàlids: {', '.join(sorted(VALID_AMBITS))}")
    for code in data.get("cap_subtopics", []):
        if isinstance(code, (int, float)) and int(code) not in VALID_CAP_CODES:
            errors.append(f"cap_subtopic {int(code)} no existeix al codebook")
    tipus = data.get("tipus_entitat", "")
    if tipus and tipus not in VALID_TIPUS:
        errors.append(f"tipus_entitat '{tipus}' no vàlid. Vàlids: {', '.join(sorted(VALID_TIPUS))}")
    idioma = data.get("idioma_original", "")
    if idioma and idioma not in ("valenciano", "castellano", "mixt"):
        errors.append(f"idioma_original '{idioma}' no vàlid")
    return errors


# ── API calls ───────────────────────────────────────────────────────────────


def _api_call(messages: list[dict], max_tokens: int = 8096) -> str | None:
    """Single Haiku API call with retry logic."""
    for attempt in range(5):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=messages,
            )
            return msg.content[0].text.strip()
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f" [rate limit, {wait}s]", end="", flush=True)
                time.sleep(wait)
            else:
                print(f" [API error: {e}]", end="", flush=True)
                return None
    return None


def _parse_json(response_text: str) -> dict | None:
    """Parse JSON from Claude response, handling common issues."""
    response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
    response_text = re.sub(r"\n?```$", "", response_text)
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(response_text)
        except json.JSONDecodeError:
            return None
    if isinstance(data, list):
        data = data[0] if data else None
    return data if isinstance(data, dict) else None


def parse_block_with_claude(bloc: str, session_id: str, block_index: int) -> dict | None:
    """Extract structured data + classification + bold from an intervention block (1 API call)."""
    prompt = EXTRACTION_PROMPT.format(bloc=bloc[:30000])
    messages = [{"role": "user", "content": prompt}]

    # Try up to 3 times: initial + 2 correction retries
    for attempt in range(3):
        response_text = _api_call(messages)
        if not response_text:
            return None

        data = _parse_json(response_text)
        if not data:
            print(f"JSON parse error (attempt {attempt + 1})")
            if attempt < 2:
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": "La resposta no és JSON vàlid. Torna a enviar el JSON complet correctament."})
                continue
            return None

        # Discard blocks that are pure Presidenta transitions
        if not data.get("entitat") and not data.get("intervinient"):
            return None

        # Validate against canonical values
        errors = validate_response(data)
        if errors and attempt < 2:
            print(f"validation errors, retrying...", end=" ", flush=True)
            messages.append({"role": "assistant", "content": response_text})
            correction = "La resposta anterior té errors de validació:\n"
            correction += "\n".join(f"- {e}" for e in errors)
            correction += "\nCorregeix i torna a enviar el JSON complet."
            messages.append({"role": "user", "content": correction})
            continue

        # Apply auto-correction for any remaining taxonomy issues
        data["temes_v2"] = validate_temes(data.get("temes_v2", {}))

        ambit = data.get("ambit", "no_especificat")
        data["ambit"] = ambit if ambit in VALID_AMBITS else "no_especificat"

        # Normalize cap_subtopics
        cap_raw = data.get("cap_subtopics", [])
        if isinstance(cap_raw, list):
            cap_codes = [int(c) for c in cap_raw if isinstance(c, (int, float))]
        else:
            cap_codes = [int(c) for c in re.findall(r'\b\d{3,4}\b', str(cap_raw))]
        data["cap_subtopics"] = cap_codes
        data["cap_major"] = sorted(set(c // 100 for c in cap_codes))

        # Ensure list fields
        for key in ("zones", "districtes"):
            if not isinstance(data.get(key), list):
                data[key] = []

        # Track validation warnings if there were errors on final attempt
        if errors:
            data["validation_warnings"] = errors

        data["id"] = f"{session_id}-{block_index:03d}"
        data["pleno_id"] = session_id
        data["ordre"] = block_index
        data["bloc_raw"] = bloc[:500]
        return data

    return None


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    if not INPUT_METADATA.exists():
        print(f"Error: {INPUT_METADATA} not found.")
        raise SystemExit(1)

    # Load existing results for resumability
    existing = {}
    if OUTPUT_FILE.exists():
        for iv in json.loads(OUTPUT_FILE.read_text()):
            existing[iv["id"]] = iv

    text_files = sorted(TEXT_DIR.glob("*.txt"))
    print(f"Processing {len(text_files)} text files...")

    all_interventions = list(existing.values())
    processed_plenos = {iv["pleno_id"] for iv in all_interventions}

    for i, txt_path in enumerate(text_files):
        sid = txt_path.stem

        if sid in processed_plenos:
            count = sum(1 for iv in all_interventions if iv["pleno_id"] == sid)
            print(f"  [{i+1}/{len(text_files)}] {sid} — already processed ({count} interventions)")
            continue

        text = txt_path.read_text(encoding="utf-8")

        if not _has_citizen_interventions(text):
            print(f"  [{i+1}/{len(text_files)}] {sid} — no citizen interventions found")
            continue

        print(f"  [{i+1}/{len(text_files)}] {sid} — parsing...")
        sections = split_intervention_sections(text)
        session_interventions = []
        block_counter = 1

        for section in sections:
            blocks = extract_intervention_blocks(section)
            print(f"    Section: {len(blocks)} intervention block(s)")

            for block in blocks:
                print(f"    Block {block_counter}: extracting...", end=" ", flush=True)
                result = parse_block_with_claude(block, sid, block_counter)

                if result:
                    session_interventions.append(result)
                    entitat_str = (result.get('entitat') or '?')[:40]
                    temes_str = ",".join(result.get("temes_v2", {}).keys())
                    has_bold = "**" in (result.get("text_original") or "")
                    warn = " [!WARN]" if result.get("validation_warnings") else ""
                    print(f"OK — {result.get('intervinient', '?')[:30]} ({entitat_str}) [{temes_str}] bold={'Y' if has_bold else 'N'}{warn}")
                else:
                    print("FAILED")

                block_counter += 1
                time.sleep(0.3)

        all_interventions.extend(session_interventions)
        print(f"    → {len(session_interventions)} interventions extracted")

        # Save after each session for fault tolerance
        OUTPUT_FILE.write_text(json.dumps(all_interventions, ensure_ascii=False, indent=2))

    print(f"\nTotal interventions: {len(all_interventions)}")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

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
import httpx

for p in [Path(".env"), Path(__file__).parent.parent / ".env"]:
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
        break

os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC", "")
client = anthropic.Anthropic(http_client=httpx.Client(trust_env=False))

INTERVENTIONS_FILE = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"

# CAP codebook subset relevant for municipal politics
CAP_CODEBOOK = """
CODEBOOK COMPARATIVE AGENDAS PROJECT (CAP)
Major topics and subtopics relevant for municipal-level politics:

2 Civil Rights
  201 Minority Discrimination
  202 Gender Discrimination
  204 Age Discrimination
  205 Handicap Discrimination
  207 Freedom of Speech
  208 Right to Privacy

3 Health
  300 General Health
  301 Health Care Reform
  322 Medical Facilities
  331 Disease Prevention
  332 Infants and Children
  334 Long-term Care

4 Agriculture
  400 General Agriculture
  402 Subsidies to Farmers
  403 Food Inspection & Safety
  405 Animal and Crop Disease (includes animal welfare)

5 Labor
  500 General Labor
  501 Worker Safety
  502 Employment Training
  506 Youth Employment

6 Education
  600 General Education
  601 Higher Education
  602 Elementary & Secondary Schools
  603 Underprivileged Education
  606 Special Education

7 Environment
  700 General Environment
  701 Drinking Water
  703 Waste Disposal
  705 Air Pollution (includes noise pollution)
  707 Recycling
  709 Species & Forest (parks, trees, urban greening)
  711 Land and Water Conservation (includes climate, flooding)

9 Immigration
  900 Immigration and Refugees

10 Transportation
  1000 General Transportation
  1001 Mass Transit (bus, metro)
  1002 Highways (traffic, parking, roads)
  1010 Infrastructure (bike lanes, pedestrian)

12 Law and Crime
  1200 General Law and Crime
  1201 Law Enforcement Agencies (police)
  1203 Illegal Drugs
  1205 Prisons
  1206 Juvenile Crime
  1207 Child Abuse
  1208 Family Issues

13 Social Welfare
  1300 General Social Welfare
  1302 Low-Income Assistance
  1303 Elderly Assistance
  1304 Disabled Assistance
  1305 Volunteer Associations
  1308 Child Care

14 Housing
  1400 General Housing
  1401 Community Development (public space, urban planning)
  1403 Urban Development
  1406 Low-Income Housing
  1408 Elderly Housing
  1409 Homeless Assistance

15 Domestic Commerce
  1500 General Commerce
  1501 Banking
  1521 Small Businesses
  1525 Consumer Safety
  1526 Sports Regulation (includes tourism regulation)

17 Technology
  1700 General Technology
  1706 Telecommunications

19 International Affairs
  1906 Human Rights
  1925 Peace Movement (anti-war, international solidarity)

20 Government Operations
  2000 General Government Operations
  2001 Intergovernmental Relations
  2004 Government Employees
  2015 Claims against the government (transparency, accountability)

21 Public Lands
  2100 General Public Lands
  2101 National Parks
  2104 Water Resources
  2105 Dependencies & Territories

23 Culture
  2300 Cultural Policy (heritage, arts, language, festivals, sports)
"""

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

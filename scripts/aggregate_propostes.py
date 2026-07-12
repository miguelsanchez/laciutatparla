#!/usr/bin/env python3
"""
Aggregate the VLCParticipa / DecidimVLC participatory-budget proposals CSV
(5,795 proposals across 7 editions 2015/16–2022/23) into a compact JSON.

Produces data/propostes.json with counts per edition, district, barri,
and proposer type.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

CSV_FILE = Path(__file__).parent.parent / "data" / "raw" / "apoyo-propuestas-decidimvlc.csv"
OUT_FILE = Path(__file__).parent.parent / "data" / "propostes.json"

# Edition number → fiscal year label
EDITION_LABELS = {
    "1": "2015/16",
    "2": "2016/17",
    "3": "2017/18",
    "4": "2018/19",
    "5": "2019/20",
    "6": "2020/21",
    "7": "2022/23",
}

# District code (1–19) → canonical district name (matches data/raw/barris_referencia.json)
DISTRICT_BY_CODE = {
    "1": "Ciutat Vella", "2": "L'Eixample", "3": "Extramurs",
    "4": "Campanar", "5": "La Saïdia", "6": "El Pla del Real",
    "7": "L'Olivereta", "8": "Patraix", "9": "Jesús",
    "10": "Quatre Carreres", "11": "Poblats Marítims",
    "12": "Camins al Grau", "13": "Algirós", "14": "Benimaclet",
    "15": "Rascanya", "16": "Benicalap", "17": "Poblats del Nord",
    "18": "Poblats de l'Oest", "19": "Poblats del Sud",
}

# For pedanías (districts 17, 18, 19), the numeric Ambito_Referencia is the
# barri index within the district. Values map to canonical barri names
# (those used in data/raw/barris_referencia.json).
BARRI_BY_DIST_AND_INDEX = {
    "17": {  # Poblats del Nord
        "1": "Benifaraig", "2": "Poble Nou", "3": "Carpesa",
        "4": "Les Cases De Barcena", "5": "Mahuella-Tauladella",
        "6": "Massarrojos", "7": "Borboto",
    },
    "18": {  # Poblats de l'Oest
        "1": "Benimamet", "2": "Beniferri",
    },
    "19": {  # Poblats del Sud
        "1": "El Forn D'Alcedo", "2": "Castellar-L'Oliveral",
        "3": "Pinedo", "4": "El Saler", "5": "El Palmar",
        "6": "El Perellonet", "7": "La Torre", "8": "Faitanar",
    },
}

# Normalize "Tipo_Proponente" → 3 canonical buckets
TIPO_MAP = {
    "Persona Fisica": "persona_fisica",
    "Persona Juridica": "persona_juridica",
    "Particular": "persona_fisica",
    "Representante GT": "grupo_trabajo",
    "Ayuntamiento": "ayuntamiento",
    "Ayuntamiento en rep. GT": "ayuntamiento",
    "Ayuntamiento de oficio": "ayuntamiento",
}


def parse_int(s: str) -> int:
    s = (s or "").strip()
    if s in ("", "NA", "No aplicable"):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def parse_yes(s: str) -> bool:
    return (s or "").strip().upper() == "SI"


def main():
    # Counters nested by various keys. Each leaf is a dict of metrics.
    def mkleaf():
        return {
            "presentadas": 0,
            "pasa_apoyo": 0,
            "pasa_viabilidad": 0,
            "seleccionadas": 0,
            "apoyos_total": 0,
            "votos_total": 0,
            "presupuesto_seleccionadas": 0,
        }

    global_totals = mkleaf()
    by_edition: dict = defaultdict(mkleaf)
    by_edition_district: dict = defaultdict(lambda: defaultdict(mkleaf))
    by_edition_barri: dict = defaultdict(lambda: defaultdict(mkleaf))
    by_edition_tipo: dict = defaultdict(lambda: defaultdict(mkleaf))
    # Totals by district and barri (all editions)
    by_district: dict = defaultdict(mkleaf)
    by_barri: dict = defaultdict(mkleaf)

    # For canonical barri we also want the parent district, so we can render
    # the same way as the quejas barri view.
    barri_to_district: dict = {}

    unmapped_codes = set()
    unmapped_tipos = set()

    with CSV_FILE.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            edition = row.get("Edicion", "").strip()
            cod = row.get("Codigo_Ambito_Referencia", "").strip()
            amb = row.get("Ambito_Referencia", "").strip()
            tipo_raw = row.get("Tipo_Proponente", "").strip()

            if edition not in EDITION_LABELS:
                continue

            # Resolve district and barri
            district = None
            barri = None
            if cod in ("Toda la ciudad", "20"):
                # Code 20 ("No consta" en Ambito) solo aparece en edición 4 y
                # las propuestas son de alcance ciudad (carril bici Valencia,
                # wifi para todos, etc.). Las agrupamos como ciudad.
                scope = "ciudad"
            elif cod in DISTRICT_BY_CODE:
                district = DISTRICT_BY_CODE[cod]
                # numeric Ambito = barri index within pedanía
                if amb.isdigit() and cod in BARRI_BY_DIST_AND_INDEX:
                    b = BARRI_BY_DIST_AND_INDEX[cod].get(amb)
                    if b:
                        barri = b
                        barri_to_district[barri] = district
                scope = "barri" if barri else "distrito"
            else:
                unmapped_codes.add(cod)
                scope = "desconocido"

            tipo = TIPO_MAP.get(tipo_raw)
            if not tipo:
                unmapped_tipos.add(tipo_raw)
                tipo = "otro"

            # Metrics
            pasa_apoyo = parse_yes(row.get("Pasa_Fase_Apoyos"))
            pasa_viab = parse_yes(row.get("Pasa_Fase_Viabilidad"))
            seleccionada = parse_yes(row.get("Seleccionada"))
            apoyos = parse_int(row.get("Numero_Apoyos"))
            votos = parse_int(row.get("Numero_Votos"))
            presupuesto = parse_int(row.get("Presupuesto_euros")) if seleccionada else 0

            def bump(leaf):
                leaf["presentadas"] += 1
                if pasa_apoyo:
                    leaf["pasa_apoyo"] += 1
                if pasa_viab:
                    leaf["pasa_viabilidad"] += 1
                if seleccionada:
                    leaf["seleccionadas"] += 1
                leaf["apoyos_total"] += apoyos
                leaf["votos_total"] += votos
                leaf["presupuesto_seleccionadas"] += presupuesto

            bump(global_totals)
            bump(by_edition[edition])
            bump(by_edition_tipo[edition][tipo])
            if district:
                bump(by_edition_district[edition][district])
                bump(by_district[district])
            if barri:
                bump(by_edition_barri[edition][barri])
                bump(by_barri[barri])

    out = {
        "total": global_totals,
        "editions": {
            ed: {
                "label": EDITION_LABELS[ed],
                "totals": by_edition[ed],
                "by_district": dict(by_edition_district[ed]),
                "by_barri": dict(by_edition_barri[ed]),
                "by_tipo": dict(by_edition_tipo[ed]),
            }
            for ed in sorted(EDITION_LABELS, key=int)
        },
        "by_district": dict(by_district),
        "by_barri": dict(by_barri),
        "barri_to_district": barri_to_district,
    }

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Total propuestas: {global_totals['presentadas']}")
    print(f"  Pasan apoyo: {global_totals['pasa_apoyo']}")
    print(f"  Pasan viabilidad: {global_totals['pasa_viabilidad']}")
    print(f"  Seleccionadas: {global_totals['seleccionadas']}")
    print(f"  Presupuesto seleccionadas: {global_totals['presupuesto_seleccionadas']:,}€")
    print(f"Ediciones: {sorted(EDITION_LABELS, key=int)}")
    print(f"Distritos con propuestas: {len(by_district)}")
    print(f"Barris con propuestas: {len(by_barri)}")
    if unmapped_codes:
        print(f"WARN códigos distrito sin mapear: {unmapped_codes}")
    if unmapped_tipos:
        print(f"WARN tipos proponente sin mapear: {unmapped_tipos}")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()

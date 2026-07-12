#!/usr/bin/env python3
"""
Aggregate quejas y sugerencias CSV into a compact JSON for the web.
Produces:
- data/quejas.json: aggregated counts by district × year × topic
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

CSV_FILE = Path(__file__).parent.parent / "data" / "raw" / "quejas_sugerencias.csv"
OUT_FILE = Path(__file__).parent.parent / "data" / "quejas.json"

# Normalize district names (CSV → our canonical names)
DISTRICT_MAP = {
    "Ciutat Vella": "Ciutat Vella",
    "L'Eixample": "L'Eixample",
    "Extramurs": "Extramurs",
    "Campanar": "Campanar",
    "La Saïdia": "La Saïdia",
    "El Pla del Real": "El Pla del Real",
    "L'Olivereta": "L'Olivereta",
    "Patraix": "Patraix",
    "Jesús": "Jesús",
    "Quatre Carreres": "Quatre Carreres",
    "Poblats Marítims": "Poblats Marítims",
    "Camins al Grau": "Camins al Grau",
    "Algirós": "Algirós",
    "Benimaclet": "Benimaclet",
    "Rascanya": "Rascanya",
    "Benicalap": "Benicalap",
    # CSV uses "Pobles" (valencian singular), we use "Poblats" (plural)
    "Pobles del Nord": "Poblats del Nord",
    "Pobles de l'Oest": "Poblats de l'Oest",
    "Pobles del Sud": "Poblats del Sud",
}

# Output canonical district names (19)
ALL_DISTRICTS = [
    "Ciutat Vella", "L'Eixample", "Extramurs", "Campanar", "La Saïdia",
    "El Pla del Real", "L'Olivereta", "Patraix", "Jesús", "Quatre Carreres",
    "Poblats Marítims", "Camins al Grau", "Algirós", "Benimaclet",
    "Rascanya", "Benicalap", "Poblats del Nord", "Poblats de l'Oest",
    "Poblats del Sud",
]

# Normalize barri names from CSV → canonical (as in barris_referencia.json).
# Only entries where the CSV name differs from canonical need to be listed;
# exact matches pass through untouched.
BARRI_MAP = {
    "Benimàmet": "Benimamet",
    "Beteró": "Betero",
    "Borbotó": "Borboto",
    "Camí Fondo": "Cami Fondo",
    "Camí Real": "Cami Real",
    "Camí de Vera": "Cami De Vera",
    "Cases de Bàrcena": "Les Cases De Barcena",
    "Ciutat Jardí": "Ciutat Jardi",
    "Ciutat Universitària": "Ciutat Universitaria",
    "Ciutat de les Arts i de les Ciències": "Ciutat De Les Arts I De Les Ciencies",
    "El Botànic": "El Botanic",
    "El Cabanyal-el Canyamelar": "Cabanyal-Canyamelar",
    "El Castellar-l'Oliverar": "Castellar-L'Oliveral",
    "El Forn d'Alcedo": "El Forn D'Alcedo",
    "El Pla del Remei": "El Pla Del Remei",
    "Exposició": "Exposicio",
    "Fonteta de Sant Lluís": "La Fonteta S.Lluis",
    "Gran Via": "La Gran Via",
    "L'Hort de Senabre": "L'Hort De Senabre",
    "La Bega Baixa": "La Vega Baixa",
    "La Creu del Grau": "La Creu Del Grau",
    "La Malva-rosa": "La Malva-Rosa",
    "Mauella": "Mahuella-Tauladella",
    "Mont-Olivet": "Montolivet",
    "Orriols": "Els Orriols",
    "Penya-roja": "Penya-Roja",
    "Sant Llorenç": "Sant Llorens",
    "Sant Marcel·lí": "Sant Marcel.Li",
    "Vara de Quart": "Vara De Quart",
}

# Values that look like barri but aren't (out-of-jurisdiction / unknown).
# Treated as "sin barri declarado".
BARRI_EXCLUDED = {
    "No consta",
    "No hi consta",
    "Fora de València",
    "Fuera de València",
    "En dependencias municipales",
    "",
}

# Map queja tema → our primary category (for topic comparison)
TEMA_TO_CAT = {
    "Servicios de limpieza en la vía pública": "urbanisme",
    "Servicios prestados en vía pública": "urbanisme",
    "Vía pública reparación de deficiencias": "urbanisme",
    "Servicios de jardinería": "medi_ambient",
    "Sugerencias para la mejora de la ciudad": None,  # too generic
    "Discrepancias con actuaciones municipales": "participacio",
    "Señalización viaria": "mobilitat",
    "Contaminación acústica": "medi_ambient",
    "Tramitación administrativa": "participacio",
    "Atención Personal Municipal": "participacio",
    "Organismos autónomos": None,
    "Otros": None,
    "Agradecimientos": None,
    "Eventos": "cultura",
    "Distinto ámbito competencial": None,
    "Tributación municipal y sanciones": "economia",
    "COVID-19": "serveis_publics",
    "Covid-19": "serveis_publics",
    "Política lingüística": "drets_i_igualtat",
}


def tipo_group(t: str) -> str:
    """Group tipo_solicitud into 'queja' or 'sugerencia'."""
    if t == "Sugerencia":
        return "sugerencia"
    if t in ("Queja", "Síndic", "Defensor"):
        return "queja"
    return "otra"


def main():
    # Counters, now per tipo
    # {tipo: {district: count}}
    by_district: dict = defaultdict(lambda: defaultdict(int))
    # {tipo: {district: {year: count}}}
    by_district_year: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # {tipo: {barri: count}}
    by_barri: dict = defaultdict(lambda: defaultdict(int))
    # {tipo: {barri: {year: count}}}
    by_barri_year: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # {tipo: count of records that had a recognized district but no valid barri}
    total_sin_barri: dict = defaultdict(int)
    # {tipo: count of records whose district couldn't be mapped to canonical
    # (i.e. "No consta"-type or outside València). These never appear in any
    # geographic cross-view.}
    total_sin_districte: dict = defaultdict(int)
    # {tipo: {tema: count}}
    by_tema: dict = defaultdict(lambda: defaultdict(int))
    # {tipo: {tema: {year: count}}}
    by_tema_year: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # {tipo: {year: {district: {tema: count}}}}
    by_year_district_tema: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    total = 0
    total_by_tipo: dict = defaultdict(int)

    with CSV_FILE.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            total += 1
            tipo_raw = row.get("tipo_solicitud", "").strip()
            tipo = tipo_group(tipo_raw)
            if tipo == "otra":
                continue
            total_by_tipo[tipo] += 1
            # Use localization district (the area affected)
            d = row.get("distrito_localización", "").strip()
            b = row.get("barrio_localización", "").strip()
            t = row.get("tema", "").strip()
            fecha = row.get("fecha_entrada_ayuntamiento", "").strip()
            year = fecha.split("/")[-1] if "/" in fecha else ""

            canonical = DISTRICT_MAP.get(d)
            if canonical:
                by_district[tipo][canonical] += 1
                if year:
                    by_district_year[tipo][canonical][year] += 1
                    if t:
                        by_year_district_tema[tipo][year][canonical][t] += 1

                # Barri aggregation — only for rows with a recognized district.
                # Normalize CSV name to canonical; drop "No consta"-type values.
                if b in BARRI_EXCLUDED:
                    total_sin_barri[tipo] += 1
                else:
                    canonical_b = BARRI_MAP.get(b, b)
                    by_barri[tipo][canonical_b] += 1
                    if year:
                        by_barri_year[tipo][canonical_b][year] += 1
            else:
                total_sin_districte[tipo] += 1

            if t:
                by_tema[tipo][t] += 1
                if year:
                    by_tema_year[tipo][t][year] += 1

    # Build output — nested by tipo
    all_years = sorted({y for tipo in by_district_year
                        for d in by_district_year[tipo].values()
                        for y in d.keys()})

    def build_tipo(tipo: str) -> dict:
        return {
            "total": total_by_tipo[tipo],
            "total_sin_barri": total_sin_barri[tipo],
            "total_sin_districte": total_sin_districte[tipo],
            "districts": {
                d: {
                    "total": by_district[tipo][d],
                    "by_year": dict(by_district_year[tipo][d]),
                }
                for d in ALL_DISTRICTS
            },
            "barris": {
                b: {
                    "total": c,
                    "by_year": dict(by_barri_year[tipo][b]),
                }
                for b, c in by_barri[tipo].items()
            },
            "temas": {
                t: {
                    "total": c,
                    "by_year": dict(by_tema_year[tipo][t]),
                }
                for t, c in by_tema[tipo].items()
            },
            "by_year_district_tema": {
                y: {d: dict(tm) for d, tm in yd.items()}
                for y, yd in by_year_district_tema[tipo].items()
            },
        }

    out = {
        "total": total_by_tipo["queja"] + total_by_tipo["sugerencia"],
        "years": all_years,
        "by_tipo": {
            "queja": build_tipo("queja"),
            "sugerencia": build_tipo("sugerencia"),
        },
    }

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Total analizado: {total}")
    for tipo in ("queja", "sugerencia"):
        with_barri = sum(by_barri[tipo].values())
        print(
            f"  {tipo}: {total_by_tipo[tipo]}  "
            f"(con barri: {with_barri}, sin barri: {total_sin_barri[tipo]})"
        )
    print(f"Barris únics (queja∪sugerencia): "
          f"{len(set(by_barri['queja']) | set(by_barri['sugerencia']))}")
    print(f"Years: {out['years']}")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()

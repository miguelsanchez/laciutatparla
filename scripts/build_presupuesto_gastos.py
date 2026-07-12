#!/usr/bin/env python3
"""
Build budget data from 'Estado liquidación de gastos' CSV.
Maps functional budget codes to our 9 thematic categories and aggregates
executed expenditure (OB. REC. NETAS) by year and category.

Output: data/presupuesto_gastos.json
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
INPUT_CSV = DATA_DIR / "raw" / "estado_liquid_gastos_2021-2026.csv"
OUTPUT_FILE = DATA_DIR / "presupuesto_gastos.json"

# ── Mapping: 3-digit functional code → our thematic category ──────────────
# Based on Spanish municipal budget functional classification.
# Only codes that map cleanly to citizen-facing services are included.
# Administrative overhead (91x, 92x, 93x) and debt (01x) are excluded.

FUNC_TO_CATEGORY = {
    # Seguridad y orden público → serveis_publics
    "132": "serveis_publics",  # Seguridad y orden público - Policía Local
    "133": "serveis_publics",  # Seguridad - Protección Civil
    "136": "serveis_publics",  # Seguridad - Bomberos

    # Vivienda y urbanismo → urbanisme
    "150": "urbanisme",  # Vivienda y urbanismo - administración general
    "151": "urbanisme",  # Urbanismo: planeamiento, gestión, ejecución
    "152": "urbanisme",  # Vivienda
    "153": "urbanisme",  # Vías públicas

    # Bienestar comunitario → medi_ambient
    "160": "medi_ambient",  # Saneamiento, abastecimiento, distribución agua
    "161": "medi_ambient",  # Saneamiento
    "162": "medi_ambient",  # Recogida, eliminación y tratamiento de residuos
    "163": "medi_ambient",  # Limpieza viaria
    "164": "medi_ambient",  # Cementerios
    "165": "medi_ambient",  # Alumbrado público

    # Medio ambiente → medi_ambient
    "171": "medi_ambient",  # Parques y jardines
    "172": "medi_ambient",  # Protección y mejora del medio ambiente

    # Protección social → serveis_publics (serveis_socials)
    "231": "serveis_publics",  # Acción social

    # Fomento de empleo → economia
    "241": "economia",  # Fomento del empleo

    # Sanidad → serveis_publics
    "311": "serveis_publics",  # Sanidad

    # Educación → serveis_publics
    "321": "serveis_publics",  # Educación - construcción colegios
    "322": "serveis_publics",  # Educación - inversiones
    "323": "serveis_publics",  # Educación - guarderías, escuelas infantiles
    "326": "serveis_publics",  # Educación - servicios complementarios

    # Cultura → cultura
    "330": "cultura",  # Cultura - administración general
    "332": "cultura",  # Bibliotecas y archivos
    "333": "cultura",  # Museos y artes
    "334": "cultura",  # Fiestas populares y festejos
    "336": "cultura",  # Patrimonio cultural
    "337": "cultura",  # Música y artes escénicas
    "338": "cultura",  # Promoción cultural

    # Deporte → cultura (esports va bajo cultura en nuestra taxonomy? No, va bajo serveis_publics)
    "341": "serveis_publics",  # Deporte - promoción
    "342": "serveis_publics",  # Deporte - instalaciones

    # Agricultura → economia
    "410": "economia",  # Agricultura
    "411": "economia",  # Agricultura - ganadería
    "412": "economia",  # Agricultura - infraestructuras agrarias

    # Comercio, turismo → economia
    "431": "economia",  # Comercio
    "432": "economia",  # Turismo

    # Transporte → mobilitat
    "441": "mobilitat",  # Transporte colectivo urbano (EMT, metro)
    "442": "mobilitat",  # Transporte - infraestructuras

    # Otras actuaciones económicas → economia
    "491": "economia",  # Infraestructuras
    "492": "economia",  # Actuaciones económicas diversas
    "493": "economia",  # Mercados
    "495": "economia",  # Información y estadística
}

# Human-readable names for the functional groups (2-digit level)
FUNC_GROUP_NAMES = {
    "13": "Seguridad y orden público",
    "15": "Vivienda y urbanismo",
    "16": "Bienestar comunitario",
    "17": "Medio ambiente",
    "23": "Acción social",
    "24": "Fomento del empleo",
    "31": "Sanidad",
    "32": "Educación",
    "33": "Cultura",
    "34": "Deporte",
    "41": "Agricultura",
    "43": "Comercio y turismo",
    "44": "Transporte público",
    "49": "Otras actuaciones económicas",
}


def parse_amount(s: str) -> float:
    """Parse Spanish number format: 1.234.567,89 → 1234567.89"""
    if not s or not s.strip():
        return 0.0
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def main():
    with open(INPUT_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    print(f"Loaded {len(rows)} rows")

    # Aggregate by year × category
    by_year_cat = defaultdict(float)         # (year, category) → total
    by_year_cat_func = defaultdict(float)    # (year, category, func2) → total
    by_year = defaultdict(float)             # year → total mapped
    unmapped_total = 0
    total_mapped = 0

    # Also track December rows for annual totals (cumulative)
    # Actually, the data is monthly snapshots. OB.REC.NETAS is cumulative.
    # We need to take December of each year (or the last month available).
    # Let's check: are the amounts cumulative or incremental?

    # Group by year and take the LAST month for each partida
    partida_year_months = defaultdict(dict)  # (partida, year) → {month: ob_rec}
    for r in rows:
        fecha = r["FECHA"].strip()
        parts_date = fecha.split("/")
        if len(parts_date) != 3:
            continue
        day, month, year = parts_date
        partida = r["APLICACION PRESUPUESTARIA"].strip()
        ob = parse_amount(r.get("OB. REC. NETAS", "0"))
        key = (partida, year)
        partida_year_months[key][int(month)] = ob

    # For each partida-year, take the value from December (month 12)
    # or the last available month
    for (partida, year), months in partida_year_months.items():
        last_month = max(months.keys())
        ob = months[last_month]

        parts = partida.split()
        if len(parts) < 2:
            continue
        func3 = parts[1][:3]

        cat = FUNC_TO_CATEGORY.get(func3)
        if cat:
            by_year_cat[(year, cat)] += ob
            func2 = func3[:2]
            by_year_cat_func[(year, cat, func2)] += ob
            by_year[year] += ob
            total_mapped += ob
        else:
            unmapped_total += ob

    print(f"Mapped: {total_mapped/1e6:.0f} M€, Unmapped (admin/debt): {unmapped_total/1e6:.0f} M€")

    # Build output structure
    years = sorted(set(y for y, _ in by_year_cat.keys()))
    categories = sorted(set(c for _, c in by_year_cat.keys()))

    result = {
        "years": years,
        "categories": categories,
        "by_year": {},
        "by_year_detail": {},
        "totals_by_year": {},
    }

    for year in years:
        result["by_year"][year] = {}
        result["by_year_detail"][year] = {}
        for cat in categories:
            amount = by_year_cat.get((year, cat), 0)
            result["by_year"][year][cat] = round(amount)

            # Detail by functional group
            detail = {}
            for (y, c, f2), val in by_year_cat_func.items():
                if y == year and c == cat:
                    name = FUNC_GROUP_NAMES.get(f2, f2)
                    detail[name] = round(val)
            result["by_year_detail"][year][cat] = detail

        result["totals_by_year"][year] = round(by_year[year])

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved to {OUTPUT_FILE}")

    # Summary
    print(f"\n{'Year':>6} | {'Total mapped':>14} | " + " | ".join(f"{c[:8]:>10}" for c in categories))
    print("-" * 120)
    for year in years:
        total = result["totals_by_year"][year]
        cats = " | ".join(f"{result['by_year'][year].get(c, 0)/1e6:>10.1f}" for c in categories)
        print(f"{year:>6} | {total/1e6:>12.1f} M | {cats}")


if __name__ == "__main__":
    main()

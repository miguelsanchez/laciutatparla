#!/usr/bin/env python3
"""
Normalize the vulnerability-by-barri CSV from the open-data portal into a
compact JSON keyed by canonical barri names (matching barris_referencia.json).

Source: https://opendata.vlci.valencia.es/dataset/vulnerabilidad-por-barrios
Output: data/vulnerabilidad.json
"""
import csv
import json
from pathlib import Path

CSV = Path(__file__).parent.parent / "data" / "raw" / "vulnerabilidad-por-barrios.csv"
REF = Path(__file__).parent.parent / "data" / "raw" / "barris_referencia.json"
OUT = Path(__file__).parent.parent / "data" / "vulnerabilidad.json"

# Manual fixes for names that differ between the CSV and our canonical.
NAME_FIX = {
    "MONT-OLIVET": "Montolivet",
    "SANT MARCEL.LI": "Sant Marcel.Li",  # already matches canonical case
}


def main():
    # Build uppercase → canonical mapping from barris_referencia.json
    ref = json.load(REF.open())
    upper_to_canon = {b["nom"].upper(): b["nom"] for b in ref}
    # Apply manual fixes
    for csv_upper, canon in NAME_FIX.items():
        upper_to_canon[csv_upper] = canon

    out: dict = {}
    unmapped: list = []

    with CSV.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name_upper = row["Nombre"].strip().upper()
            canon = upper_to_canon.get(name_upper)
            if not canon:
                unmapped.append(row["Nombre"])
                continue
            out[canon] = {
                "distrito": row["Distrito"].strip(),
                "ind_equipamientos": float(row["Ind_Equip"]),
                "ind_demografico": float(row["Ind_Dem"]),
                "ind_socioeconomico": float(row["Ind_Econom"]),
                "ind_global": float(row["Ind_Global"]),
                "vul_equipamientos": row["Vul_Equip"].strip(),
                "vul_demografico": row["Vul_Dem"].strip(),
                "vul_socioeconomico": row["Vul_Econom"].strip(),
                "vul_global": row["Vul_Global"].strip(),
            }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    print(f"  Barris mapped: {len(out)} / 70")
    if unmapped:
        print(f"  UNMAPPED: {unmapped}")

    # Distribution summary
    for label in ("vul_global", "vul_demografico", "vul_socioeconomico", "vul_equipamientos"):
        counts: dict = {}
        for v in out.values():
            cat = v[label]
            counts[cat] = counts.get(cat, 0) + 1
        print(f"  {label}: {counts}")


if __name__ == "__main__":
    main()

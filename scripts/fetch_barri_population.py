#!/usr/bin/env python3
"""
Fetch per-barri population evolution PDFs from the València Oficina
d'Estadística and extract the yearly population series.

Source: https://www.valencia.es/estadistica/inf_dtba/2026/Districte_XX_Barri_Y.pdf
Each PDF contains "Evolución de la población" with years 1991, 1996, 2001,
and continuous data 2015-2025.

Outputs data/raw/barri_poblacion.json keyed by canonical barri name.
"""
import json
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

OUT_FILE = Path(__file__).parent.parent / "data" / "raw" / "barri_poblacion.json"
BASE_URL = "https://www.valencia.es/estadistica/inf_dtba/2026/Districte_{d:02d}_Barri_{b}.pdf"

# (district_code, district_name, [(barri_index, canonical_barri_name)])
# Indices match the PDF numbering used in Tabla 6 of the Oficina d'Estadística report.
BARRIS_PER_DISTRICT = {
    1:  ("Ciutat Vella", [
        (1, "La Seu"), (2, "La Xerea"), (3, "El Carme"),
        (4, "El Pilar"), (5, "El Mercat"), (6, "Sant Francesc"),
    ]),
    2:  ("L'Eixample", [
        (1, "Russafa"), (2, "El Pla Del Remei"), (3, "La Gran Via"),
    ]),
    3:  ("Extramurs", [
        (1, "El Botanic"), (2, "La Roqueta"),
        (3, "La Petxina"), (4, "Arrancapins"),
    ]),
    4:  ("Campanar", [
        (1, "Campanar"), (2, "Les Tendetes"),
        (3, "El Calvari"), (4, "Sant Pau"),
    ]),
    5:  ("La Saïdia", [
        (1, "Marxalenes"), (2, "Morvedre"), (3, "Trinitat"),
        (4, "Tormos"), (5, "Sant Antoni"),
    ]),
    6:  ("El Pla del Real", [
        (1, "Exposicio"), (2, "Mestalla"),
        (3, "Jaume Roig"), (4, "Ciutat Universitaria"),
    ]),
    7:  ("L'Olivereta", [
        (1, "Nou Moles"), (2, "Soternes"), (3, "Tres Forques"),
        (4, "La Fontsanta"), (5, "La Llum"),
    ]),
    8:  ("Patraix", [
        (1, "Patraix"), (2, "Sant Isidre"), (3, "Vara De Quart"),
        (4, "Safranar"), (5, "Favara"),
    ]),
    9:  ("Jesús", [
        (1, "La Raiosa"), (2, "L'Hort De Senabre"),
        (3, "La Creu Coberta"), (4, "Sant Marcel.Li"), (5, "Cami Real"),
    ]),
    10: ("Quatre Carreres", [
        (1, "Montolivet"), (2, "En Corts"), (3, "Malilla"),
        (4, "La Fonteta S.Lluis"), (5, "Na Rovella"),
        (6, "La Punta"), (7, "Ciutat De Les Arts I De Les Ciencies"),
    ]),
    11: ("Poblats Marítims", [
        (1, "El Grau"), (2, "Cabanyal-Canyamelar"),
        (3, "La Malva-Rosa"), (4, "Betero"), (5, "Natzaret"),
    ]),
    12: ("Camins al Grau", [
        (1, "Aiora"), (2, "Albors"),
        (3, "La Creu Del Grau"), (4, "Cami Fondo"), (5, "Penya-Roja"),
    ]),
    13: ("Algirós", [
        (1, "L'Illa Perduda"), (2, "Ciutat Jardi"),
        (3, "L'Amistat"), (4, "La Vega Baixa"), (5, "La Carrasca"),
    ]),
    14: ("Benimaclet", [
        (1, "Benimaclet"), (2, "Cami De Vera"),
    ]),
    15: ("Rascanya", [
        (1, "Els Orriols"), (2, "Torrefiel"), (3, "Sant Llorens"),
    ]),
    16: ("Benicalap", [
        (1, "Benicalap"), (2, "Ciutat Fallera"),
    ]),
    17: ("Poblats del Nord", [
        (1, "Benifaraig"), (2, "Poble Nou"), (3, "Carpesa"),
        (4, "Les Cases De Barcena"), (5, "Mahuella-Tauladella"),
        (6, "Massarrojos"), (7, "Borboto"),
    ]),
    18: ("Poblats de l'Oest", [
        (1, "Benimamet"), (2, "Beniferri"),
    ]),
    19: ("Poblats del Sud", [
        (1, "El Forn D'Alcedo"), (2, "Castellar-L'Oliveral"),
        (3, "Pinedo"), (4, "El Saler"), (5, "El Palmar"),
        (6, "El Perellonet"), (7, "La Torre"), (8, "Faitanar"),
    ]),
}


def fetch_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "La Ciutat Parla / research"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_evolution_section(text: str) -> dict:
    """Locate the 'Evolución de la población' table and parse the year→pop mapping."""
    # Find the header line containing the years
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # Heuristic: the header row has multiple 4-digit year tokens.
        years = re.findall(r"\b(19\d{2}|20\d{2})\b", line)
        if len(years) >= 6:  # at least 6 years → this is the evolution header
            # Values row is typically 1-2 lines below.
            for j in range(i + 1, min(i + 4, len(lines))):
                nums = re.findall(r"[\d\.]+", lines[j])
                parsed = []
                for n in nums:
                    try:
                        parsed.append(int(n.replace(".", "")))
                    except ValueError:
                        pass
                if len(parsed) >= len(years):
                    return {y: parsed[k] for k, y in enumerate(years)}
            break
    return {}


def main():
    out: dict = {}
    errors: list = []
    total = sum(len(bs) for _, bs in BARRIS_PER_DISTRICT.values())
    idx = 0

    for dcode, (dname, barris) in BARRIS_PER_DISTRICT.items():
        for bidx, bname in barris:
            idx += 1
            url = BASE_URL.format(d=dcode, b=bidx)
            print(f"[{idx}/{total}] {dname} / {bname}...", end=" ", flush=True)
            try:
                pdf_bytes = fetch_pdf(url)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name
                text = subprocess.check_output(["pdftotext", "-layout", tmp_path, "-"], text=True)
                Path(tmp_path).unlink(missing_ok=True)
                pop = parse_evolution_section(text)
                if not pop:
                    errors.append((dname, bname, "no series"))
                    print("EMPTY")
                else:
                    out[bname] = {"district": dname, "poblacion_por_anyo": pop}
                    print(f"{len(pop)} years")
            except Exception as e:
                errors.append((dname, bname, str(e)))
                print(f"ERR {e}")
            time.sleep(0.25)  # be polite

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nWrote {OUT_FILE}")
    print(f"Barris with data: {len(out)} / {total}")
    if errors:
        print("\nErrors:")
        for dname, bname, err in errors:
            print(f"  {dname} / {bname}: {err}")


if __name__ == "__main__":
    main()

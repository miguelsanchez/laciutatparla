"""
export_dataset.py — Genera los archivos del dataset público de La Ciutat Parla.

Salida en web/public/datos/:
  intervencions.json          — dataset completo (JSON canónico)
  intervencions_metadata.csv  — metadatos sin textos (apto para Excel)
  entitats.json               — catálogo de entidades

Uso: python3 export_dataset.py
Idempotente: sobreescribe los archivos existentes.
"""

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "web" / "public" / "datos"

INTERVENCIONS_FILE = DATA_DIR / "intervencions.json"
ENTITATS_FILE = DATA_DIR / "entitats.json"

# Campos excluidos del dataset público (artefactos internos del pipeline)
EXCLUDE_FIELDS = {"temes", "barri_o_zona", "punts_ordre_dia", "ordre"}


def strip_bold(text: str) -> str:
    """Elimina los marcadores **negrita** del texto."""
    return re.sub(r'\*\*(.+?)\*\*', r'\1', text or "")


def pipe(lst: list) -> str:
    return "|".join(str(x) for x in lst) if lst else ""


def flatten_temes_v2(temes_v2: dict) -> tuple[str, str]:
    """Devuelve (categorias_pipe, subcategorias_pipe) desde temes_v2."""
    cats = list(temes_v2.keys())
    subs = [f"{cat}:{sub}" for cat, subs in temes_v2.items() for sub in subs]
    return pipe(cats), pipe(subs)


def clean_intervention_json(iv: dict) -> dict:
    """Devuelve una versión limpia de la intervención para el JSON público."""
    out = {k: v for k, v in iv.items() if k not in EXCLUDE_FIELDS}
    out["text_cas"] = strip_bold(out.get("text_cas", ""))
    out["text_val"] = strip_bold(out.get("text_val", ""))
    return out


def intervention_to_csv_row(iv: dict) -> dict:
    """Aplana una intervención al formato CSV (sin textos completos)."""
    cats, subs = flatten_temes_v2(iv.get("temes_v2", {}))
    return {
        "id": iv["id"],
        "pleno_id": iv["pleno_id"],
        "fecha": iv["fecha"],
        "mandat_id": iv.get("mandat_id", ""),
        "intervinient": iv.get("intervinient", ""),
        "entitat": iv.get("entitat", ""),
        "entitat_id": iv.get("entitat_id", ""),
        "tipus_entitat": iv.get("tipus_entitat", ""),
        "idioma_original": iv.get("idioma_original", ""),
        "ambit": iv.get("ambit", ""),
        "zones": pipe(iv.get("zones", [])),
        "districtes": pipe(iv.get("districtes", [])),
        "categorias": cats,
        "subcategorias": subs,
        "cap_major": pipe(iv.get("cap_major", [])),
        "cap_subtopics": pipe(iv.get("cap_subtopics", [])),
        "resum_cas": iv.get("resum_cas", ""),
        "resum_val": iv.get("resum_val", ""),
    }


def clean_entitat(e: dict) -> dict:
    """Elimina campos internos del catálogo de entidades."""
    return {k: v for k, v in e.items() if k != "variants"}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Cargando datos...")
    intervencions = json.loads(INTERVENCIONS_FILE.read_text())
    entitats = json.loads(ENTITATS_FILE.read_text())
    print(f"  {len(intervencions)} intervenciones · {len(entitats)} entidades")

    # 1. JSON canónico
    clean_ivs = [clean_intervention_json(iv) for iv in intervencions]
    out_json = OUT_DIR / "intervencions.json"
    out_json.write_text(json.dumps(clean_ivs, ensure_ascii=False, indent=2))
    print(f"  → {out_json} ({out_json.stat().st_size // 1024} KB)")

    # 2. CSV de metadatos (sin textos)
    csv_rows = [intervention_to_csv_row(iv) for iv in intervencions]
    out_csv = OUT_DIR / "intervencions_metadata.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"  → {out_csv} ({out_csv.stat().st_size // 1024} KB)")

    # 3. Catálogo de entidades
    clean_ents = [clean_entitat(e) for e in entitats]
    out_ents = OUT_DIR / "entitats.json"
    out_ents.write_text(json.dumps(clean_ents, ensure_ascii=False, indent=2))
    print(f"  → {out_ents} ({out_ents.stat().st_size // 1024} KB)")

    print("\nExportación completada.")


if __name__ == "__main__":
    main()

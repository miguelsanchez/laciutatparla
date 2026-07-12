#!/usr/bin/env python3
"""
Process obras ejecutadas GeoJSON into a slim JSON for the web.
Extracts centroid (from polygon), key fields, and classifies by financing type.
Output: data/obras_ejecutadas.json
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
INPUT = DATA_DIR / "raw" / "obras_ejecutadas.json"
OUTPUT = DATA_DIR / "obras_ejecutadas.json"


def centroid(coords):
    """Compute centroid of a polygon. Handles nested coordinate arrays."""
    # Flatten until we get a list of [lng, lat] pairs
    ring = coords
    while ring and isinstance(ring[0], list) and isinstance(ring[0][0], list):
        ring = ring[0]
    if not ring or not isinstance(ring[0], (int, float)):
        # ring is a list of [lng, lat] pairs
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
    else:
        # ring is already a single point
        return ring[:2]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


def main():
    data = json.loads(INPUT.read_text())
    features = data["features"]

    obras = []
    for f in features:
        p = f["properties"]
        geom = f.get("geometry")
        if not geom:
            continue

        coords = geom.get("coordinates", [])
        if not coords:
            continue

        center = centroid(coords)

        presupuesto = 0
        for field in ("presupuesto_adjudicacion", "presupuesto_proyecto", "presupuesto"):
            val = p.get(field)
            if val and val != "None":
                try:
                    presupuesto = float(str(val).replace(",", "."))
                    break
                except ValueError:
                    pass

        financiacion = p.get("financiacion") or "Desconocido"
        is_participacion = "participaci" in financiacion.lower()

        obras.append({
            "titulo": (p.get("titulo") or "").strip(),
            "ambito": (p.get("ambito") or "").strip(),
            "descripcion": (p.get("descripcion") or "").strip()[:200],
            "tipo": (p.get("tipo_intervencion") or "").strip(),
            "financiacion": financiacion.strip(),
            "participacion_ciudadana": is_participacion,
            "presupuesto": round(presupuesto),
            "lng": round(center[0], 6),
            "lat": round(center[1], 6),
        })

    OUTPUT.write_text(json.dumps(obras, ensure_ascii=False, indent=2))

    pc = sum(1 for o in obras if o["participacion_ciudadana"])
    total_pres = sum(o["presupuesto"] for o in obras)
    pc_pres = sum(o["presupuesto"] for o in obras if o["participacion_ciudadana"])

    print(f"Saved {len(obras)} obras to {OUTPUT}")
    print(f"  Participación Ciudadana: {pc} ({pc_pres/1e6:.1f} M€)")
    print(f"  Otras: {len(obras) - pc} ({(total_pres - pc_pres)/1e6:.1f} M€)")
    print(f"  Total presupuesto: {total_pres/1e6:.1f} M€")


if __name__ == "__main__":
    main()

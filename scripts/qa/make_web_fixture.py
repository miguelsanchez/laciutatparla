#!/usr/bin/env python3
"""Build the small, stable data fixture the web tests run on (arquitectura-agentes.md F4.2).

    "$PY" scripts/qa/make_web_fixture.py            # (re)writes web/tests/fixtures/data/
    LCP_DATA_DIR=tests/fixtures/data npm run build  # in web/: the site on the fixture

It takes the 10 entities with most interventions, one pleno per mandate (the one with most of
those entities' interventions) plus the pleno with a floor cession and the plenos in EXTRA_PLENOS (video states), and at most 4 interventions
per pleno from those entities: 5 plenos, 20 interventions, 10 entities or so. Counts and previews
are recomputed so the fixture is self-consistent. Context files (mandates, barrios, budgets,
complaints…) are small and are copied whole.

Reads data/ only; writes only under web/tests/fixtures/data/. Deterministic: the same data/
gives the same fixture, so visual snapshots stay stable until it is regenerated on purpose.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "web" / "tests" / "fixtures" / "data"

N_ENTITIES = 10
PER_PLENO = 4
CESSION_PLENO = "2026-07-23"
# Plenos kept for their video state (plan 3.11): split in 2 parts, live-player URL, and a pair that
# shares one recording. Interventions: the first EXTRA_PER_PLENO by id, whatever the entity.
EXTRA_PLENOS = ("2022-03-31", "2022-11-17", "2023-10-24", "2023-10-24-1")
EXTRA_PER_PLENO = 4
COPIED = ("mandats.json", "vulnerabilidad.json", "presupuesto_gastos.json", "obras_ejecutadas.json",
          "quejas.json", "presupuestos_oficial.json", "propostes.json",
          "raw/barri_poblacion.json", "raw/barris_referencia.json")


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def dump(name: str, obj) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select(ivs: list[dict], entities: list[dict]) -> tuple[list[str], list[dict]]:
    top = {e["id"] for e in sorted(entities, key=lambda e: (-e.get("num_intervencions", 0), e["id"]))[:N_ENTITIES]}
    by_pleno: dict[str, list[dict]] = {}
    for iv in ivs:
        if iv.get("entitat_id") in top:
            by_pleno.setdefault(iv["pleno_id"], []).append(iv)
    mandat_of = {iv["pleno_id"]: iv.get("mandat_id") for iv in ivs}
    plenos = []
    for mandat in sorted({m for m in mandat_of.values() if m}):
        candidates = [p for p in by_pleno if mandat_of[p] == mandat]
        if candidates:
            plenos.append(max(candidates, key=lambda p: (len(by_pleno[p]), p)))
    if CESSION_PLENO in mandat_of and CESSION_PLENO not in plenos:
        plenos.append(CESSION_PLENO)
    plenos += [p for p in EXTRA_PLENOS if p not in plenos]
    chosen = []
    for p in sorted(plenos):
        pool = by_pleno.get(p) or []
        if p in EXTRA_PLENOS:
            pool = sorted((iv for iv in ivs if iv["pleno_id"] == p), key=lambda iv: iv["id"])
        if p == CESSION_PLENO:   # keep the cession even when its entity is not in the top
            pool = [iv for iv in ivs if iv["pleno_id"] == p and iv.get("entitat_cessio")] + pool
        seen, picked = set(), []
        for iv in pool:
            if iv["id"] not in seen:
                seen.add(iv["id"])
                picked.append(iv)
        chosen += sorted(picked[:EXTRA_PER_PLENO if p in EXTRA_PLENOS else PER_PLENO], key=lambda iv: iv["id"])
    return sorted(plenos), chosen


def main() -> int:
    ivs = load("intervencions.json")
    entities = load("entitats.json")
    plenos_index = {p["id"]: p for p in load("plenos.json")}
    pleno_ids, chosen = select(ivs, entities)
    ids = {iv["id"] for iv in chosen}
    ent_ids = {iv.get("entitat_id") for iv in chosen} | {
        (iv.get("entitat_cessio") or {}).get("entitat_id") for iv in chosen}
    counts = Counter(iv.get("entitat_id") for iv in chosen)
    fixture_entities = [{**e, "num_intervencions": counts.get(e["id"], 0)}
                        for e in entities if e["id"] in ent_ids]

    if OUT.exists():
        shutil.rmtree(OUT)
    dump("intervencions.json", chosen)
    dump("entitats.json", fixture_entities)
    index = []
    for pid in pleno_ids:
        full = load(f"plenos/{pid}.json")
        kept = [iv for iv in full.get("intervencions", []) if iv["id"] in ids]
        dump(f"plenos/{pid}.json", {**full, "intervencions": kept, "num_intervencions": len(kept)})
        entry = dict(plenos_index[pid])
        entry["num_intervencions"] = len(kept)
        if "entitats_preview" in entry:
            names = {iv.get("entitat") for iv in kept}
            entry["entitats_preview"] = [n for n in entry["entitats_preview"] if n in names] or \
                sorted(n for n in names if n)[:3]
        index.append(entry)
    dump("plenos.json", index)
    for name in COPIED:
        dump(name, load(name))
    print(f"make_web_fixture: {len(pleno_ids)} plenos, {len(chosen)} interventions, "
          f"{len(fixture_entities)} entities → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

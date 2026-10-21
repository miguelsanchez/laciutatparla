#!/usr/bin/env python3
"""
Genera un PDF tipo libro con todas las intervenciones ciudadanas,
organizadas por mandato > año > pleno.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
OUT = Path(__file__).parent.parent / "docs"

ivs = json.loads((DATA / "intervencions.json").read_text())
plenos_idx = json.loads((DATA / "plenos.json").read_text())
mandats = json.loads((DATA / "mandats.json").read_text())

# Build lookup: pleno_id → session info (for URLs, alcalde)
plenos_by_id = {p["id"]: p for p in plenos_idx}

# Mandat lookup
def get_mandat(fecha: str):
    for m in mandats:
        if fecha >= m["inici"] and (m["fi"] is None or fecha <= m["fi"]):
            return m
    return None

# Group: mandat_id → year → pleno_id → [ivs]
tree: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
for iv in ivs:
    mandat = get_mandat(iv["fecha"])
    mid = mandat["id"] if mandat else "desconegut"
    year = iv["fecha"][:4]
    pleno_id = iv["pleno_id"]
    tree[mid][year][pleno_id].append(iv)

# Sort: mandats oldest first, years ascending, plenos by date, ivs by ordre
for mid in tree:
    for year in tree[mid]:
        for pid in tree[mid][year]:
            tree[mid][year][pid].sort(key=lambda iv: iv.get("ordre", 0))

mandats_sorted = sorted(mandats, key=lambda m: m["inici"])

# Bold markup to markdown
def md_escape(text: str) -> str:
    # Keep ** for bold, escape others
    return text.replace("<", "&lt;").replace(">", "&gt;")

def render_iv(iv: dict) -> str:
    """Render one intervention as markdown."""
    text = iv.get("text_cas") or iv.get("text_val") or ""
    if not text.strip():
        text = "*(Texto no disponible)*"
    temes_v2 = iv.get("temes_v2") or {}
    cat_parts = []
    for cat, subs in temes_v2.items():
        if subs:
            cat_parts.append(f"**{cat}** ({', '.join(subs)})")
        else:
            cat_parts.append(f"**{cat}**")
    ambit = iv.get("ambit", "")
    zones = iv.get("zones", []) or []
    districtes = iv.get("districtes", []) or []
    geo = ""
    if zones:
        geo = "📍 " + ", ".join(zones)
    elif districtes:
        geo = "📍 " + ", ".join(districtes)
    elif ambit and ambit != "no_especificat":
        geo = f"📍 {ambit}"

    header = f"### {iv.get('intervinient','—')}\n\n"
    header += f"*{iv.get('entitat','')}*  "
    if geo:
        header += f" · {geo}"
    header += "\n\n"
    if cat_parts:
        header += f"Temas: {', '.join(cat_parts)}\n\n"
    # Summary
    resum = iv.get("resum_cas") or iv.get("resum_val") or ""
    if resum:
        header += f"> {resum}\n\n"
    # Full text — paragraphs
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    body = "\n\n".join(paragraphs)
    return header + body + "\n\n"


# Build markdown
md = []
md.append("---\n")
md.append("title: La Ciutat Parla — Llibre d'intervencions ciutadanes\n")
md.append("subtitle: Archivo completo de las intervenciones ciudadanas en los plenos del Ayuntamiento de València\n")
md.append("---\n\n")

md.append("# La Ciutat Parla\n\n")
md.append("## Llibre d'intervencions ciutadanes\n\n")
md.append("Archivo completo de las intervenciones ciudadanas en los plenos del Ayuntamiento de València, organizado por mandato, año y pleno.\n\n")
md.append(f"**Total**: {len(ivs)} intervenciones de {len(set(iv['entitat_id'] for iv in ivs))} entidades en {len(set(iv['pleno_id'] for iv in ivs))} plenos.\n\n")
md.append("---\n\n")

# TOC
md.append("# Índice\n\n")
for m in mandats_sorted:
    mid = m["id"]
    if mid not in tree:
        continue
    md.append(f"## Mandato {m['legislatura']} · {m['alcalde']}\n\n")
    years = sorted(tree[mid].keys())
    for year in years:
        md.append(f"### {year}\n\n")
        pids = sorted(tree[mid][year].keys())
        for pid in pids:
            pleno = plenos_by_id.get(pid, {})
            fecha = pleno.get("fecha", pid[:10])
            count = len(tree[mid][year][pid])
            md.append(f"- **{fecha}** — {count} intervenciones\n")
        md.append("\n")

md.append("\n\\pagebreak\n\n")

# Content
for m in mandats_sorted:
    mid = m["id"]
    if mid not in tree:
        continue
    md.append(f"# Mandato {m['legislatura']}\n\n")
    md.append(f"**Alcalde/alcaldesa**: {m['alcalde']}\n\n")
    md.append(f"**Inicio**: {m['inici']}")
    if m.get("fi"):
        md.append(f" · **Fin**: {m['fi']}")
    md.append("\n\n\\pagebreak\n\n")

    years = sorted(tree[mid].keys())
    for year in years:
        md.append(f"## Año {year}\n\n")
        pids = sorted(tree[mid][year].keys())
        for pid in pids:
            pleno = plenos_by_id.get(pid, {})
            fecha = pleno.get("fecha", pid[:10])
            tipo = pleno.get("tipo", "")
            md.append(f"## Pleno {fecha}")
            if tipo:
                md.append(f" *({tipo})*")
            md.append("\n\n")
            for iv in tree[mid][year][pid]:
                md.append(render_iv(iv))
            md.append("\\pagebreak\n\n")

out_md = OUT / "libro-intervenciones.md"
out_md.write_text("".join(md))
print(f"Generated {out_md}")
print(f"Word count: {len(''.join(md).split())}")

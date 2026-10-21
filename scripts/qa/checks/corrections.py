"""N7: schema and integrity of data/corrections/*.yml (§7). Also run by the pre-commit hook."""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter

import yaml

from qa.model import Context, Finding, check
from qa.schemas import CORRECTION_FILES, SCHEMAS, VALID_IDIOMES, VALID_TIPUS, Schema

LEGACY_FILE = "meta/qa/n7_legacy.json"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def legacy_keys(ctx: Context) -> dict[str, set[str]]:
    """Entry keys that existed when N7 was introduced: exempt from reason/date."""
    p = ctx.repo_root / LEGACY_FILE
    if not p.exists():
        return {}
    return {k: set(v) for k, v in json.loads(p.read_text()).items()}


def section_id(s: Schema) -> str:
    return f"{s.file}:{s.section}" if s.section else s.file


def entries(doc, s: Schema):
    if s.section:
        return (doc or {}).get(s.section) or [] if isinstance(doc, dict) else None
    return doc or []


def _f(severity, schema: Schema, key, problem: str, message: str, **details) -> Finding:
    return Finding(check="N7", severity=severity, subject=f"{schema.file}|{key}", key=problem,
                   message=message, details={"file": f"data/corrections/{schema.file}", **details})


@check("N7", family="corrections", title="schema and integrity of data/corrections/*.yml", fast=True)
def n7_corrections(ctx: Context):
    docs, broken = {}, set()
    for name in CORRECTION_FILES:
        path = ctx.corrections_dir / name
        if not path.exists():
            continue
        try:
            docs[name] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            broken.add(name)
            yield Finding(check="N7", severity="P0", subject=name, key="yaml",
                          message=f"YAML does not parse: {str(e).splitlines()[0]}",
                          details={"file": f"data/corrections/{name}"})

    # What references may point to
    raw_ids = {str(iv.get("id")) for iv in ctx.interventions_raw}
    final_ids = {iv["id"] for iv in ctx.intervencions}
    manual_ids = {str(m.get("id")) for m in docs.get("manual_interventions.yml") or [] if isinstance(m, dict)}
    merged_away = {str(i) for m in docs.get("text_merges.yml") or [] if isinstance(m, dict)
                   for i in m.get("merge_ids") or []}
    known_ivs = raw_ids | final_ids | manual_ids | merged_away
    plenos = {s["id"] for s in ctx.sessions_index}
    catalog = {e["id"] for e in ctx.entitats}
    # A new entity is not in entitats.json until apply_merges creates it: in a proposal branch it
    # is "pending" — not stale — when an intervention will count for it (its entitat text maps or
    # slugifies to the id, the way apply_merges resolves it).
    from slugify import slugify
    variant_map = ctx._json("raw/entity_variant_map.json") or {}
    forced = {str(v.get("text", "")).lower().strip(): v.get("entity_id")
              for v in docs.get("variant_map_forced.yml") or [] if isinstance(v, dict)}
    texts = {str(iv.get("entitat") or "") for iv in ctx.interventions_raw}
    texts |= {str(m.get("entitat") or "") for m in docs.get("manual_interventions.yml") or [] if isinstance(m, dict)}
    pending = {forced.get(t.lower().strip()) or variant_map.get(t.lower().strip()) or slugify(t)
               for t in texts if t} | set(forced.values())
    legacy = legacy_keys(ctx)
    patched_lang = {str(p.get("iv_id")) for p in docs.get("patches.yml") or []
                    if isinstance(p, dict) and (p.get("fields") or {}).get("idioma_original") in VALID_IDIOMES}

    for s in SCHEMAS:
        if s.file not in docs or s.file in broken:
            continue
        items = entries(docs[s.file], s)
        if not isinstance(items, list):
            yield _f("P1", s, s.section or "-", "shape",
                     f"expected a list{' under ' + s.section if s.section else ''}")
            continue
        keys = Counter(str(e.get(s.key)) for e in items if isinstance(e, dict))
        for k, n in keys.items():
            if n > 1:
                yield _f("P1", s, k, "duplicate", f"{s.key} {k!r} appears {n} times")
        old = legacy.get(section_id(s), set())

        for i, e in enumerate(items):
            if not isinstance(e, dict):
                yield _f("P1", s, f"#{i}", "shape", f"entry #{i} is not a mapping")
                continue
            key = str(e.get(s.key, f"#{i}"))
            for req in s.required:
                if e.get(req) in (None, "", []):
                    yield _f("P1", s, key, f"missing:{req}", f"required field {req!r} is missing or empty")
            for fld in s.str_fields:
                v = e.get(fld)
                if v is not None and not isinstance(v, str):
                    hint = " (quote it: an unquoted date parses as a date)" if isinstance(v, dt.date) else ""
                    yield _f("P1", s, key, f"type:{fld}", f"{fld} must be a string, got {type(v).__name__}{hint}")
            for fld in s.list_fields:
                v = e.get(fld)
                if v is not None and not isinstance(v, list):
                    yield _f("P1", s, key, f"type:{fld}", f"{fld} must be a list")
            for fld in s.iv_refs:
                if e.get(fld) is not None and str(e[fld]) not in known_ivs:
                    yield _f("P1", s, key, f"ref:{fld}", f"{fld} {e[fld]!r} is not a known intervention")
            for fld in s.final_iv_refs:
                if e.get(fld) is not None and str(e[fld]) not in final_ids:
                    yield _f("P1", s, key, f"ref:{fld}",
                             f"{fld} {e[fld]!r} is not in intervencions.json: the correction no longer applies")
            for fld in s.pleno_refs:
                if e.get(fld) is not None and str(e[fld]) not in plenos:
                    yield _f("P1", s, key, f"ref:{fld}", f"{fld} {e[fld]!r} is not in sessions_index.json")
            for fld in s.extra.get("strict_entity_refs", ()):
                if e.get(fld) and e[fld] not in catalog:
                    yield _f("P1", s, key, f"ref:{fld}", f"{fld} {e[fld]!r} is not in entitats.json")
            cessio = e.get("entitat_cessio")
            if isinstance(cessio, dict):
                for req in ("nom_cas", "nom_val"):
                    if not cessio.get(req):
                        yield _f("P1", s, key, f"missing:entitat_cessio.{req}", f"entitat_cessio needs {req}")
            for fld in s.entity_refs:
                if s.file == "new_entities.yml" and e.get(fld) in pending:
                    continue
                if e.get(fld) and e[fld] not in catalog:
                    yield _f("P3", s, key, f"stale:{fld}",
                             f"{fld} {e[fld]!r} is not in entitats.json: this entry has no effect")
            if s.tipus_field and e.get(s.tipus_field) and e[s.tipus_field] not in VALID_TIPUS:
                yield _f("P2", s, key, "tipus", f"tipus {e[s.tipus_field]!r} is not a valid entity type")
            # Intervention values, in a manual intervention or a patch's fields (new entries only;
            # a manual one whose patch sets the language publishes the patch's value)
            if s.file in ("manual_interventions.yml", "patches.yml") and key not in old:
                vals = e.get("fields") if s.file == "patches.yml" else e
                if isinstance(vals, dict):
                    lang_patched = s.file == "manual_interventions.yml" and key in patched_lang
                    if vals.get("idioma_original") and vals["idioma_original"] not in VALID_IDIOMES \
                            and not lang_patched:
                        yield _f("P1", s, key, "idioma", f"idioma_original {vals['idioma_original']!r} "
                                                         f"is not one of {sorted(VALID_IDIOMES)}")
                    if vals.get("tipus_entitat") and vals["tipus_entitat"] not in VALID_TIPUS:
                        yield _f("P2", s, key, "tipus",
                                 f"tipus_entitat {vals['tipus_entitat']!r} is not a valid entity type")
            if s.needs_reason and key not in old:
                if not str(e.get("reason") or "").strip():
                    yield _f("P2", s, key, "reason", "new entry without `reason` (required since N7)")
                d = e.get("date")
                if not (isinstance(d, dt.date) or (isinstance(d, str) and ISO_DATE.match(d))):
                    yield _f("P2", s, key, "date", "new entry without `date: YYYY-MM-DD` (required since N7)")

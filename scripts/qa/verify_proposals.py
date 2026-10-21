#!/usr/bin/env python3
"""Verify LLM proposals before they reach propose.py (arquitectura-agentes.md §3.3, F2.2).

Every proposal must survive five gates; the first one it fails is the reason it is dropped:

  1. quote   the evidence quote is in the acta, compared after the same normalisation on both
             sides (hyphen at a line end, whitespace, typographic quotes and dashes, case). No
             accent folding and no fuzzy match: a "similar" quote is an invented quote. A
             text_original the proposal copies from the acta must be ≥ 90 % literal, by sentence.
  2. idioma  a quote found in text_cas/text_val but not in the acta is a translation: dropped.
  3. ids     the subject and the ids the entry names exist (intervention, pleno, entity).
  4. N7      the entry, appended to a copy of data/corrections/, passes N7 (schema, integrity).
  5. dry-run apply_merges in memory with the entry added: no new orphaned entity, and the
             entry has the effect it claims (a deleted intervention is gone, a reassignment
             points to a catalog entity, a patched or inserted one is there).

Nothing under --data-dir is written: gates 4–5 work on a temporary copy of corrections/.
Dropped proposals go to runs.jsonl with their reason (unless --no-state).

    "$PY" scripts/qa/verify_proposals.py --input agent.json --output verified.json [--agent NAME]
    "$PY" scripts/qa/verify_proposals.py --input agent.json --data-dir "$TMPDIR/bt/data" --no-state

Input and output: propose.py's format (a JSON list of {fp, check, severity, subject, title,
message, evidence: {file, quote}, file, section?, entry, op?}).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa import proposals as P  # noqa: E402
from qa.model import REPO_ROOT, Context, state_dir  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
MIN_QUOTE_WORDS = 4
MIN_TEXT_FIDELITY = 0.9   # the first real backtest: 186 of 190 sentences, all ≥ 0.96 per speech

# ── 1–2. Quote normalisation ─────────────────────────────────────────────────

_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "«": '"', "»": '"', "‘": "'", "’": "'",
                         "´": "'", "`": "'", "–": "-", "—": "-", "‒": "-", "−": "-", "­": ""})
# A hyphen right before a line break. pdftotext indents the next line, so the break is `-` plus
# any whitespace. In the citizen sections these are mostly dashes closing an aside
# ("en castellano-\n   infecta"), not split words, so both readings are tried (see `forms`).
_LINE_HYPHEN = re.compile(r"(?<=\w)-[ \t]*\n\s*(?=\w)")
_HYPHEN_SPACE = re.compile(r"(?<=\w)-\s+(?=\w)")
_WS = re.compile(r"\s+")


def _base(text: str) -> str:
    return text.translate(_QUOTES)


def forms(text: str, *, source: bool) -> tuple[str, str]:
    """(joined, kept): the text with line-end hyphens removed, and with them kept.

    The acta (`source`) only has the ambiguous hyphen before a newline; a quote may have
    copied it as `- ` or dropped it, so in a quote the same reading applies to `-` + spaces."""
    t = _base(text)
    pat = _LINE_HYPHEN if source else _HYPHEN_SPACE
    joined = _WS.sub(" ", pat.sub("", t)).strip().lower()
    kept = _WS.sub(" ", pat.sub("-", t)).strip().lower()
    return joined, kept


def quote_in(quote: str, source_forms: tuple[str, str]) -> bool:
    q = forms(quote, source=False)
    if q[0] in source_forms[0] or q[1] in source_forms[1]:
        return True
    # a dash and a space in the middle of a line ("2.000 euros- por"), copied as it is
    return _WS.sub(" ", _base(quote)).strip().lower() in source_forms[1]


def strip_page_headers(text: str) -> str:
    """Drop the running page headers ("ACTA DE PLE", "SESIÓN ORDINARIA DE 28 DE DICIEMBRE DE
    2012"…): upper-case lines repeated on several pages. A speech that crosses a page break has one
    in the middle of a sentence, and the sentence is then not found in the acta."""
    lines = text.replace("\f", "\n").splitlines()
    count = Counter(l.strip() for l in lines)
    def header(l: str) -> bool:
        s = l.strip()
        return count[s] >= 3 and sum(c.isalpha() for c in s) >= 3 and s == s.upper()
    return "\n".join(l for l in lines if not header(l))


def acta_forms(text: str) -> tuple[str, str]:
    """The acta as it is and without its page headers, so a quote may match either: the filter
    also drops section titles ("RESPOSTA", "ACORD"), which a quote might include."""
    return forms(text + "\n\n" + strip_page_headers(text), source=True)


# ── Verifier ─────────────────────────────────────────────────────────────────

class Verifier:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.ctx = Context(self.data_dir)
        self._acta_cache: dict[str, tuple[str, str] | None] = {}
        self.raw_by_id = {str(iv.get("id")): iv for iv in self.ctx.interventions_raw}
        manual = self.ctx.corrections("manual_interventions.yml") or []
        self.manual_by_id = {str(m.get("id")): m for m in manual if isinstance(m, dict)}
        self.pleno_ids = ({s.get("id") for s in self.ctx.sessions_metadata}
                          | {s.get("id") for s in self.ctx.sessions_index})
        self.tmp = Path(tempfile.mkdtemp(prefix="lcp-verify-"))
        self._baseline = None
        self._root: Path | None = None
        self._snap: dict[str, bytes] = {}

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # gate 1–2
    def acta(self, rel: str) -> tuple[str, str] | None:
        if rel not in self._acta_cache:
            name = Path(rel).name
            p = self.data_dir / "raw" / "texts" / name
            ok = rel.replace("\\", "/").endswith(f"raw/texts/{name}") and p.exists()
            self._acta_cache[rel] = acta_forms(p.read_text(errors="replace")) if ok else None
        return self._acta_cache[rel]

    def iv(self, iv_id: str) -> dict | None:
        return self.raw_by_id.get(iv_id) or self.manual_by_id.get(iv_id)

    def check_quote(self, prop: dict) -> str | None:
        ev = prop.get("evidence") or {}
        quote, rel = (ev.get("quote") or "").strip(), ev.get("file") or ""
        if len(quote.split()) < MIN_QUOTE_WORDS:
            return f"quote: missing or shorter than {MIN_QUOTE_WORDS} words"
        acta = self.acta(rel)
        if acta is None:
            return f"quote: evidence file {rel!r} is not an acta under raw/texts/"
        subject_iv = self.iv(str(prop.get("subject")))
        pleno = (subject_iv or {}).get("pleno_id") or (prop.get("entry") or {}).get("pleno_id")
        if pleno and Path(rel).stem != pleno:
            return f"quote: evidence is from {Path(rel).stem}, the subject is in pleno {pleno}"
        if quote_in(quote, acta):
            return self.check_text_fidelity(prop, acta)
        if subject_iv:
            for field in ("text_cas", "text_val"):
                text = (subject_iv.get(field) or "").replace("**", "")
                if text and quote_in(quote, forms(text, source=True)):
                    return f"idioma: the quote is from {field} (a translation), not from the acta"
        return "quote: not found in the acta"

    def check_text_fidelity(self, prop: dict, acta: tuple[str, str]) -> str | None:
        """A text an agent copies from the acta (a missed speech, a restored truncated one) must be
        the acta's: the quote alone proves the speaker exists, not that the speech is not invented.
        Sentence by sentence, to tolerate page headers that pdftotext drops in the middle."""
        entry = prop.get("entry") or {}
        text = entry.get("text_original") or (entry.get("fields") or {}).get("text_original")
        if not text:
            return None
        sents = [s for s in re.split(r"(?<=[.!?…])\s+", text.replace("**", "")) if len(s.split()) >= 6]
        if not sents:
            return None
        found = sum(quote_in(s, acta) for s in sents)
        if found / len(sents) < MIN_TEXT_FIDELITY:
            return (f"text: only {found} of {len(sents)} sentences of text_original are in the acta "
                    f"(needs {MIN_TEXT_FIDELITY:.0%})")
        return None

    def warnings(self, prop: dict) -> list[str]:
        """Not reasons to drop, but worth a look in the PR."""
        out = []
        if prop.get("file") == "new_entities.yml":
            from qa.checks.entities import entity_similarity
            new = {"id": "?", **(prop.get("entry") or {})}
            for e in self.ctx.entitats:
                sim = entity_similarity(new, e)
                if sim >= 0.6:
                    out.append(f"looks like the existing entity {e['id']} ({e.get('nom_val')!r}, "
                               f"{sim:.2f}): map the text to it with variant_map_forced instead?")
        return out[:3]

    # gate 3
    def check_ids(self, prop: dict) -> str | None:
        file, entry = prop.get("file"), prop.get("entry") or {}
        subject = str(prop.get("subject") or "")
        if file == "manual_interventions.yml":
            if entry.get("pleno_id") not in self.pleno_ids:
                return f"ids: pleno_id {entry.get('pleno_id')!r} is not a known session"
            if str(entry.get("id")) in self.raw_by_id and prop.get("op") != "replace":
                return f"ids: intervention {entry.get('id')!r} already exists"
            if not str(entry.get("id") or "").startswith(f"{entry.get('pleno_id')}-"):
                return f"ids: id {entry.get('id')!r} does not follow {{pleno_id}}-NNN"
            return None
        iv_id = entry.get("iv_id") or entry.get("base_id")
        for ref in [iv_id, *(entry.get("merge_ids") or [])]:
            if ref is not None and self.iv(str(ref)) is None:
                return f"ids: intervention {ref!r} does not exist"
        if iv_id is None and subject and subject not in self.pleno_ids and self.iv(subject) is None \
                and file not in ("entity_merges.yml", "variant_map_forced.yml", "new_entities.yml"):
            return f"ids: subject {subject!r} is neither an intervention nor a pleno"
        catalog = {e["id"] for e in self.ctx.entitats}
        corr = Context(self._root) if self._root else self.ctx   # includes entities accepted in this batch
        new_ids = {e.get("id") for e in corr.corrections("new_entities.yml") or []}
        canon = {m.get("canonical_id") for m in corr.corrections("entity_merges.yml") or []}
        known = catalog | new_ids | canon
        for key in ("entitat_id", "entity_id"):
            eid = entry.get(key)
            if eid and eid not in known and not (file == "deletions.yml"):
                return f"ids: entity {eid!r} is not in the catalog, new_entities or a merge"
        cessio = entry.get("entitat_cessio") or {}
        if cessio.get("entitat_id") and cessio["entitat_id"] not in known:
            return f"ids: entitat_cessio.entitat_id {cessio['entitat_id']!r} is not a catalog entity"
        return None

    # gate 4
    def _overlay(self) -> Path:
        """A data dir in tmp: corrections/ copied, everything else linked (read-only use).

        Created once per batch and kept: every accepted proposal stays in it, so a later one can
        rely on an earlier one (an intervention from a missed speaker on the new entity proposed
        just before). A rejected proposal is rolled back with `_restore`."""
        if self._root is None:
            root = self.tmp / "data"
            root.mkdir(parents=True)
            for child in self.data_dir.iterdir():
                if child.name == "corrections":
                    # copyfile, not copy2: the source may be read-only (a backtest's chmod a-w
                    # data/), and the overlay must stay writable
                    shutil.copytree(child, root / "corrections", copy_function=shutil.copyfile)
                else:
                    (root / child.name).symlink_to(child)
            self._root = root
        return self._root

    def _snapshot(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in (self._overlay() / "corrections").iterdir() if p.is_file()}

    def _restore(self, snap: dict[str, bytes]) -> None:
        corr = self._overlay() / "corrections"
        for p in corr.iterdir():
            if p.is_file() and p.name not in snap:
                p.unlink()
        for name, data in snap.items():
            (corr / name).write_bytes(data)

    def check_n7(self, prop: dict) -> tuple[str | None, Path | None]:
        root = self._overlay()
        self._snap = self._snapshot()
        reason = self._append_and_n7(prop, root)
        if reason:
            self._restore(self._snap)
            return reason, None
        return None, root

    def _append_and_n7(self, prop: dict, root: Path) -> str | None:
        entry = dict(prop.get("entry") or {})
        entry.setdefault("reason", prop.get("title"))
        entry.setdefault("date", P.today())
        entry.setdefault("finding", prop.get("fp"))
        try:
            schema = P.schema_for(prop.get("file"), prop.get("section"))
            replace = prop.get("op") == "replace"
            if prop.get("op", "append") in ("append", "replace"):
                key = str(entry.get(schema.key))
                doc = Context(root).corrections(prop["file"])
                items = (doc or {}).get(prop.get("section")) or [] if prop.get("section") else (doc or [])
                exists = any(isinstance(e, dict) and str(e.get(schema.key)) == key for e in items)
                if replace and not exists:
                    replace = False          # nothing to replace: the agent meant a new entry
                    prop["op"] = "append"
                elif not replace and exists and prop["file"] == "patches.yml":
                    replace = True           # one patch per intervention: replace_entry merges the fields
                    prop["op"] = "replace"
            if replace:
                P.replace_entry(root / "corrections", prop["file"], prop.get("section"), entry)
            else:
                P.append_entry(root / "corrections", prop["file"], prop.get("section"), entry)
        except (P.ProposalError, KeyError, TypeError) as e:
            return f"N7: {e}"
        from qa import run_checks
        from qa.model import REGISTRY
        run_checks.load_checks()
        subject = f"{prop['file']}|{entry[schema.key]}"
        for f in REGISTRY["N7"].fn(Context(root, repo_root=REPO_ROOT)):
            if f.subject == subject and f.severity != "P3":
                return f"N7: {f.key}: {f.message}"
        return None

    # gate 5
    def _apply(self, data_dir: Path) -> dict:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import apply_merges
        return apply_merges.apply_corrections(apply_merges.load_inputs(data_dir), log=lambda *_: None)

    def baseline(self) -> dict:
        if self._baseline is None:
            self._baseline = self._apply(self.data_dir)
        return self._baseline

    def check_dry_run(self, prop: dict, root: Path) -> str | None:
        try:
            result = self._apply(root)
        except Exception as e:  # a correction that crashes apply_merges never reaches the PR
            return f"dry-run: apply_merges failed: {type(e).__name__}: {e}"
        new_orphans = result["orphaned"] - self.baseline()["orphaned"]
        if new_orphans:
            return f"dry-run: leaves orphaned entity ids {sorted(new_orphans)}"
        file, entry = prop["file"], prop.get("entry") or {}
        ids = {iv["id"] for iv in result["interventions"]}
        entity_ids = {e["id"] for e in result["entities"]}
        if file == "deletions.yml" and prop.get("section") == "interventions" and entry.get("iv_id") in ids:
            return f"dry-run: {entry['iv_id']} is still there after the deletion"
        if file in ("patches.yml", "reassignments.yml") and entry.get("iv_id") not in ids:
            return f"dry-run: {entry.get('iv_id')} is not in the result (deleted elsewhere?)"
        if file == "manual_interventions.yml" and str(entry.get("id")) not in ids:
            return f"dry-run: {entry.get('id')} is not in the result"
        if file == "reassignments.yml" and entry.get("entitat_id") not in entity_ids:
            return f"dry-run: entitat_id {entry.get('entitat_id')!r} is not in the resulting catalog"
        # The changed interventions must not gain a C1 error (taxonomy, CAP, ambit, tipus…):
        # N7 checks a patch's shape, not the values it writes.
        # Only interventions that existed before: a manual insert has no classification yet (the
        # enrichment scripts add it), so every C1 error on it would be "new".
        before_ids = {iv["id"] for iv in self.baseline()["interventions"]}
        touched = {str(entry.get(k)) for k in ("iv_id", "id", "base_id") if entry.get(k)} & before_ids
        if touched:
            from qa.checks.classification import validation_errors
            after = [iv for iv in result["interventions"] if iv["id"] in touched]
            before = [iv for iv in self.baseline()["interventions"] if iv["id"] in touched]
            new = set(validation_errors(self.ctx, after)) - set(validation_errors(self.ctx, before))
            if new:
                return f"dry-run: C1 {sorted(new)[0]}"
        return None

    def verify(self, prop: dict) -> str | None:
        """None if the proposal passes, else the reason it is dropped."""
        if prop.get("file") not in {s.file for s in P.SCHEMAS}:
            return f"N7: unknown corrections file {prop.get('file')!r}"
        reason = self.check_quote(prop) or self.check_ids(prop)
        if reason:
            return reason
        reason, root = self.check_n7(prop)
        if reason:
            return reason
        reason = self.check_dry_run(prop, root)
        if reason:
            self._restore(self._snap)
        return reason


# Entities first: an intervention from a missed speaker may need the entity proposed with it.
FILE_ORDER = ("new_entities.yml", "variant_map_forced.yml", "entity_merges.yml")


def verify_all(proposals: list[dict], data_dir: Path) -> tuple[list[dict], list[dict]]:
    """Verify in order, each proposal on top of the ones accepted before it."""
    v = Verifier(data_dir)
    try:
        accepted, rejected = [], []
        order = {f: i for i, f in enumerate(FILE_ORDER)}
        for prop in sorted(proposals, key=lambda p: order.get(p.get("file"), len(FILE_ORDER))):
            reason = v.verify(prop)
            if reason:
                rejected.append({"fp": prop.get("fp"), "check": prop.get("check"),
                                 "subject": prop.get("subject"), "reason": reason})
            else:
                warn = v.warnings(prop)
                if warn:   # shown in the PR next to the proposal, for the reviewer to decide
                    prop["warnings"] = warn
                    prop["message"] = ((prop.get("message") or "") + "\n\n⚠️ " + "\n⚠️ ".join(warn)).strip()
                accepted.append(prop)
        return accepted, rejected
    finally:
        v.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, help="accepted proposals (propose.py --input format)")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--agent", default="manual", help="recorded in runs.jsonl")
    ap.add_argument("--no-state", action="store_true", help="do not write runs.jsonl")
    args = ap.parse_args(argv)

    proposals = json.loads(args.input.read_text())
    accepted, rejected = verify_all(proposals, args.data_dir)
    for r in rejected:
        print(f"  - {r['fp']} ({r['subject']}): {r['reason']}")
    print(f"verify: {len(accepted)} accepted, {len(rejected)} dropped of {len(proposals)}")
    if args.output:
        args.output.write_text(json.dumps(accepted, ensure_ascii=False, indent=2))
    if not args.no_state:
        from qa.run_checks import State
        State(state_dir()).append("runs.jsonl", [{
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "trigger": "verify", "agent": args.agent, "proposals": len(proposals),
            "accepted": len(accepted), "dropped": len(rejected),
            "drop_rate": round(len(rejected) / len(proposals), 3) if proposals else 0.0,
            "reasons": rejected,
        }])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

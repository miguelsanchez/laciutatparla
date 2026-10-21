"""Proposals of the QA data PR: shared by propose.py, sync.py and apply.sh (§6.3).

A proposal is one correction entry for data/corrections/*.yml, with the finding that justifies
it. The branch of the qa-data PR carries the list in meta/qa/proposals.json, so the PR body, the
rejects and a rebase onto main are all rebuilt from it:

    {"branch": "qa/2026-10", "proposals": [
       {"fp": "C1-…", "check": "C1", "severity": "P2", "subject": "2018-01-25-101",
        "title": "…", "message": "…", "evidence": {"file": …, "quote": …},
        "file": "patches.yml", "section": null, "entry": {…},
        "op": "append" | "replace" | "delete",
        "yaml_text": "<exact text written to the file; empty for a delete>",
        "old_text": "<replace and delete: the block it replaced or removed>",
        "status": "proposed" | "rejected" | "queued", "reject_reason": null}]}

YAML is only ever edited as text: an entry is appended at the end of its list (or of its section
in deletions.yml), or — op "replace" — an existing entry written by propose.py is swapped for a new
version, or — op "delete" — removed (an entry left dead by a merge), and a reject removes, swaps
back or re-appends exactly that block. Re-dumping a whole file would
reformat it (several do not survive a yaml load/dump round trip).
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import yaml

from qa.schemas import SCHEMAS, Schema

PROPOSALS_FILE = "meta/qa/proposals.json"
TEMPLATE = Path(__file__).with_name("templates") / "pr_body.md"
MAX_PER_PR = 10
BODY_BUDGET = 60_000   # GitHub rejects a PR body over 65 536 chars; data_diff and merge_body add a little
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


class ProposalError(ValueError):
    pass


# ── The proposals file ───────────────────────────────────────────────────────

def load(worktree: Path) -> dict:
    """The proposals of the branch checked out in worktree.

    main carries the file of the last merged data PR, so a branch cut from main without propose.py
    (a hand-made data PR, #103) inherits proposals that are already applied: the file names its
    branch, and on any other branch it counts as empty. Outside a git repo it is read as is."""
    p = worktree / PROPOSALS_FILE
    doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"branch": None, "proposals": []}
    current = subprocess.run(["git", "branch", "--show-current"], cwd=worktree, text=True,
                             capture_output=True).stdout.strip()
    if current and doc.get("branch") and doc["branch"] != current:
        return {"branch": current, "proposals": []}
    return doc


def save(worktree: Path, doc: dict) -> None:
    p = worktree / PROPOSALS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def active(doc: dict) -> list[dict]:
    return [p for p in doc["proposals"] if p["status"] == "proposed"]


# ── Text-only YAML editing ───────────────────────────────────────────────────

def schema_for(file: str, section: str | None) -> Schema:
    for s in SCHEMAS:
        if s.file == file and s.section == section:
            return s
    raise ProposalError(f"no schema for {file}{':' + section if section else ''}")


def render_entry(entry: dict, indent: str = "") -> str:
    text = yaml.safe_dump([entry], allow_unicode=True, sort_keys=False, width=100)
    return "".join(indent + line if line.strip() else line for line in text.splitlines(keepends=True))


def has_entry(corrections_dir: Path, file: str, section: str | None, entry: dict) -> bool:
    """Whether the file already holds an entry with entry's key."""
    schema = schema_for(file, section)
    path = corrections_dir / file
    doc = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or ([] if section is None else {})
    items = (doc.get(section) or []) if section else doc
    return any(isinstance(e, dict) and str(e.get(schema.key)) == str(entry[schema.key]) for e in items)


def append_entry(corrections_dir: Path, file: str, section: str | None, entry: dict) -> str:
    """Append entry to its list; return the exact text added (for a later reject)."""
    schema = schema_for(file, section)
    missing = [k for k in schema.required if entry.get(k) in (None, "", [])]
    if missing:
        raise ProposalError(f"{file}: entry lacks {missing}")
    path = corrections_dir / file
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    doc = yaml.safe_load(text) or ([] if section is None else {})
    items = (doc.get(section) or []) if section else doc
    key = str(entry[schema.key])
    if any(str(e.get(schema.key)) == key for e in items if isinstance(e, dict)):
        raise ProposalError(f"{file}: an entry with {schema.key}={key!r} already exists; edit it by hand")
    if section is None:
        block = render_entry(entry)
        # an empty list is written `[]` (often under a comment header): drop that line
        kept = [l for l in text.splitlines(keepends=True) if l.strip() != "[]"]
        head = "".join(kept).rstrip("\n")
        new = (head + "\n" if head else "") + block
    else:
        new, block = _append_in_section(text, section, entry)
    path.write_text(new, encoding="utf-8")
    # The file must still parse and now hold the entry
    check = yaml.safe_load(new)
    items = (check.get(section) or []) if section else check
    if not any(str(e.get(schema.key)) == key for e in items if isinstance(e, dict)):
        path.write_text(text, encoding="utf-8")
        raise ProposalError(f"{file}: the appended entry did not parse back")
    return block


def _append_in_section(text: str, section: str, entry: dict) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    try:
        start = next(i for i, l in enumerate(lines) if l.rstrip() == f"{section}:")
    except StopIteration:
        block = f"{section}:\n" + render_entry(entry)
        return text.rstrip("\n") + "\n" + block, block
    end = start + 1
    while end < len(lines) and (lines[end].startswith((" ", "-", "\t")) or not lines[end].strip()):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    indent = "" if end > start + 1 and lines[start + 1].startswith("-") else "  "
    block = render_entry(entry, indent)
    return "".join(lines[:end]) + block + "".join(lines[end:]), block


def replace_entry(corrections_dir: Path, file: str, section: str | None, entry: dict) -> tuple[str, str]:
    """Swap the existing entry with the same key for `entry`; return (new_block, old_block).

    Works on entries in propose.py's own layout (the exact render_entry text): that covers every
    entry added by the QA cycle. A hand-formatted entry has to be edited by hand.
    """
    schema = schema_for(file, section)
    path = corrections_dir / file
    text = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text) or ([] if section is None else {})
    items = (doc.get(section) or []) if section else doc
    key = str(entry[schema.key])
    current = [e for e in items if isinstance(e, dict) and str(e.get(schema.key)) == key]
    if len(current) != 1:
        raise ProposalError(f"{file}: {len(current)} entries with {schema.key}={key!r}; replace needs exactly one")
    if file == "patches.yml" and isinstance(current[0].get("fields"), dict) and isinstance(entry.get("fields"), dict):
        # An intervention has one patch: a new one for it keeps the fields it does not touch. The
        # classification auditor does not see the existing patch, and once dropped a language fix.
        entry = {**entry, "fields": {**current[0]["fields"], **entry["fields"]}}
    for indent in ("", "  "):
        old = render_entry(current[0], indent)
        if text.count(old) == 1:
            new = render_entry(entry, indent)
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            check = yaml.safe_load(path.read_text(encoding="utf-8"))
            got = [e for e in ((check.get(section) or []) if section else check)
                   if isinstance(e, dict) and str(e.get(schema.key)) == key]
            if got != [entry]:
                path.write_text(text, encoding="utf-8")
                raise ProposalError(f"{file}: the replaced entry did not parse back")
            return new, old
    raise ProposalError(f"{file}: the entry {schema.key}={key!r} is not in propose.py's layout; edit it by hand")


def delete_entry(corrections_dir: Path, file: str, section: str | None, entry: dict) -> str:
    """Remove the existing entry with entry's key; return the block removed (for a reject).

    Same layout rule as replace_entry. Only the key of `entry` is used."""
    schema = schema_for(file, section)
    path = corrections_dir / file
    text = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text) or ([] if section is None else {})
    items = (doc.get(section) or []) if section else doc
    key = str(entry[schema.key])
    current = [e for e in items if isinstance(e, dict) and str(e.get(schema.key)) == key]
    if len(current) != 1:
        raise ProposalError(f"{file}: {len(current)} entries with {schema.key}={key!r}; delete needs exactly one")
    for indent in ("", "  "):
        old = render_entry(current[0], indent)
        if text.count(old) == 1:
            path.write_text(text.replace(old, "", 1), encoding="utf-8")
            check = yaml.safe_load(path.read_text(encoding="utf-8")) or ([] if section is None else {})
            left = (check.get(section) or []) if section else check
            if any(isinstance(e, dict) and str(e.get(schema.key)) == key for e in left):
                path.write_text(text, encoding="utf-8")
                raise ProposalError(f"{file}: the deleted entry is still there")
            return old
    raise ProposalError(f"{file}: the entry {schema.key}={key!r} is not in propose.py's layout; edit it by hand")


def apply_op(corrections_dir: Path, p: dict) -> tuple[str, str | None]:
    """Write proposal p into its file; return (yaml_text, old_text)."""
    op, file, section, entry = p.get("op", "append"), p["file"], p.get("section"), p["entry"]
    if op == "replace":
        return replace_entry(corrections_dir, file, section, entry)
    if op == "delete":
        return "", delete_entry(corrections_dir, file, section, entry)
    return append_entry(corrections_dir, file, section, entry), None


def applied(corrections_dir: Path, p: dict, doc: dict | None = None) -> bool:
    """Whether p is still in its file: its block for append/replace, its key gone for a delete.

    With doc, a block that a later proposal of the same PR replaced (and so merged into its own,
    see replace_entry) also counts: two patches for one intervention in one PR."""
    if p.get("op") != "delete":
        if block_present(corrections_dir, p["file"], p["yaml_text"]):
            return True
        return doc is not None and any(
            q is not p and q.get("op") == "replace" and q.get("old_text") == p["yaml_text"]
            and q.get("status") == "proposed" and applied(corrections_dir, q, doc)
            for q in doc["proposals"])
    schema = schema_for(p["file"], p.get("section"))
    path = corrections_dir / p["file"]
    doc = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or {}
    items = (doc.get(p["section"]) or []) if p.get("section") else doc
    key = str(p["entry"][schema.key])
    return not any(isinstance(e, dict) and str(e.get(schema.key)) == key for e in items)


def remove_block(corrections_dir: Path, file: str, block: str) -> bool:
    path = corrections_dir / file
    text = path.read_text(encoding="utf-8")
    if text.count(block) != 1:
        return False
    path.write_text(text.replace(block, "", 1), encoding="utf-8")
    return True


def swap_block(corrections_dir: Path, file: str, block: str, replacement: str) -> bool:
    path = corrections_dir / file
    text = path.read_text(encoding="utf-8")
    if text.count(block) != 1:
        return False
    path.write_text(text.replace(block, replacement, 1), encoding="utf-8")
    return True


def undo(corrections_dir: Path, p: dict) -> bool:
    """Take a proposal back out of the file: remove an append, swap a replace back, re-append a
    delete (at the end of its list: the order of these entries carries no meaning)."""
    if p.get("op") == "replace":
        return swap_block(corrections_dir, p["file"], p["yaml_text"], p["old_text"])
    if p.get("op") == "delete":
        try:
            append_entry(corrections_dir, p["file"], p.get("section"), yaml.safe_load(p["old_text"])[0])
        except ProposalError:
            return False
        return True
    return remove_block(corrections_dir, p["file"], p["yaml_text"])


def block_present(corrections_dir: Path, file: str, block: str) -> bool:
    path = corrections_dir / file
    return path.exists() and block in path.read_text(encoding="utf-8")


def subject_hash(p: dict) -> str:
    """The finding's own subject hash (Finding.subject_hash), for `until_changed`. Empty when the
    check does not compute one: the suppression then holds for as long as the finding exists."""
    return p.get("subject_hash") or ""


def today() -> str:
    return dt.date.today().isoformat()


# ── PR body ──────────────────────────────────────────────────────────────────

def _cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def render_body(doc: dict, data_diff: str | None = None) -> str:
    props = sorted(doc["proposals"], key=lambda p: (SEVERITY_ORDER.get(p["severity"], 9), p["check"]))
    live = [p for p in props if p["status"] == "proposed"]
    rejected = [p for p in props if p["status"] == "rejected"]
    rows = []
    for p in live:
        quote = (p.get("evidence") or {}).get("quote")
        evidence = f"«{_cell(quote)}»" if quote else _cell((p.get("evidence") or {}).get("file") or "—")
        box = "☐ " if p["severity"] in ("P0", "P1") else ""
        rows.append(f"| {box}{p['severity']} | {p['check']} | {_cell(p['subject'])} | {_cell(p['title'])} "
                    f"| {evidence} | `{p['file']}` | `{p['fp']}` |")
    def details(max_yaml: int | None) -> str:
        out = []
        for p in live:
            verb = {"replace": "replaces the existing entry in",
                    "delete": "deleted from"}.get(p.get("op"), "appended to")
            yaml_text = p["old_text"] if p.get("op") == "delete" else p["yaml_text"]
            if max_yaml and len(yaml_text) > max_yaml:
                yaml_text = yaml_text[:max_yaml].rstrip() + f"\n# … {len(p['yaml_text'])} chars in all: see the diff\n"
            out.append(f"<details><summary><code>{p['fp']}</code> · {_cell(p['title'])}</summary>\n\n"
                       f"{p.get('message') or ''}\n\n```yaml\n# {verb} data/corrections/{p['file']}"
                       f"{' · ' + p['section'] if p.get('section') else ''}\n{yaml_text}```\n</details>")
        return "\n\n".join(out)

    rej = "\n".join(f"- ~~`{p['fp']}`~~ {_cell(p['title'])}: {_cell(p.get('reject_reason'))}" for p in rejected)
    rejects = "\n".join(f"   reject {p['fp']}" for p in live)  # indented: inside a list item
    tpl = TEMPLATE.read_text(encoding="utf-8")
    body = (tpl.replace("{{BRANCH}}", doc.get("branch") or "")
               .replace("{{COUNT}}", str(len(live)))
               .replace("{{ROWS}}", "\n".join(rows) or "| — | | | (no live proposals) | | | |")
               .replace("{{REJECT_LINES}}", rejects or "   (none)")
               .replace("{{REJECTED}}", rej or "_None._")
               .replace("{{DATA_DIFF}}", data_diff or "_Not applied yet: run `/apply-approved` on the dedicated Mac._"))
    # A big batch (long texts, or more than MAX_PER_PR proposals) must still fit in a PR body:
    # shorten each entry, and as a last resort leave the entries to the diff.
    for max_yaml in (None, 600):
        full = body.replace("{{DETAILS}}", details(max_yaml))
        if len(full) <= BODY_BUDGET:
            return full
    return body.replace("{{DETAILS}}", "_The entries do not fit in the PR body: see the diff._")


QA_START, QA_END = "<!-- qa:start -->", "<!-- qa:end -->"


def merge_body(current: str | None, qa_section: str) -> str:
    """Put the QA section between markers, keeping whatever else the PR body says (an ingest/*
    PR from /update-plenos has its own description)."""
    block = f"{QA_START}\n{qa_section.rstrip()}\n{QA_END}"
    current = current or ""
    if QA_START in current and QA_END in current:
        head, rest = current.split(QA_START, 1)
        return head + block + rest.split(QA_END, 1)[1]
    return (current.rstrip() + "\n\n---\n\n" if current.strip() else "") + block


def update_pr_body(cwd: Path, number: int, doc: dict, data_diff: str | None = None) -> None:
    import tempfile
    current = run(["gh", "pr", "view", str(number), "--json", "body", "--jq", ".body"], cwd=cwd)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(merge_body(current, render_body(doc, data_diff)))
    try:
        run(["gh", "pr", "edit", str(number), "--body-file", fh.name], cwd=cwd)
    finally:
        Path(fh.name).unlink(missing_ok=True)


# ── git / gh ─────────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: Path | None = None, check: bool = True, capture: bool = True) -> str:
    r = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{(r.stderr or r.stdout or '').strip()}")
    return (r.stdout or "").strip()


def open_data_pr(cwd: Path) -> dict | None:
    """The single open qa-data PR (ingest/* or qa/*), if any."""
    out = run(["gh", "pr", "list", "--label", "qa-data", "--state", "open",
               "--json", "number,headRefName,url,title", "--limit", "5"], cwd=cwd)
    prs = json.loads(out or "[]")
    if len(prs) > 1:
        raise RuntimeError(f"{len(prs)} qa-data PRs are open; there must be one at most: "
                           + ", ".join(f"#{p['number']}" for p in prs))
    return prs[0] if prs else None

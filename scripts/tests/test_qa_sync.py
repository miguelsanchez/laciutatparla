"""propose.py / sync.py: text-only YAML edits, commits per finding, rejects (F1.2–F1.4).

Everything runs in a throwaway git repo shaped like the QA worktree; no network, no gh.
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from qa import proposals as P
from qa import propose, sync

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]


@pytest.fixture
def wt(tmp_path, monkeypatch):
    """A tiny repo with the files propose/sync touch, plus data N7 needs."""
    root = tmp_path / "lcp-qa"
    (root / "data/corrections").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / "meta/qa").mkdir(parents=True)
    (root / "data/corrections/patches.yml").write_text("# header comment\n[]\n")
    (root / "data/corrections/deletions.yml").write_text(
        "interventions:\n- iv_id: '2026-01-01-009'\n  reason: old\nentities:\n- entity_id: x\n  reason: ''\n")
    (root / "meta/qa/suppressions.yml").write_text("# rejected findings\n[]\n")
    ivs = [{"id": f"2026-01-01-00{i}", "pleno_id": "2026-01-01"} for i in range(1, 4)]
    (root / "data/raw/interventions_raw.json").write_text(json.dumps(ivs))
    (root / "data/intervencions.json").write_text(json.dumps(ivs))
    (root / "data/entitats.json").write_text("[]")
    (root / "data/raw/sessions_index.json").write_text(json.dumps([{"id": "2026-01-01"}]))
    subprocess.run(["git", "init", "-q", "-b", "qa/test", str(root)], check=True)
    subprocess.run([*GIT, "-C", str(root), "add", "."], check=True)
    subprocess.run([*GIT, "-C", str(root), "commit", "-qm", "init"], check=True)
    monkeypatch.setenv("LCP_QA_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t"); monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t"); monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    monkeypatch.setattr(P, "run", lambda cmd, cwd=None, check=True, capture=True: subprocess.run(
        [*cmd[:1], "-c", "core.hooksPath=/dev/null", *cmd[1:]] if cmd[0] == "git" else cmd,
        cwd=cwd, check=check, capture_output=True, text=True).stdout.strip())
    return root


def prop(i, sev="P2", file="patches.yml", section=None, entry=None):
    return {"fp": f"C1-{i:010x}", "check": "C1", "severity": sev, "subject": f"2026-01-01-00{i}",
            "title": f"fix {i}", "message": "m", "evidence": {"quote": "una cita"},
            "file": file, "section": section,
            "entry": entry or {"iv_id": f"2026-01-01-00{i}", "fields": {"ambit": "ciutat"}}}


def log(root):
    return subprocess.run(["git", "-C", str(root), "log", "--format=%s"], capture_output=True,
                          text=True).stdout.splitlines()


def test_append_keeps_header_and_parses(wt):
    block = P.append_entry(wt / "data/corrections", "patches.yml", None,
                           {"iv_id": "2026-01-01-001", "fields": {"ambit": "ciutat"}})
    text = (wt / "data/corrections/patches.yml").read_text()
    assert text.startswith("# header comment\n") and "[]" not in text
    assert yaml.safe_load(text)[0]["iv_id"] == "2026-01-01-001"
    assert P.remove_block(wt / "data/corrections", "patches.yml", block)


def test_append_in_section_and_duplicate(wt):
    P.append_entry(wt / "data/corrections", "deletions.yml", "interventions",
                   {"iv_id": "2026-01-01-002", "reason": "r"})
    doc = yaml.safe_load((wt / "data/corrections/deletions.yml").read_text())
    assert [e["iv_id"] for e in doc["interventions"]] == ["2026-01-01-009", "2026-01-01-002"]
    assert doc["entities"] == [{"entity_id": "x", "reason": ""}]
    with pytest.raises(P.ProposalError):
        P.append_entry(wt / "data/corrections", "deletions.yml", "interventions",
                       {"iv_id": "2026-01-01-002", "reason": "again"})


def test_one_commit_per_finding_cap_and_n7(wt):
    doc = {"branch": "qa/test", "proposals": []}
    bad = prop(9, entry={"iv_id": "2099-01-01-001", "fields": {"ambit": "ciutat"}})  # unknown iv: N7 refuses
    many = [prop(i) for i in range(1, 4)] + [bad]
    monkeypatch_cap = P.MAX_PER_PR
    P.MAX_PER_PR = 2
    try:
        added, overflow = propose.add_proposals(wt, doc, many)
    finally:
        P.MAX_PER_PR = monkeypatch_cap
    assert [p["fp"] for p in added] == ["C1-0000000001", "C1-0000000002"]
    assert [p["fp"] for p in overflow] == ["C1-0000000003", "C1-0000000009"]
    assert log(wt)[:2] == ["qa(C1): fix 2", "qa(C1): fix 1"]
    entries = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert all(e["reason"] and e["date"] and e["finding"] for e in entries)
    body = P.render_body(doc)
    assert "reject C1-0000000001" in body and "«una cita»" in body


def test_new_entity_is_committed_after_the_intervention_that_uses_it(wt):
    """Each commit passes the pre-commit hook alone; N7 only accepts a new entity once an
    intervention in the branch resolves to it (the #63 data PR failed on this order)."""
    doc = P.load(wt)
    doc["branch"] = "qa/test"
    entity = prop(1, sev="P1", file="new_entities.yml",
                  entry={"id": "afa-nova", "nom_cas": "AFA Nova", "nom_val": "AFA Nova", "tipus": "educacio"})
    manual = prop(2, sev="P1", file="manual_interventions.yml",
                  entry={"id": "2026-01-01-101", "pleno_id": "2026-01-01", "intervinient": "X",
                         "entitat": "AFA Nova", "text_original": "Bon dia."})
    added, _ = propose.add_proposals(wt, doc, [entity, manual])
    assert [a["file"] for a in added] == ["manual_interventions.yml", "new_entities.yml"]
    assert log(wt)[:2] == ["qa(C1): fix 1", "qa(C1): fix 2"]   # newest first: entity last


def test_n7_rejects_unknown_intervention(wt):
    doc = {"branch": "qa/test", "proposals": []}
    added, _ = propose.add_proposals(wt, doc, [prop(9, entry={"iv_id": "2099-01-01-001", "fields": {"a": 1}})])
    assert added == [] and len(log(wt)) == 1
    assert "2099" not in (wt / "data/corrections/patches.yml").read_text()


def test_sync_rejects_comment_and_hand_deletion(wt, tmp_path, monkeypatch):
    doc = {"branch": "qa/test", "proposals": []}
    propose.add_proposals(wt, doc, [prop(1), prop(2), prop(3)])
    # Miguel deletes proposal 3 by hand in the PR
    p3 = next(p for p in doc["proposals"] if p["fp"] == "C1-0000000003")
    P.remove_block(wt / "data/corrections", "patches.yml", p3["yaml_text"])
    subprocess.run([*GIT, "-C", str(wt), "commit", "-qam", "manual edit", "--no-verify"], check=True)
    comments = [{"body": "Looks good except:\nreject C1-0000000001 no es un error\nreject C1-ffffffffff typo",
                 "user": {"login": "miguelsanchez"}, "created_at": "2026-10-17T10:00:00Z"}]
    recorded = tmp_path / "comments.json"
    recorded.write_text(json.dumps(comments))
    monkeypatch.chdir(wt)
    assert sync.main(["--here", "--comments-json", str(recorded), "--no-push"]) == 0

    doc = P.load(wt)
    status = {p["fp"]: (p["status"], p["reject_reason"]) for p in doc["proposals"]}
    assert status["C1-0000000001"] == ("rejected", "no es un error (@miguelsanchez)")
    assert status["C1-0000000002"][0] == "proposed"
    assert status["C1-0000000003"] == ("rejected", "removed from the diff by hand")
    patches = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert [e["iv_id"] for e in patches] == ["2026-01-01-002"]
    sup = yaml.safe_load((wt / "meta/qa/suppressions.yml").read_text())
    assert {s["fp"] for s in sup} == {"C1-0000000001", "C1-0000000003"}
    assert all(s["mode"] == "until_changed" for s in sup)
    assert log(wt)[0].startswith("qa: reject C1-0000000001")
    # idempotent
    assert sync.main(["--here", "--comments-json", str(recorded), "--no-push"]) == 0
    assert log(wt)[0].startswith("qa: reject")
    assert len([l for l in log(wt) if l.startswith("qa: reject")]) == 1


def test_rejected_finding_stays_suppressed(wt):
    """run_checks honours what sync wrote (until_changed with the same subject hash)."""
    from qa.run_checks import is_suppressed
    from qa.model import Finding
    import datetime
    f = Finding(check="C1", severity="P2", subject="s", message="m", subject_hash="abc")
    sup = [{"fp": f.fp, "mode": "until_changed", "subject_hash": "abc"}]
    assert is_suppressed(f, sup, datetime.date.today())
    f2 = Finding(check="C1", severity="P2", subject="s", message="m", subject_hash="changed")
    assert not is_suppressed(f2, sup, datetime.date.today())
    # checks that compute no hash: suppressed for as long as the finding exists
    f3 = Finding(check="C1", severity="P2", subject="s", message="m")
    assert is_suppressed(f3, [{"fp": f3.fp, "mode": "until_changed", "subject_hash": ""}], datetime.date.today())


def test_merge_body_keeps_the_rest_of_the_pr_description():
    ingest = "## Pleno 2026-09-29\n12 interventions extracted."
    once = P.merge_body(ingest, "QA v1")
    assert once.startswith(ingest) and P.QA_START in once and "QA v1" in once
    twice = P.merge_body(once, "QA v2")
    assert twice.count(P.QA_START) == 1 and "QA v1" not in twice and "QA v2" in twice
    assert twice.startswith(ingest)
    assert P.merge_body("", "QA").startswith(P.QA_START)


def test_rebase_carries_only_sources(tmp_path, monkeypatch):
    """apply_steps.rebase: main moved on (a code commit and a new correction); the PR branch is
    rebuilt on it with its proposal re-appended, and derived files come from main untouched."""
    from qa import apply_steps

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    (seed / "data/corrections").mkdir(parents=True)
    (seed / "meta/qa").mkdir(parents=True)
    (seed / "data/corrections/patches.yml").write_text("[]\n")
    (seed / "meta/qa/suppressions.yml").write_text("[]\n")
    (seed / "data/intervencions.json").write_text('["derived v1"]')
    (seed / "data/raw").mkdir()
    (seed / "data/raw/interventions_raw.json").write_text("[]")
    g = [*GIT, "-C", str(seed)]
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-qm", "seed"], check=True)
    subprocess.run([*g, "remote", "add", "origin", str(origin)], check=True)
    subprocess.run([*g, "push", "-q", "origin", "main"], check=True)

    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True)
    w = [*GIT, "-C", str(wt)]
    subprocess.run([*w, "switch", "-q", "-c", "qa/2026-10"], check=True)
    doc = {"branch": "qa/2026-10", "proposals": []}
    block = P.append_entry(wt / "data/corrections", "patches.yml", None,
                           {"iv_id": "2026-01-01-001", "fields": {"ambit": "ciutat"}})
    doc["proposals"].append({**prop(1), "yaml_text": block, "status": "proposed", "reject_reason": None,
                             "entry": {"iv_id": "2026-01-01-001", "fields": {"ambit": "ciutat"}}})
    P.save(wt, doc)
    (wt / "data/intervencions.json").write_text('["derived by the branch"]')  # stale derived file
    subprocess.run([*w, "add", "."], check=True)
    subprocess.run([*w, "commit", "-qm", "proposal + derived"], check=True)

    # main moves: code commit + another correction + new derived data
    subprocess.run([*g, "pull", "-q", "origin", "main"], check=True)
    P.append_entry(seed / "data/corrections", "patches.yml", None,
                   {"iv_id": "2026-01-01-099", "fields": {"ambit": "barri"}})
    (seed / "data/intervencions.json").write_text('["derived v2 on main"]')
    (seed / "README").write_text("code change")
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-qm", "main moves"], check=True)
    subprocess.run([*g, "push", "-q", "origin", "main"], check=True)
    subprocess.run([*w, "fetch", "-q", "origin"], check=True)

    monkeypatch.setenv("GIT_AUTHOR_NAME", "t"); monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t"); monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    monkeypatch.setattr(P, "run", lambda cmd, cwd=None, check=True, capture=True: subprocess.run(
        [*cmd[:1], "-c", "core.hooksPath=/dev/null", *cmd[1:]] if cmd[0] == "git" else cmd,
        cwd=cwd, check=check, capture_output=True, text=True).stdout.strip())
    assert apply_steps.rebase(wt) is True
    assert apply_steps._is_ancestor(wt)
    patches = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert [e["iv_id"] for e in patches] == ["2026-01-01-099", "2026-01-01-001"]  # main's, then ours
    assert (wt / "data/intervencions.json").read_text() == '["derived v2 on main"]'  # never merged by hand
    assert (wt / "README").exists()
    assert apply_steps.rebase(wt) is False  # idempotent


def test_rebase_carries_a_delete(tmp_path, monkeypatch):
    """A delete of an entry on main survives the rebuild of the branch on a newer main."""
    from qa import apply_steps

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    (seed / "data/corrections").mkdir(parents=True)
    (seed / "meta/qa").mkdir(parents=True)
    (seed / "meta/qa/suppressions.yml").write_text("[]\n")
    (seed / "data/corrections/patches.yml").write_text("[]\n")
    for iv in ("2026-01-01-001", "2026-01-01-002"):
        P.append_entry(seed / "data/corrections", "patches.yml", None, {"iv_id": iv, "fields": {"ambit": "barri"}})
    g = [*GIT, "-C", str(seed)]
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-qm", "seed"], check=True)
    subprocess.run([*g, "remote", "add", "origin", str(origin)], check=True)
    subprocess.run([*g, "push", "-q", "origin", "main"], check=True)

    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True)
    w = [*GIT, "-C", str(wt)]
    subprocess.run([*w, "switch", "-q", "-c", "qa/2026-10"], check=True)
    rec = {**prop(1), "op": "delete", "entry": {"iv_id": "2026-01-01-001"}, "status": "proposed",
           "reject_reason": None}
    rec["yaml_text"], rec["old_text"] = P.apply_op(wt / "data/corrections", rec)
    P.save(wt, {"branch": "qa/2026-10", "proposals": [rec]})
    subprocess.run([*w, "add", "."], check=True)
    subprocess.run([*w, "commit", "-qm", "delete"], check=True)

    (seed / "README").write_text("code change")
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-qm", "main moves"], check=True)
    subprocess.run([*g, "push", "-q", "origin", "main"], check=True)
    subprocess.run([*w, "fetch", "-q", "origin"], check=True)

    monkeypatch.setenv("GIT_AUTHOR_NAME", "t"); monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t"); monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    assert apply_steps.rebase(wt) is True
    patches = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert [e["iv_id"] for e in patches] == ["2026-01-01-002"]
    assert P.load(wt)["proposals"][0]["old_text"].startswith("- iv_id: 2026-01-01-001")


def _hand_pr(tmp_path, monkeypatch, main_edit):
    """A data PR made by hand (#103): an entry added to reassignments.yml, no proposals. main then
    moves with a code commit and main_edit(seed). Returns (worktree, branch head before the rebase)."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    (seed / "data/corrections").mkdir(parents=True)
    (seed / "meta/qa").mkdir(parents=True)
    (seed / "meta/qa/suppressions.yml").write_text("[]\n")
    (seed / "data/corrections/reassignments.yml").write_text("- iv_id: 2026-01-01-001\n  entitat: A\n")
    (seed / "data/corrections/patches.yml").write_text("[]\n")
    P.save(seed, {"branch": "qa/2026-10-5", "proposals": [{**prop(1), "status": "proposed"}]})  # #100's, applied
    g = [*GIT, "-C", str(seed)]
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-qm", "seed"], check=True)
    subprocess.run([*g, "remote", "add", "origin", str(origin)], check=True)
    subprocess.run([*g, "push", "-q", "origin", "main"], check=True)

    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True)
    w = [*GIT, "-C", str(wt)]
    subprocess.run([*w, "switch", "-q", "-c", "qa/2026-10-20-cessions"], check=True)
    with open(wt / "data/corrections/reassignments.yml", "a") as f:
        f.write("- iv_id: 2014-01-31-101\n  entitat: AV Natzaret\n")
    subprocess.run([*w, "commit", "-qam", "hand-made cession"], check=True)
    head = subprocess.run([*w, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

    (seed / "README").write_text("code change")
    main_edit(seed)
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-qm", "main moves"], check=True)
    subprocess.run([*g, "push", "-q", "origin", "main"], check=True)
    subprocess.run([*w, "fetch", "-q", "origin"], check=True)
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "t")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "t@t")
    return wt, head


def test_rebase_carries_a_hand_made_prs_corrections(tmp_path, monkeypatch):
    """#103 had no proposals: a rebase replayed none and would have dropped its two cessions."""
    from qa import apply_steps

    def main_edit(seed):  # another data PR merged: a patch, in a file the branch does not touch
        P.append_entry(seed / "data/corrections", "patches.yml", None, {"iv_id": "2026-01-01-099", "fields": {"ambit": "barri"}})

    wt, _ = _hand_pr(tmp_path, monkeypatch, main_edit)
    assert apply_steps.rebase(wt) is True
    assert apply_steps._is_ancestor(wt)
    cessions = yaml.safe_load((wt / "data/corrections/reassignments.yml").read_text())
    assert [e["iv_id"] for e in cessions] == ["2026-01-01-001", "2014-01-31-101"]
    assert [e["iv_id"] for e in yaml.safe_load((wt / "data/corrections/patches.yml").read_text())] == ["2026-01-01-099"]
    assert (wt / "README").exists()
    assert subprocess.run([*GIT, "-C", str(wt), "status", "--porcelain"], capture_output=True, text=True).stdout == ""


def test_rebase_stops_when_a_hand_made_edit_conflicts(tmp_path, monkeypatch):
    """main appended to the same file: the rebase stops and leaves the branch as it was."""
    from qa import apply_steps

    def main_edit(seed):
        with open(seed / "data/corrections/reassignments.yml", "a") as f:
            f.write("- iv_id: 2026-02-02-002\n  entitat: B\n")

    wt, head = _hand_pr(tmp_path, monkeypatch, main_edit)
    with pytest.raises(SystemExit, match="do not apply on origin/main"):
        apply_steps.rebase(wt)
    now = subprocess.run([*GIT, "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert now == head
    assert "2014-01-31-101" in (wt / "data/corrections/reassignments.yml").read_text()


def test_prune_baseline_only_shrinks(tmp_path, monkeypatch):
    from qa import apply_steps
    wt = tmp_path
    (wt / "meta/qa").mkdir(parents=True)
    (wt / "data").mkdir()
    (wt / "scripts/lib").mkdir(parents=True)
    (wt / "scripts/lib/taxonomy.json").write_text(json.dumps(
        {"categories": {"economia": ["comerc_ocupacio"], "mobilitat": ["transit"]}}))
    (wt / "data/intervencions.json").write_text(json.dumps([
        {"id": "a", "ambit": "ciutat", "zones": [], "temes_v2": {"economia": ["comerc_ocupacio"]}},
        {"id": "b", "ambit": "barri", "zones": [], "temes_v2": {"comerc_ocupacio": ["x"]}},
    ]))
    (wt / "meta/qa/baseline.json").write_text(json.dumps({
        "known_issues": {"ambit_barri_without_zones": {"ids": ["a", "b"]}, "invalid_temes_v2": {"ids": ["a", "b"]}},
        "findings": [{"fp": "C3-aaaaaaaaaa"}, {"fp": "C3-keepkeep01"}]}))
    P.save(wt, {"branch": "qa/x", "proposals": [{"fp": "C3-aaaaaaaaaa", "status": "proposed"},
                                                 {"fp": "C3-rejected01", "status": "rejected"}]})
    removed = apply_steps.prune_baseline(wt)
    base = json.loads((wt / "meta/qa/baseline.json").read_text())
    assert [f["fp"] for f in base["findings"]] == ["C3-keepkeep01"]
    assert base["known_issues"]["ambit_barri_without_zones"]["ids"] == ["b"]
    assert base["known_issues"]["invalid_temes_v2"]["ids"] == ["b"]
    assert "C3-aaaaaaaaaa" in removed


def test_bold_count_reads_an_empty_translation_as_the_original(tmp_path):
    """C1b: emptying text_cas because the speech is in castellano publishes text_original, bold included."""
    from qa import apply_steps
    (tmp_path / "data/raw").mkdir(parents=True)
    raw = tmp_path / "data/raw/interventions_raw.json"
    raw.write_text(json.dumps([{"text_original": "**a**", "text_cas": "**a**", "text_val": "**b**"}]))
    assert apply_steps.bold_count(tmp_path) == 3
    raw.write_text(json.dumps([{"text_original": "**a**", "text_cas": "", "text_val": "b"}]))
    assert apply_steps.bold_count(tmp_path) == 2


def test_replace_then_reject_restores_the_previous_entry(wt, tmp_path, monkeypatch):
    doc = {"branch": "qa/test", "proposals": []}
    propose.add_proposals(wt, doc, [prop(1)])                       # patch v1: ambit
    v2 = {"iv_id": "2026-01-01-001", "fields": {"ambit": "ciutat", "zones": [], "districtes": []},
          "reason": "v2: also clear zones", "date": "2026-10-18"}
    repl = {**prop(2), "fp": "C3-0000000abc", "subject": "2026-01-01-001", "op": "replace", "entry": v2}
    added, _ = propose.add_proposals(wt, doc, [repl])
    assert [p["op"] for p in added] == ["replace"]
    entries = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert len(entries) == 1 and entries[0]["fields"]["zones"] == []      # swapped in place, no duplicate
    assert "replaces the existing entry" in P.render_body(doc)

    recorded = tmp_path / "c.json"
    recorded.write_text(json.dumps([{"body": "reject C3-0000000abc no", "user": {"login": "m"}}]))
    monkeypatch.chdir(wt)
    assert sync.main(["--here", "--comments-json", str(recorded), "--no-push"]) == 0
    entries = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert entries[0]["fields"] == {"ambit": "ciutat"} and "zones" not in entries[0]["fields"]


def test_replacing_a_patch_keeps_the_fields_it_does_not_touch(wt):
    """2022-10-21-008: a temes_v2 patch replaced the language fix of the same intervention."""
    doc = {"branch": "qa/test", "proposals": []}
    propose.add_proposals(wt, doc, [prop(1)])                       # patch v1: ambit
    v2 = {"iv_id": "2026-01-01-001", "fields": {"temes_v2": {"urbanisme": ["habitatge"]}},
          "reason": "v2: add habitatge", "date": "2026-10-19"}
    repl = {**prop(2), "fp": "C6-0000000abd", "subject": "2026-01-01-001", "op": "replace", "entry": v2}
    propose.add_proposals(wt, doc, [repl])
    [entry] = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert entry["fields"] == {"ambit": "ciutat", "temes_v2": {"urbanisme": ["habitatge"]}}
    assert entry["reason"] == "v2: add habitatge"
    # the first proposal is folded into the second, not "removed from the diff by hand"
    first = next(p for p in doc["proposals"] if p["fp"] != "C6-0000000abd")
    assert P.applied(wt / "data/corrections", first, doc)
    assert not P.applied(wt / "data/corrections", first)


def test_two_patches_for_one_intervention_in_one_batch_are_merged(wt):
    """F5 sample: the auditor's temes_v2 and ambit patches for 2018-04-26-004, both appends."""
    doc = {"branch": "qa/test", "proposals": []}
    second = {**prop(2), "fp": "C6-0000000abe", "subject": "2026-01-01-001",
              "entry": {"iv_id": "2026-01-01-001", "fields": {"temes_v2": {"urbanisme": ["habitatge"]}}}}
    added, _ = propose.add_proposals(wt, doc, [prop(1), second])
    assert [a["op"] for a in added] == ["append", "replace"]
    [entry] = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert entry["fields"] == {"ambit": "ciutat", "temes_v2": {"urbanisme": ["habitatge"]}}
    assert P.applied(wt / "data/corrections", added[0], doc)


def test_an_entity_nobody_uses_is_skipped_not_fatal(wt):
    """The pre-commit hook blocks N7's P3 "has no effect": propose skips it instead of stopping."""
    doc = {"branch": "qa/test", "proposals": []}
    orphan = prop(1, sev="P1", file="new_entities.yml",
                  entry={"id": "afa-sola", "nom_cas": "AFA Sola", "nom_val": "AFA Sola", "tipus": "educacio"})
    added, _ = propose.add_proposals(wt, doc, [orphan, prop(2)])
    assert [a["fp"] for a in added] == ["C1-0000000002"]
    assert not (wt / "data/corrections/new_entities.yml").exists() or \
        "afa-sola" not in (wt / "data/corrections/new_entities.yml").read_text()


def test_delete_then_reject_restores_the_entry(wt, tmp_path, monkeypatch):
    doc = {"branch": "qa/test", "proposals": []}
    propose.add_proposals(wt, doc, [prop(1), prop(2)])
    dele = {**prop(3), "fp": "N7-00000000de", "subject": "2026-01-01-001", "op": "delete",
            "entry": {"iv_id": "2026-01-01-001"}}
    added, _ = propose.add_proposals(wt, doc, [dele])
    assert [(p["op"], p["yaml_text"]) for p in added] == [("delete", "")]
    entries = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert [e["iv_id"] for e in entries] == ["2026-01-01-002"]
    assert "deleted from" in P.render_body(doc) and "2026-01-01-001" in P.render_body(doc)
    assert P.applied(wt / "data/corrections", added[0])

    monkeypatch.chdir(wt)
    recorded = tmp_path / "c.json"
    recorded.write_text("[]")
    assert sync.main(["--here", "--comments-json", str(recorded), "--no-push"]) == 0
    assert doc_status(wt, "N7-00000000de") == "proposed"            # still deleted: not a reject

    recorded.write_text(json.dumps([{"body": "reject N7-00000000de keep it", "user": {"login": "m"}}]))
    assert sync.main(["--here", "--comments-json", str(recorded), "--no-push"]) == 0
    entries = yaml.safe_load((wt / "data/corrections/patches.yml").read_text())
    assert sorted(e["iv_id"] for e in entries) == ["2026-01-01-001", "2026-01-01-002"]
    assert doc_status(wt, "N7-00000000de") == "rejected"


def test_delete_put_back_by_hand_is_a_reject(wt, tmp_path, monkeypatch):
    doc = {"branch": "qa/test", "proposals": []}
    propose.add_proposals(wt, doc, [prop(1)])
    before = (wt / "data/corrections/patches.yml").read_text()
    dele = {**prop(3), "fp": "N7-00000000df", "subject": "2026-01-01-001", "op": "delete",
            "entry": {"iv_id": "2026-01-01-001"}}
    propose.add_proposals(wt, doc, [dele])
    (wt / "data/corrections/patches.yml").write_text(before)       # the entry restored in the diff
    monkeypatch.chdir(wt)
    recorded = tmp_path / "c.json"
    recorded.write_text("[]")
    assert sync.main(["--here", "--comments-json", str(recorded), "--no-push"]) == 0
    assert doc_status(wt, "N7-00000000df") == "rejected"


def test_delete_needs_exactly_one_entry(wt):
    with pytest.raises(P.ProposalError, match="0 entries"):
        P.delete_entry(wt / "data/corrections", "patches.yml", None, {"iv_id": "2026-01-01-001"})


def doc_status(root, fp):
    return next(p["status"] for p in P.load(root)["proposals"] if p["fp"] == fp)


def test_replace_refuses_hand_formatted_entries(wt):
    (wt / "data/corrections/patches.yml").write_text(
        "- iv_id: '2026-01-01-001'   # hand comment\n  fields: {ambit: barri}\n")
    with pytest.raises(P.ProposalError, match="by hand"):
        P.replace_entry(wt / "data/corrections", "patches.yml", None,
                        {"iv_id": "2026-01-01-001", "fields": {"ambit": "ciutat"}})


def test_free_branch_name_never_reuses_a_merged_branch(monkeypatch):
    heads = "abc\trefs/heads/qa/2026-10\ndef\trefs/heads/qa/2026-10-2\n"
    monkeypatch.setattr(P, "run", lambda cmd, cwd=None, check=True, capture=True: heads)
    assert propose.free_branch_name(Path("."), "qa/2026-10") == "qa/2026-10-3"
    monkeypatch.setattr(P, "run", lambda cmd, cwd=None, check=True, capture=True: "")
    assert propose.free_branch_name(Path("."), "qa/2026-11") == "qa/2026-11"


def test_cap_can_be_raised_for_a_one_off_batch(wt):
    doc = {"branch": "qa/test", "proposals": []}
    added, overflow = propose.add_proposals(wt, doc, [prop(i) for i in range(1, 4)], cap=3)
    assert len(added) == 3 and overflow == []


def test_a_big_batch_still_fits_in_a_pr_body():
    """GitHub rejects a body over 65 536 chars: the language-rule PR had 150 long patches."""
    long = {"fp": "", "check": "C4", "severity": "P1", "subject": "x", "title": "t", "message": "m",
            "evidence": {"file": "f", "quote": None}, "file": "patches.yml", "section": None,
            "status": "proposed", "yaml_text": "- iv_id: x\n  fields:\n    text_val: " + "paraula " * 600 + "\n"}
    def body(n):
        return P.render_body({"branch": "qa/test",
                              "proposals": [{**long, "fp": f"C4-{i:010d}"} for i in range(n)]})
    assert "paraula " * 600 in body(3)                       # fits whole
    shortened = body(15)
    assert "chars in all: see the diff" in shortened and len(shortened) <= P.BODY_BUDGET
    big = body(150)
    assert "do not fit in the PR body" in big and len(big) <= P.BODY_BUDGET


def test_a_branch_cut_from_main_does_not_inherit_the_merged_prs_proposals(tmp_path):
    """main keeps the proposals file of the last merged data PR: a hand-made data PR cut from main
    (#103) showed #100's 92 applied proposals in its plan and PR body, and a rebase would re-add them."""
    subprocess.run(["git", "init", "-q", "-b", "qa/2026-10-5", str(tmp_path)], check=True)
    P.save(tmp_path, {"branch": "qa/2026-10-5", "proposals": [{"fp": "C3-aaaaaaaaaa", "status": "proposed"}]})
    assert len(P.active(P.load(tmp_path))) == 1
    subprocess.run([*GIT, "-C", str(tmp_path), "switch", "-q", "-c", "qa/2026-10-20-cessions"], check=True)
    assert P.load(tmp_path) == {"branch": "qa/2026-10-20-cessions", "proposals": []}

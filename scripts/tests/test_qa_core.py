"""Core of the QA sentinel: fingerprints, delta, baseline, suppressions, PAUSE, lock, --data-dir."""

import json

import pytest

from qa import run_checks as rc
from qa.model import REGISTRY, Context, Finding, check

FIXTURE_IDS = ("2026-01-01-001", "2026-01-01-002")


@pytest.fixture(scope="module", autouse=True)
def fake_check():
    """A check that reports one finding per intervention in the data dir it is given."""
    @check("ZZ1", family="test", title="one finding per intervention")
    def _zz1(ctx: Context):
        for iv in ctx.intervencions:
            yield Finding(check="ZZ1", severity="P2", subject=iv["id"], message="test",
                          subject_hash=iv.get("h", ""))
    yield
    REGISTRY.pop("ZZ1", None)


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "intervencions.json").write_text(json.dumps([{"id": i, "h": "a"} for i in FIXTURE_IDS]))
    return d


@pytest.fixture
def state(tmp_path, monkeypatch):
    s = tmp_path / "state"
    monkeypatch.setenv("LCP_QA_STATE", str(s))
    monkeypatch.setattr(rc, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(rc, "SUPPRESSIONS_PATH", tmp_path / "suppressions.yml")
    return s


def run(data_dir, *extra):
    return rc.main(["--only", "ZZ1", "--data-dir", str(data_dir), *extra])


def last(state):
    return json.loads((state / "last_run.json").read_text())


def test_fingerprint_is_stable():
    a = Finding(check="E1", severity="P1", subject="2026-09-29", message="x", key="3/4")
    b = Finding(check="E1", severity="P1", subject="2026-09-29", message="different text", key="3/4")
    assert a.fp == b.fp and a.fp.startswith("E1-")
    assert a.fp != Finding(check="E1", severity="P1", subject="2026-09-29", message="x", key="2/4").fp


def test_same_fingerprints_on_two_runs_and_empty_delta(data_dir, state):
    assert run(data_dir) == 0
    first = last(state)
    assert sum(f["new"] for f in first["findings"]) == 2
    assert run(data_dir) == 0
    second = last(state)
    assert {f["fp"] for f in first["findings"]} == {f["fp"] for f in second["findings"]}
    assert sum(f["new"] for f in second["findings"]) == 0


def test_resolved_then_reopened(data_dir, state):
    run(data_dir)
    (data_dir / "intervencions.json").write_text(json.dumps([{"id": FIXTURE_IDS[0]}]))
    run(data_dir)
    statuses = [json.loads(l)["status"] for l in (state / "findings.jsonl").read_text().splitlines()]
    assert statuses.count("resolved") == 1
    (data_dir / "intervencions.json").write_text(json.dumps([{"id": i} for i in FIXTURE_IDS]))
    run(data_dir)
    assert sum(f["new"] for f in last(state)["findings"]) == 1


def test_baseline_is_not_new(data_dir, state, tmp_path):
    fp = Finding(check="ZZ1", severity="P2", subject=FIXTURE_IDS[0], message="").fp
    (tmp_path / "baseline.json").write_text(json.dumps({"findings": [{"fp": fp, "reason": "known"}]}))
    run(data_dir)
    by_fp = {f["fp"]: f for f in last(state)["findings"]}
    assert by_fp[fp]["status"] == "baseline" and not by_fp[fp]["new"]


def test_baseline_add_appends_once_and_then_they_are_baseline(data_dir, state, tmp_path):
    (tmp_path / "baseline.json").write_text(json.dumps({"_doc": "keep me", "findings": []}))
    assert run(data_dir, "--baseline-add", "--reason", "accepted in a test") == 0
    doc = json.loads((tmp_path / "baseline.json").read_text())
    assert doc["_doc"] == "keep me"
    assert [b["reason"] for b in doc["findings"]] == ["accepted in a test"] * 2
    assert run(data_dir, "--baseline-add", "--reason", "again") == 0
    assert len(json.loads((tmp_path / "baseline.json").read_text())["findings"]) == 2
    assert run(data_dir, "--strict") == 0
    assert {f["status"] for f in last(state)["findings"]} == {"baseline"}


def test_baseline_add_needs_only_and_reason(data_dir, state):
    with pytest.raises(SystemExit):
        rc.main(["--data-dir", str(data_dir), "--baseline-add", "--reason", "x"])
    with pytest.raises(SystemExit):
        run(data_dir, "--baseline-add")


@pytest.mark.parametrize("mode,hidden", [
    ("forever", True),
    ("until:2999-01-01", True),
    ("until:2000-01-01", False),
    ("until_changed", True),
])
def test_suppressions(data_dir, state, tmp_path, mode, hidden):
    fp = Finding(check="ZZ1", severity="P2", subject=FIXTURE_IDS[0], message="").fp
    (tmp_path / "suppressions.yml").write_text(
        f"- fp: {fp}\n  check: ZZ1\n  reason: test\n  mode: '{mode}'\n  subject_hash: a\n")
    run(data_dir)
    new = {f["fp"] for f in last(state)["findings"] if f["new"]}
    assert (fp not in new) == hidden


def test_until_changed_reappears_when_subject_changes(data_dir, state, tmp_path):
    fp = Finding(check="ZZ1", severity="P2", subject=FIXTURE_IDS[0], message="").fp
    (tmp_path / "suppressions.yml").write_text(
        f"- fp: {fp}\n  mode: until_changed\n  subject_hash: old\n")
    run(data_dir)
    assert fp in {f["fp"] for f in last(state)["findings"] if f["new"]}


def test_pause_does_nothing(data_dir, state):
    state.mkdir()
    (state / "PAUSE").touch()
    assert run(data_dir) == 0
    assert not (state / "runs.jsonl").exists()
    assert not (state / "last_run.json").exists()


def test_lock_held_exits_and_is_logged(data_dir, state):
    holder = rc.State(state)
    assert holder.acquire()
    try:
        assert run(data_dir) == rc.EXIT_LOCKED
    finally:
        holder.release()
    runs = [json.loads(l) for l in (state / "runs.jsonl").read_text().splitlines()]
    assert runs[-1]["exit"] == "locked"


def test_runs_jsonl_records_the_run(data_dir, state):
    run(data_dir, "--trigger", "test")
    rec = json.loads((state / "runs.jsonl").read_text().splitlines()[-1])
    assert rec["trigger"] == "test" and rec["findings_new"] == 2 and rec["exit"] == 0


def test_no_state_writes_nothing(data_dir, state):
    assert run(data_dir, "--no-state") == 0
    assert not state.exists()


def test_strict_exits_1_on_new(data_dir, state):
    assert run(data_dir, "--strict") == 1
    assert run(data_dir, "--strict") == 0


def test_crashing_check_is_reported(data_dir, state):
    @check("ZZ2", family="test", title="crashes")
    def _boom(ctx):
        raise RuntimeError("boom")
    try:
        assert rc.main(["--only", "ZZ2", "--data-dir", str(data_dir)]) == 3
        assert last(state)["findings"][0]["subject"] == "crash"
    finally:
        REGISTRY.pop("ZZ2")


def test_list_runs_without_state(capsys):
    assert rc.main(["--list"]) == 0

"""Case table for the data guard hook (.claude/hooks/guard_data.py).

Design: meta/docs/arquitectura-agentes.md §3.2. The hook must ask before any
script under scripts/** (or push-public.sh) runs, unless it is in
scripts/qa/guard_allowlist.txt, and must stay silent on read-only commands.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

HOOK = Path(os.environ.get("LCP_GUARD_HOOK", REPO_ROOT / ".claude" / "hooks" / "guard_data.py"))

S07 = "scripts/07_build_final_json.py"


def run_hook(payload: dict) -> dict | None:
    r = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None


def _load_hook():
    spec = importlib.util.spec_from_file_location("guard_data", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load_hook()


def bash(command: str, cwd: Path = REPO_ROOT) -> str | None:
    """In-process for speed; test_hook_process_* cover the stdin/stdout contract."""
    out = guard.decide({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})
    return out and out[0]


def test_hook_process_asks_for_07():
    out = run_hook({"tool_name": "Bash", "cwd": str(REPO_ROOT),
                    "tool_input": {"command": "cd scripts && python 07_build_final_json.py"}})
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "ask"
    assert "07_build_final_json.py" in out["permissionDecisionReason"]


def test_hook_process_silent_for_grep():
    assert run_hook({"tool_name": "Bash", "cwd": str(REPO_ROOT),
                     "tool_input": {"command": f"grep -n x {S07}"}}) is None


ASK = [
    # pipeline and other scripts that write to data/
    "python scripts/scrape_video_archive.py",
    "python scripts/01_crawl_index.py",
    "python scripts/export_dataset.py",
    "python scripts/build_presupuesto_gastos.py",
    "python scripts/validate_interventions.py --json",
    f"python {S07}",
    "python3 scripts/apply_merges.py",
    "scripts/.venv/bin/python scripts/05_parse_interventions.py",
    '"$LCP_ROOT/scripts/.venv/bin/python" "$LCP_ROOT/scripts/07_build_final_json.py"',
    "python scripts/nuevo_script.py",  # does not exist yet: still guarded
    # publication
    "bash push-public.sh",
    "./push-public.sh",
    "sh ./push-public.sh",
    # ways around a plain prefix match
    "cd scripts && python3 07_build_final_json.py",
    "cd scripts; python 07_build_final_json.py",
    'sh -c "python scripts/07_build_final_json.py"',
    "bash -c 'cd scripts && python 07_build_final_json.py'",
    "zsh -c \"python3 scripts/apply_merges.py\"",
    "python -c \"exec(open('scripts/07_build_final_json.py').read())\"",
    "python -c \"import runpy; runpy.run_path('scripts/apply_merges.py')\"",
    "QA_APPROVED=1 python scripts/07_build_final_json.py",
    "env X=1 python scripts/apply_merges.py",
    "env -i PATH=/usr/bin python3 scripts/apply_merges.py",
    "env -S 'python3 scripts/apply_merges.py'",
    "exec python scripts/07_build_final_json.py",
    "nohup python scripts/07_build_final_json.py &",
    "time python scripts/07_build_final_json.py",
    "echo scripts/07_build_final_json.py | xargs python",
    "source scripts/07_build_final_json.py",
    ". scripts/qa/install_launchd.sh",
    "cd scripts && ./07_build_final_json.py",
    "scripts/07_build_final_json.py",
    ".venv/bin/python -m scripts.apply_merges",
    "scripts/.venv/bin/python -m apply_merges",
    "bash desconocido.sh",
    "python /tmp/whatever.py",
    "cat scripts/07_build_final_json.py | python",
    "echo 'python scripts/07_build_final_json.py' | bash",
    "python - <<'EOF'\nimport runpy\nrunpy.run_path('scripts/07_build_final_json.py')\nEOF",
    "bash <<EOF\ncd scripts && python 07_build_final_json.py\nEOF",
    'python -c "$(cat scripts/07_build_final_json.py)"',
    "perl -e 'system(\"python scripts/07_build_final_json.py\")'",
    "find scripts -name '07_*' -exec python {} \\;",
    "uv run python scripts/07_build_final_json.py",
    "timeout 60 python scripts/07_build_final_json.py",
    "bash scripts/qa/apply.sh",
    "scripts/.venv/bin/python scripts/qa/complete_manual.py --worktree ../lcp-qa --commit",
    # chained: the read-only half does not hide the executing half
    f"grep -n main {S07} && python {S07}",
    f"cat {S07} | head -5; cd scripts && python 07_build_final_json.py",
    # shell writes into data/
    "echo '[]' > data/intervencions.json",
    "cp /tmp/x.json data/entitats.json",
    "rm data/plenos/2026-07-23.json",
    "sed -i '' 's/a/b/' data/intervencions.json",
    "git checkout -- data/raw/interventions_raw.json",
    "git restore data/",
    "git reset --hard",
    "python -c \"import json; json.dump([], open('data/intervencions.json', 'w'))\"",
    # allowlisted only without spending API money (+--dry-run, !--translate)
    "scripts/.venv/bin/python scripts/qa/run_agents.py --pleno 2026-04-30",
    "scripts/.venv/bin/python scripts/qa/retranslate.py --translate",
    # inline analysis that writes or runs, or names a module whose functions write
    "python - <<'EOF'\nimport sys; sys.path.insert(0, 'scripts')\nfrom qa.run_agents import main\nmain(['--pleno', 'x'])\nEOF",
    "python - <<'EOF'\nfrom qa import proposals as P\nP.append_entry(p, 'patches.yml', None, {})\nEOF",
    "python - <<'EOF'\nimport apply_merges\napply_merges.write_outputs(d, apply_merges.apply_corrections(i))\nEOF",
    "python - <<'EOF'\nfrom qa.run_agents import to_proposals\nPath('out.json').write_text('[]')\nEOF",
    "python -c \"from qa.verify_proposals import main; main(['--input', 'x'])\"",
]

SILENT = [
    # reads that name the scripts
    f"cat {S07}",
    f"less {S07}",
    f"head -50 {S07}",
    f"tail -n 20 {S07}",
    f"grep -n main {S07}",
    "rg build_intervention scripts/",
    f"sed -n '1,40p' {S07}",
    f"wc -l {S07}",
    "ls scripts/",
    "cat push-public.sh",
    f"git log -- {S07}",
    f"git diff main -- {S07}",
    f"git show HEAD:{S07}",
    f"git blame -- {S07}",
    "git status --porcelain data/",
    # allowlisted scripts
    "python scripts/validate_interventions.py",
    "scripts/.venv/bin/python scripts/validate_interventions.py --strict",
    "python scripts/detect_missed_interventions.py",
    "python scripts/check_new_sessions.py",
    "python -m pytest scripts/tests",
    "scripts/.venv/bin/python -m pytest scripts/tests -q",
    '"$LCP_ROOT/scripts/.venv/bin/python" -m pytest "$LCP_ROOT/scripts/tests" -q',
    'PY="$(git rev-parse --show-toplevel)/scripts/.venv/bin/python"; "$PY" -m pytest scripts/tests',
    "python scripts/qa/run_checks.py --list",
    '"$LCP_ROOT/scripts/.venv/bin/python" "$LCP_ROOT/scripts/qa/run_checks.py"',
    "bash scripts/qa/doctor.sh",
    "cd scripts && python validate_interventions.py",
    # unrelated work
    "cd web && npm run build",
    "git commit -m 'x'",
    "git checkout main",
    "python3 -m venv scripts/.venv",
    "source scripts/.venv/bin/activate",
    "python -c 'print(1)'",
    "echo hello > /tmp/out.txt",
    "cat data/intervencions.json | jq length",
    "cp data/intervencions.json /tmp/backup.json",
    "python scripts/validate_interventions.py 2>&1 | tail -5",
    # rehearsals (+--dry-run in the allowlist)
    "scripts/.venv/bin/python scripts/qa/run_agents.py --pleno 2026-04-30 --dry-run",
    "scripts/.venv/bin/python scripts/qa/propose.py --input x.json --dry-run",
    # no API: opening the data PR is allowed (2026-10-18), and so are retranslate's free modes
    "scripts/.venv/bin/python scripts/qa/propose.py --input x.json --push",
    "scripts/.venv/bin/python scripts/qa/retranslate.py --dry-run",
    "scripts/.venv/bin/python scripts/qa/retranslate.py --proposals /tmp/p.json",
    # read-only analysis that imports pure functions (allowed 2026-10-17)
    "python - <<'EOF'\nimport sys; sys.path.insert(0, 'scripts')\nfrom qa.run_agents import to_proposals\n"
    "print(len(to_proposals('a', 'p', {})[0]))\nEOF",
    "python - <<'EOF'\nfrom qa import verify_proposals as V\nprint(V.quote_in('a b', V.forms('a b', source=True)))\nEOF",
    "python -c \"import apply_merges; r = apply_merges.apply_corrections(apply_merges.load_inputs('data')); "
    "print(len(r['interventions']))\"",
]


@pytest.mark.parametrize("command", ASK)
def test_asks(command):
    assert bash(command) == "ask", command


@pytest.mark.parametrize("command", SILENT)
def test_silent(command):
    assert bash(command) is None, command


def test_never_allows_or_denies_bash():
    """The guard only asks: it must never auto-approve or hard-block a Bash call."""
    decisions = {bash(c) for c in ASK + SILENT}
    assert decisions <= {"ask", None}


def test_relative_target_resolved_from_cwd():
    assert bash("python 07_build_final_json.py", cwd=REPO_ROOT / "scripts") == "ask"
    assert bash("python validate_interventions.py", cwd=REPO_ROOT / "scripts") is None


def test_garbage_input_asks():
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True)
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


# ── Write / Edit ──────────────────────────────────────────────────────────────

def edit(tool: str, file_path: Path, cwd: Path = REPO_ROOT) -> str | None:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    out = guard.decide({"tool_name": tool, "tool_input": {key: str(file_path)}, "cwd": str(cwd)})
    return out and out[0]


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
@pytest.mark.parametrize("rel", [
    "data/intervencions.json",
    "data/raw/interventions_raw.json",
    "data/plenos/new.json",
    "data/corrections/patches.yml",  # main checkout: corrections are not exempt
])
def test_edit_data_denied_in_main_checkout(tool, rel):
    if rel.startswith("data/corrections/") and guard.corrections_exempt(str(REPO_ROOT / rel)):
        pytest.skip("running inside the QA worktree on a qa/* branch, where corrections are editable "
                    "(the exemption itself is tested with throwaway worktrees below)")
    assert edit(tool, REPO_ROOT / rel) == "deny"


@pytest.mark.parametrize("rel", [
    "scripts/qa/guard_allowlist.txt", ".claude/settings.json", ".claude/hooks/guard_data.py",
])
def test_edit_guard_itself_asks(rel):
    assert edit("Edit", REPO_ROOT / rel) == "ask"


@pytest.mark.parametrize("rel", ["scripts/qa/run_checks.py", "meta/qa/baseline.json", "web/src/x.ts"])
def test_edit_outside_data_silent(rel):
    assert edit("Write", REPO_ROOT / rel) is None


def test_edit_relative_path_uses_cwd():
    assert edit("Edit", Path("intervencions.json"), cwd=REPO_ROOT / "data") == "deny"


@pytest.fixture
def qa_worktree(tmp_path):
    """A throwaway repo with a linked worktree, standing in for ../lcp-qa."""
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    for d in ("data/corrections", ".claude/hooks", "scripts/qa"):
        (main / d).mkdir(parents=True)
    (main / "data/corrections/patches.yml").write_text("[]\n")
    (main / "data/intervencions.json").write_text("[]\n")
    (main / ".claude/hooks/guard_data.py").write_text(HOOK.read_text())
    (main / "scripts/qa/guard_allowlist.txt").write_text("pytest\n")
    git = ["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    wt = tmp_path / "lcp-qa"
    subprocess.run([*git, "worktree", "add", "-q", "-b", "qa/2026-10", str(wt)], check=True)
    return main, wt


def edit_with(hook: Path, file_path: Path) -> str | None:
    r = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(file_path)},
                          "cwd": str(file_path.parent)}),
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else None


def test_corrections_editable_in_qa_worktree(qa_worktree):
    _, wt = qa_worktree
    assert edit_with(wt / ".claude/hooks/guard_data.py", wt / "data/corrections/patches.yml") is None


def test_other_data_denied_in_qa_worktree(qa_worktree):
    _, wt = qa_worktree
    assert edit_with(wt / ".claude/hooks/guard_data.py", wt / "data/intervencions.json") == "deny"


def test_corrections_denied_in_qa_worktree_off_qa_branch(qa_worktree):
    _, wt = qa_worktree
    subprocess.run(["git", "-C", str(wt), "switch", "-q", "-c", "feature/x"], check=True)
    assert edit_with(wt / ".claude/hooks/guard_data.py", wt / "data/corrections/patches.yml") == "deny"


def test_corrections_denied_in_main_checkout_on_qa_branch(qa_worktree):
    """A qa/* branch in the main checkout is not the QA worktree."""
    main, wt = qa_worktree
    subprocess.run(["git", "-C", str(wt), "switch", "-q", "--detach"], check=True)
    subprocess.run(["git", "-C", str(main), "switch", "-q", "qa/2026-10"], check=True)
    assert edit_with(main / ".claude/hooks/guard_data.py", main / "data/corrections/patches.yml") == "deny"


def test_env_cannot_unlock_data(qa_worktree):
    main, _ = qa_worktree
    env = {**os.environ, "QA_APPROVED": "1", "LCP_QA_WORKTREE": "1", "GIT_BRANCH": "qa/x"}
    r = subprocess.run(
        [sys.executable, str(main / ".claude/hooks/guard_data.py")],
        input=json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": str(main / "data/corrections/patches.yml")}}),
        capture_output=True, text=True, env=env,
    )
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ── Wiring ────────────────────────────────────────────────────────────────────

def test_settings_wire_the_hook():
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    pre = settings["hooks"]["PreToolUse"]
    matchers = {m["matcher"] for m in pre if "guard_data.py" in json.dumps(m)}
    assert any({"Bash", "Write", "Edit"} <= set(m.split("|")) for m in matchers)
    assert any("push-public.sh" in r for r in settings["permissions"]["ask"])
    assert any("07_build_final_json" in r for r in settings["permissions"]["ask"])


def test_settings_never_bypass_permissions():
    text = (REPO_ROOT / ".claude" / "settings.json").read_text()
    for bad in ("bypassPermissions", "dangerously", "acceptEdits"):
        assert bad not in text

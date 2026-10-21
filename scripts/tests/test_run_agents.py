"""run_agents.py (arquitectura-agentes F2.7) and E7, without any API call.

A fake `claude` (LCP_CLAUDE_BIN) stands in for the real one: it records its arguments and answers
with a fixed JSON document shaped like `claude -p --output-format json`.
"""
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from qa import run_agents as RA  # noqa: E402
from qa import run_checks as rc  # noqa: E402
from qa.model import REGISTRY, Context  # noqa: E402

DATA = ROOT / "data"
needs_data = pytest.mark.skipif(not (DATA / "raw/texts/2021-04-29.txt").exists(), reason="data/ not present")

GOOD = {"check": "C6", "severity": "P2", "subject": "2021-04-29-005", "title": "test", "message": "",
        "quote": "quan la zitzània -la cizaña, en castellano- infecta un espai s’acaba havent de votar",
        "evidence_pleno": "2021-04-29", "file": "patches.yml", "section": None, "op": "append",
        "entry_json": json.dumps({"iv_id": "2021-04-29-005", "fields": {"idioma_original": "valenciano"},
                                  "reason": "test"})}
INVENTED = {**GOOD, "quote": "una frase que no apareix enlloc de l'acta del ple",
            "entry_json": json.dumps({"iv_id": "2021-04-29-004", "fields": {"idioma_original": "mixt"}})}
BROKEN = {**GOOD, "entry_json": "{not json"}


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    calls = tmp_path / "calls.jsonl"
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({
        "type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "total_cost_usd": 0.0123,
        "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 300,
                  "output_tokens": 500},
        "structured_output": {"proposals": [GOOD, INVENTED, BROKEN], "notes": "checked"},
    }))
    script = tmp_path / "claude"
    script.write_text(f"""#!{sys.executable}
import json, os, sys
stdin = sys.stdin.read()
with open({str(calls)!r}, "a") as fh:
    fh.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "files": sorted(os.listdir()),
                          "key": os.environ.get("ANTHROPIC_API_KEY"), "prompt_len": len(stdin)}}) + "\\n")
print(open({str(answer)!r}).read())
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LCP_CLAUDE_BIN", str(script))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LCP_QA_STATE", str(tmp_path / "state"))

    def read_calls():
        return [json.loads(l) for l in calls.read_text().splitlines()] if calls.exists() else []
    return read_calls


def runs(tmp_path):
    p = tmp_path / "state" / "runs.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


# ── agent definitions and the contract ──

@pytest.mark.parametrize("name,model", [("extraction-reviewer", "sonnet"), ("entity-curator", "sonnet"),
                                        ("classification-auditor", "haiku")])
def test_agents_are_read_only_with_the_designed_model(name, model):
    meta, body = RA.parse_agent(RA.AGENTS_DIR / f"{name}.md")
    assert meta["name"] == name and meta["model"] == model
    assert {t.strip() for t in meta["tools"].split(",")} == {"Read", "Grep", "Glob"}
    assert "quote" in body and "entry_json" in body


def test_schema_is_valid_json_and_requires_a_quote():
    schema = json.loads(RA.SCHEMA_PATH.read_text())
    item = schema["properties"]["proposals"]["items"]
    assert {"quote", "evidence_pleno", "entry_json"} <= set(item["required"])


def test_command_is_bare_read_only_and_capped(tmp_path):
    meta, _ = RA.parse_agent(RA.AGENTS_DIR / "extraction-reviewer.md")
    cmd = RA.claude_command(meta, tmp_path / "p.md", 1.5)
    assert "--bare" in cmd and "--allowedTools=Read,Grep,Glob" in cmd
    assert any(a.startswith("--disallowedTools=") and "Bash" in a and "Write" in a for a in cmd)
    assert cmd[cmd.index("--max-turns") + 1] == "25" and cmd[cmd.index("--max-budget-usd") + 1] == "1.50"


# ── when nothing runs ──

def test_empty_delta_runs_nothing(tmp_path, fake_claude, capsys):
    d = tmp_path / "data"
    (d / "raw").mkdir(parents=True)
    ivs = [{"id": "2026-01-01-001", "pleno_id": "2026-01-01"}]
    (d / "raw/interventions_raw.json").write_text(json.dumps(ivs))
    (d / "intervencions.json").write_text(json.dumps(ivs))
    assert RA.main(["--data-dir", str(d)]) == 0
    assert "0 tokens" in capsys.readouterr().out
    assert fake_claude() == [] and runs(tmp_path) == []


def test_pause_runs_nothing(tmp_path, fake_claude):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "PAUSE").write_text("")
    assert RA.main(["--pleno", "2021-04-29"]) == 0
    assert fake_claude() == [] and runs(tmp_path) == []


@needs_data
@pytest.mark.slow
def test_dry_run_shows_the_plan_and_calls_nothing(fake_claude, capsys):
    assert RA.main(["--pleno", "2021-04-29", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "extraction-reviewer" in out and "classification-auditor" in out and "dry run" in out
    assert fake_claude() == []


@needs_data
@pytest.mark.slow
def test_monthly_cap_skips_and_is_logged(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("LCP_QA_TOKEN_CAP", "10")
    assert RA.main(["--pleno", "2021-04-29", "--only", "classification-auditor"]) == 0
    assert fake_claude() == []
    assert [r["exit"] for r in runs(tmp_path)] == ["cap"]


# ── a real run with the fake claude ──

@needs_data
@pytest.mark.slow
def test_run_records_tokens_and_verifies_the_output(tmp_path, fake_claude, data_without_patches):
    # GOOD patches 2021-04-29-005: without a copy of data/, a real patch for it would make N7 drop it
    data = data_without_patches("2021-04-29-005")
    out = tmp_path / "verified.json"
    assert RA.main(["--data-dir", str(data), "--pleno", "2021-04-29", "--only", "extraction-reviewer",
                    "--output", str(out)]) == 0
    [call] = fake_claude()
    assert call["key"] == "sk-test" and "acta.txt" in call["files"] and call["prompt_len"] > 1000
    assert "Pleno 2021-04-29" not in call["cwd"]          # temp dir, not the repo
    [rec] = runs(tmp_path)
    assert rec["trigger"] == "agents" and rec["agent"] == "extraction-reviewer" and rec["model"] == "sonnet"
    assert rec["tokens"] == 2000 and rec["output_tokens"] == 500 and rec["cost_usd"] == 0.0123
    assert (rec["proposals"], rec["accepted"], rec["dropped"]) == (3, 1, 2)
    verified = json.loads(out.read_text())
    assert [p["subject"] for p in verified] == ["2021-04-29-005"]
    assert verified[0]["evidence"]["file"] == "data/raw/texts/2021-04-29.txt"
    assert verified[0]["agent"] == "extraction-reviewer" and verified[0]["fp"].startswith("C6-")


@needs_data
@pytest.mark.slow
def test_subscription_run_has_no_api_key_and_skips_the_cap(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("LCP_QA_TOKEN_CAP", "10")          # an API run would be skipped
    monkeypatch.setenv("ANTHROPIC", "sk-other")
    assert RA.main(["--subscription", "--pleno", "2021-04-29", "--only", "classification-auditor"]) == 0
    [call] = fake_claude()
    assert call["key"] is None and "--bare" not in call["argv"] and "--strict-mcp-config" in call["argv"]
    [rec] = runs(tmp_path)
    assert rec["auth"] == "subscription" and rec["exit"] == 0


@needs_data
@pytest.mark.slow
def test_a_sweep_saves_after_every_run_and_resumes(tmp_path, fake_claude):
    """F5 overnight sweep: a stop in the middle keeps what is done, --resume skips it."""
    plenos = tmp_path / "plenos.txt"
    plenos.write_text("# sweep\n2021-04-29\n2021-04-29\n")
    out = tmp_path / "sweep" / "verified.json"
    args = ["--subscription", "--plenos-file", str(plenos), "--only", "classification-auditor", "--output", str(out)]
    assert RA.main(args) == 0
    assert len(fake_claude()) == 1                         # the duplicate line runs once
    assert (tmp_path / "sweep" / "verified.json.done").read_text() == "2021-04-29 classification-auditor\n"
    kept = json.loads(out.read_text())
    assert RA.main(args) == 2                              # never overwrites a sweep without --resume
    assert RA.main([*args, "--resume"]) == 0
    assert len(fake_claude()) == 1 and json.loads(out.read_text()) == kept


@needs_data
@pytest.mark.slow
def test_a_sweep_stops_after_failures_in_a_row(tmp_path, fake_claude):
    (tmp_path / "answer.json").write_text(json.dumps(
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "usage": {}}))
    out = tmp_path / "verified.json"
    ivs = json.loads((DATA / "raw/interventions_raw.json").read_text())
    four = sorted({iv["pleno_id"] for iv in ivs})[:RA.MAX_FAILURES + 1]
    args = ["--subscription", "--only", "classification-auditor", "--output", str(out)]
    assert RA.main([*args, *(a for p in four for a in ("--pleno", p))]) == 3
    assert len(fake_claude()) == RA.MAX_FAILURES
    assert json.loads(out.read_text()) == [] and not (tmp_path / "verified.json.done").exists()


def test_sections_are_capped_each_and_in_all():
    small, runaway = "a" * 1000, "b" * (RA.SECTION_CHARS * 3)
    out = RA.cap_sections([small, runaway, runaway, small])
    assert out[0] == small
    assert out[1].startswith("b" * RA.SECTION_CHARS) and "section cut at" in out[1]
    assert sum(len(s) for s in out) < RA.SECTIONS_CHARS + 500
    assert out[-1].startswith("[… more sections")


def test_subscription_is_refused_under_launchd(fake_claude):
    assert RA.main(["--subscription", "--trigger", "launchd", "--pleno", "2021-04-29"]) == 2
    assert fake_claude() == []


def test_api_key_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OTHER=1\nANTHROPIC=sk-from-env\n")
    assert RA.load_api_key(tmp_path) == "sk-from-env"


# ── E7 on the real 2026-07-23 acta, before acf7cad added the two cessions ──

@pytest.mark.skipif(not (DATA / "raw/texts/2026-07-23.txt").exists(), reason="data/ not present")
def test_e7_finds_the_two_cessions_of_2026_07_23(tmp_path):
    rc.load_checks()
    d = tmp_path / "data"
    (d / "raw/texts").mkdir(parents=True)
    (d / "corrections").mkdir()
    ivs = [iv for iv in json.loads((DATA / "raw/interventions_raw.json").read_text())
           if iv["pleno_id"] == "2026-07-23"]
    shutil.copy(DATA / "raw/texts/2026-07-23.txt", d / "raw/texts/")
    shutil.copy(DATA / "raw/entity_variant_map.json", d / "raw/")
    shutil.copy(DATA / "entitats.json", d / "entitats.json")
    # Today's data: the cessions are recorded, so they are not candidates
    (d / "raw/interventions_raw.json").write_text(json.dumps(ivs))
    assert not {"2026-07-23-005", "2026-07-23-006"} & {f.subject for f in REGISTRY["E7"].fn(Context(d))}
    # Before acf7cad: no entitat_cessio
    for iv in ivs:
        iv.pop("entitat_cessio", None)
    (d / "raw/interventions_raw.json").write_text(json.dumps(ivs))
    found = {f.subject: f for f in REGISTRY["E7"].fn(Context(d))}
    assert {"2026-07-23-005", "2026-07-23-006"} <= set(found)
    assert "Víctimes de la DANA" in found["2026-07-23-005"].message

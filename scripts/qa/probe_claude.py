#!/usr/bin/env python3
"""Can the agents run from launchd? (arquitectura-agentes.md F2.8)

Run by the es.laciutatparla.qa-probe LaunchDaemon (scripts/qa/install_launchd.sh --probe), where
there is no login session and the login keychain is locked. Checks what run_agents.py needs:

  claude   found on PATH, and `claude -p --bare` answers with the API key from .env
           (one Haiku turn, under 0.01 $)
  gh       found and authenticated (propose.py --push needs it)

Writes one line to runs.jsonl: {"trigger": "probe", "exit": 0, "result": "OK", …}.

    "$PY" scripts/qa/probe_claude.py            # same check by hand, from SSH
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa.model import state_dir  # noqa: E402
from qa.run_agents import load_api_key  # noqa: E402
from qa.run_checks import State  # noqa: E402


def main() -> int:
    rec: dict = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "trigger": "probe",
                 "user": os.environ.get("USER"), "path": os.environ.get("PATH")}
    claude = shutil.which(os.environ.get("LCP_CLAUDE_BIN", "claude"))
    rec["claude"] = claude
    gh = shutil.which("gh")
    rec["gh"] = bool(gh) and subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0
    key = load_api_key()
    rec["api_key"] = bool(key)
    if not claude or not key:
        rec.update(exit="no-claude" if not claude else "no-api-key", result=None)
    else:
        p = subprocess.run(
            [claude, "-p", "--bare", "--model", "haiku", "--max-turns", "1", "--max-budget-usd", "0.05",
             "--output-format", "json", "--no-session-persistence", "--disallowedTools=Bash,Edit,Write"],
            input="Reply with exactly: OK", capture_output=True, text=True, timeout=120,
            env={**os.environ, "ANTHROPIC_API_KEY": key}, cwd=state_dir() if state_dir().exists() else None)
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {}
        result = (out.get("result") or "").strip()
        u = out.get("usage") or {}
        rec.update(result=result or None, cost_usd=out.get("total_cost_usd"),
                   tokens=sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                            "cache_read_input_tokens", "output_tokens")),
                   exit=0 if p.returncode == 0 and result.startswith("OK") else (p.returncode or "unexpected"),
                   stderr=p.stderr[-300:] or None)
    State(state_dir()).append("runs.jsonl", [rec])
    print(json.dumps({k: v for k, v in rec.items() if k != "path"}, ensure_ascii=False))
    return 0 if rec["exit"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

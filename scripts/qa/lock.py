#!/usr/bin/env python3
"""The shared run lock in $LCP_QA_STATE/lock (§5): one job at a time on the dedicated Mac.

    "$PY" scripts/qa/lock.py --trigger launchd -- bash scripts/qa/daily.sh --locked
    "$PY" scripts/qa/lock.py hold       # take it by hand until Ctrl-C (to test, or to keep jobs off)

If the lock is taken, the command does not start; the attempt goes to runs.jsonl with
"exit": "locked" and lock.py exits 75. Also honours PAUSE.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa.model import state_dir  # noqa: E402
from qa.run_checks import EXIT_LOCKED, State, now  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[argv.index("--") + 1:] if "--" in argv else []
    own = argv[:argv.index("--")] if "--" in argv else argv
    ap = argparse.ArgumentParser(description="run a command under the QA lock")
    ap.add_argument("action", nargs="?", choices=["hold"], help="hold the lock until Ctrl-C")
    ap.add_argument("--trigger", default="manual")
    args = ap.parse_args(own)

    state = State(state_dir())
    if state.paused and not args.action:
        print(f"PAUSE present in {state.root}: nothing runs.")
        return 0
    if not state.acquire():
        print(f"{state.path('lock')} is taken: not starting.", file=sys.stderr)
        state.append("runs.jsonl", [{"ts": now(), "trigger": args.trigger, "exit": "locked",
                                     "cmd": " ".join(cmd) or args.action}])
        return EXIT_LOCKED
    try:
        if args.action == "hold":
            signals = {signal.SIGINT, signal.SIGTERM}
            signal.pthread_sigmask(signal.SIG_BLOCK, signals)
            print(f"holding {state.path('lock')}; Ctrl-C to release", flush=True)
            signal.sigwait(signals)
            return 0
        if not cmd:
            ap.error("nothing to run: give a command after --")
        return subprocess.call(cmd)
    finally:
        state.release()


if __name__ == "__main__":
    sys.exit(main())

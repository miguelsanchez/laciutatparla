#!/usr/bin/env bash
# The daily sentinel job (launchd, 08:00). Design: arquitectura-agentes.md §4 and §10 F0.10.
#
#   lock → sync_repo.sh → doctor.sh --auth → run_checks.py → notify.py
#
# Never commits or pushes: all state stays in $LCP_QA_STATE (~/.lcp-qa). Silent by default:
# notify.py emails only a new P0/P1 or a new acta, and pings healthchecks.io when the run
# finished. A divergent repo or expired credentials email you and skip the ping, so
# healthchecks.io notices even if the email itself fails.
#
#   bash scripts/qa/daily.sh            # what launchd runs: takes the lock, then the steps
#   bash scripts/qa/daily.sh --locked   # (internal) the steps, lock already held
set -uo pipefail

LCP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$LCP_ROOT/scripts/.venv/bin/python"
STATE="${LCP_QA_STATE:-$HOME/.lcp-qa}"
TRIGGER="${LCP_QA_TRIGGER:-launchd}"
cd "$LCP_ROOT"

log() { echo "[$(date '+%F %T')] daily: $*"; }

rotate_logs() {  # keep launchd logs under ~1 MB × 5
  local f
  for f in "$STATE"/logs/*.log; do
    [[ -f "$f" ]] || continue
    if (( $(stat -f %z "$f") > 1048576 )); then
      for i in 4 3 2 1; do [[ -f "$f.$i" ]] && mv "$f.$i" "$f.$((i + 1))"; done
      mv "$f" "$f.1"
    fi
  done
}

case "${1:-}" in
  "")
    mkdir -p "$STATE/logs"
    rotate_logs
    exec "$PY" scripts/qa/lock.py --trigger "$TRIGGER" -- bash "$LCP_ROOT/scripts/qa/daily.sh" --locked
    ;;
  --locked)
    log "sync"
    bash scripts/qa/sync_repo.sh || { log "repo not synced: no checks, no ping"; exit 10; }
    # main may have new scripts now: continue with the updated version of this file
    exec bash "$LCP_ROOT/scripts/qa/daily.sh" --synced
    ;;
  --synced)
    log "doctor --auth"
    if ! out=$(bash scripts/qa/doctor.sh --auth 2>&1); then
      echo "$out"
      "$PY" scripts/qa/notify.py --alert "autenticación caducada" --force \
        --body "$(hostname -s): doctor.sh --auth falla. No se ha ejecutado ningún check.

$out" || true
      log "auth failed: no checks, no ping"
      exit 11
    fi
    log "run_checks"
    "$PY" scripts/qa/run_checks.py --no-lock --trigger "$TRIGGER"
    log "run_checks exit $?"
    log "notify"
    "$PY" scripts/qa/notify.py
    ;;
  *)
    echo "usage: daily.sh [--locked|--synced]" >&2
    exit 2
    ;;
esac

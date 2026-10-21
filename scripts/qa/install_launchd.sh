#!/usr/bin/env bash
# Install the daily QA job on the dedicated Mac (arquitectura-agentes.md §10 F0.10).
#
#   bash scripts/qa/install_launchd.sh            # render, validate, install (asks for sudo)
#   bash scripts/qa/install_launchd.sh --print    # only print the rendered plist
#   bash scripts/qa/install_launchd.sh --uninstall
#   bash scripts/qa/install_launchd.sh --probe            # F2.8: one-shot claude -p test from launchd
#   bash scripts/qa/install_launchd.sh --uninstall-probe
#
# Run it as the user the job must run as (lcp), not with sudo: it renders the template with
# that user's LCP_ROOT, PATH, HOME and state dir, and uses sudo only to install it.
#
# The job is a LaunchDaemon (/Library/LaunchDaemons, system domain) with UserName = that
# user. A LaunchAgent would need a GUI login session, which lcp never has: it is reached
# through SSH and `su -`, and with FileVault on and no autologin (§11.7) there is none after
# a restart either. Refuses any plist that would bypass permissions.
set -euo pipefail

if (( $(id -u) == 0 )); then
  echo "run as the job's user (e.g. lcp), not as root: sudo is used only to install" >&2
  exit 2
fi

LCP_ROOT="$(git rev-parse --show-toplevel)"
STATE="${LCP_QA_STATE:-$HOME/.lcp-qa}"
DAEMONS="/Library/LaunchDaemons"
DOMAIN="system"
FORBIDDEN='dangerously|bypass|acceptEdits'

# PATH for launchd: the directories of the tools the job calls, then the system ones
path_for_job() {
  local dirs=() t d
  for t in git claude gh node pdftotext tmux; do
    if d=$(command -v "$t" 2>/dev/null); then dirs+=("$(dirname "$d")"); fi
  done
  dirs+=(/opt/homebrew/bin /usr/local/bin /usr/bin /bin /usr/sbin /sbin)
  printf '%s\n' "${dirs[@]}" | awk '!seen[$0]++' | paste -sd: -
}

render() {  # $1 template
  sed -e "s|@LCP_ROOT@|$LCP_ROOT|g" -e "s|@PATH@|$(path_for_job)|g" \
      -e "s|@STATE@|$STATE|g" -e "s|@USER@|$(id -un)|g" -e "s|@HOME@|$HOME|g" "$1"
}

# A LaunchAgent left by the earlier installer (it never ran: lcp has no GUI session)
remove_old_agent() {  # $1 label
  launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$1.plist"
}

templates=("$LCP_ROOT"/scripts/qa/launchd/*.plist.tmpl)
probe=("$LCP_ROOT"/scripts/qa/launchd/probe/*.plist.tmpl)   # F2.8, installed only with --probe

uninstall() {  # templates…
  local t label
  for t in "$@"; do
    label=$(basename "$t" .plist.tmpl)
    sudo launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
    sudo rm -f "$DAEMONS/$label.plist"
    remove_old_agent "$label"
    echo "removed $label"
  done
}

case "${1:-}" in
  --print)
    for t in "${templates[@]}" "${probe[@]}"; do render "$t"; done
    exit 0
    ;;
  --probe)            # one-shot: runs once now, result in $STATE/runs.jsonl and logs/probe.log
    templates=("${probe[@]}")
    ;;
  --uninstall-probe) uninstall "${probe[@]}"; exit 0 ;;
  --uninstall) uninstall "${templates[@]}"; exit 0 ;;
  "") ;;
  *) echo "usage: install_launchd.sh [--print|--uninstall|--probe|--uninstall-probe]" >&2; exit 2 ;;
esac

# Created by the user, so launchd (which opens the log as root) appends to a file lcp owns
mkdir -p "$STATE/logs" "$STATE/backups"
touch "$STATE/logs/daily.log" "$STATE/logs/probe.log"

for t in "${templates[@]}"; do
  label=$(basename "$t" .plist.tmpl)
  out="$DAEMONS/$label.plist"
  tmp="$(mktemp)"
  render "$t" > "$tmp"
  if grep -qE "$FORBIDDEN" "$t" "$tmp"; then
    echo "refusing $label: the plist contains $(grep -oE "$FORBIDDEN" "$tmp" | head -1)" >&2
    rm -f "$tmp"
    exit 1
  fi
  if grep -q "@[A-Z_]*@" "$tmp"; then
    echo "refusing $label: unrendered placeholder $(grep -o '@[A-Z_]*@' "$tmp" | head -1)" >&2
    exit 1
  fi
  plutil -lint "$tmp" >/dev/null
  remove_old_agent "$label"
  sudo launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  sudo install -m 644 -o root -g wheel "$tmp" "$out"
  rm -f "$tmp"
  sudo launchctl bootstrap "$DOMAIN" "$out"
  echo "installed $label → $out, runs as $(id -un) (RunAtLoad: a first run starts now; logs in $STATE/logs/)"
  echo "run it by hand: sudo launchctl kickstart -k $DOMAIN/$label"
done

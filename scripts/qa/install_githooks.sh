#!/usr/bin/env bash
# Point git at the versioned hooks in scripts/qa/githooks (arquitectura-agentes.md F0b.5).
#
#   bash scripts/qa/install_githooks.sh                    # install
#   bash scripts/qa/install_githooks.sh --replace-local    # also when .git/hooks has differing hooks
#   bash scripts/qa/install_githooks.sh --uninstall
#
# core.hooksPath makes git ignore .git/hooks/ entirely. So a hook that only exists there
# (like the dedicated Mac's pre-push, P.10) would stop running without a word: the script
# refuses while .git/hooks holds a hook that differs from the versioned one, and shows the
# diff, until you have compared them and pass --replace-local.
set -euo pipefail

LCP_ROOT="$(git rev-parse --show-toplevel)"
VERSIONED="scripts/qa/githooks"
LOCAL="$(git rev-parse --path-format=absolute --git-common-dir)/hooks"
cd "$LCP_ROOT"

case "${1:-}" in
  --uninstall)
    git config --unset core.hooksPath || true
    echo "core.hooksPath removed: git uses $LOCAL again"
    exit 0
    ;;
  ""|--replace-local) ;;
  *) echo "usage: install_githooks.sh [--replace-local|--uninstall]" >&2; exit 2 ;;
esac

conflicts=0
for hook in "$LOCAL"/*; do
  [[ -f "$hook" && -x "$hook" && "$hook" != *.sample ]] || continue
  name=$(basename "$hook")
  if [[ -f "$VERSIONED/$name" ]] && cmp -s "$hook" "$VERSIONED/$name"; then
    continue
  fi
  conflicts=$((conflicts + 1))
  echo "── local hook $LOCAL/$name"
  if [[ -f "$VERSIONED/$name" ]]; then
    echo "   differs from $VERSIONED/$name:"
    diff -u "$hook" "$VERSIONED/$name" | sed 's/^/   /' || true
  else
    echo "   has no versioned counterpart: with core.hooksPath it would stop running."
  fi
done
if (( conflicts )) && [[ "${1:-}" != "--replace-local" ]]; then
  echo
  echo "Not installed: $conflicts local hook(s) would be silenced. Compare them above; if the"
  echo "versioned ones cover them, run again with --replace-local (or port what is missing"
  echo "to $VERSIONED in a PR first)."
  exit 1
fi

chmod +x "$VERSIONED"/*
git config core.hooksPath "$VERSIONED"
echo "core.hooksPath = $VERSIONED ($(ls "$VERSIONED" | paste -sd' ' -))"

#!/usr/bin/env bash
# Bring the dedicated Mac's checkout to origin/main before a run (arquitectura-agentes.md §10.0c).
#
#   git fetch → git switch main → git pull --ff-only
#
# Fast-forward only: local main never gets commits, so if it cannot fast-forward something
# is wrong. Then, and also with a dirty tree, nothing runs: it emails "repo divergente" and
# exits 10 without pinging, so healthchecks.io notices even if the email fails.
# Also warns (without stopping) about ingest/* or qa/* branches with commits not pushed
# for more than 24 h.
#
# Exit: 0 synced · 10 divergent / dirty / fetch failed (alert sent)
set -uo pipefail

LCP_ROOT="$(git rev-parse --show-toplevel)"
PY="$LCP_ROOT/scripts/.venv/bin/python"
cd "$LCP_ROOT"

alert() {  # $1 subject, $2 body
  echo "sync_repo: $1" >&2
  "$PY" scripts/qa/notify.py --alert "$1" --body "$2" --force || true
}

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  alert "repo divergente: árbol sucio" "$(hostname -s): $LCP_ROOT tiene cambios sin commit en $(git branch --show-current). No se ha ejecutado ningún check.

$(git status --short --untracked-files=no | head -30)"
  exit 10
fi

if ! git fetch --quiet --prune origin; then
  alert "repo divergente: git fetch falló" "$(hostname -s): no se pudo hacer git fetch de origin (¿red o deploy key?). No se ha ejecutado ningún check."
  exit 10
fi

# Unpushed work on ingest/* and qa/* branches older than 24 h
now=$(date +%s)
stale=""
while read -r br; do
  [[ -z "$br" ]] && continue
  upstream="origin/$br"
  if git rev-parse --verify --quiet "$upstream" >/dev/null; then
    range="$upstream..$br"
  else
    range="origin/main..$br"
  fi
  oldest=$(git log --format=%ct --reverse "$range" 2>/dev/null | head -1)
  if [[ -n "$oldest" ]] && (( now - oldest > 86400 )); then
    stale+="  $br ($(git rev-list --count "$range") commit(s) sin push)"$'\n'
  fi
done < <(git for-each-ref --format='%(refname:short)' refs/heads/ingest refs/heads/qa)
if [[ -n "$stale" ]]; then
  alert "ramas sin push > 24 h" "$(hostname -s): estas ramas tienen commits sin push desde hace más de 24 h:
$stale
Haz push (o bórralas) para no perder trabajo pagado si falla el disco."
fi

if ! git switch --quiet main || ! git merge --ff-only --quiet origin/main; then
  alert "repo divergente: main no avanza en fast-forward" "$(hostname -s): main local no puede avanzar en fast-forward a origin/main.
local:  $(git rev-parse --short main)
origin: $(git rev-parse --short origin/main)
No se ha ejecutado ningún check. Revísalo por SSH; main local nunca debería tener commits propios."
  exit 10
fi
echo "sync_repo: main at $(git rev-parse --short HEAD) (origin/main)"

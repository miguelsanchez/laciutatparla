#!/usr/bin/env bash
# /apply-approved, in two halves (arquitectura-agentes.md §6.3 step 4, F1.5).
#
#   bash scripts/qa/apply.sh plan <PR>   # no derived data written: checks, rebase onto main if
#                                        # needed (sources only), rejects, preview
#   bash scripts/qa/apply.sh run <PR>    # after your explicit yes: regenerate data/ on the PR branch
#
# Both work in the QA worktree ($LCP_QA_WORKTREE, default ../lcp-qa), never in the main checkout,
# and take the shared lock (~/.lcp-qa/lock): the daily job and /publish wait.
#
# run: backup → apply_merges → 07 → export_dataset → pytest → run_checks --fast → C4 (language
# rule) → C1b (bold texts must not drop) → npm run build → W6/W8 (page weight, internal links)
# → commit + push to the PR branch → data
# summary in the PR body.
# Any failure restores the backup and the derived files, and stops before committing.
#
# Refuses on main, and on any branch without an open qa-data PR.
set -uo pipefail

MAIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$MAIN/scripts/.venv/bin/python"
WT="${LCP_QA_WORKTREE:-$(cd "$MAIN/.." && pwd)/lcp-qa}"
STATE="${LCP_QA_STATE:-$HOME/.lcp-qa}"

usage() { echo "usage: apply.sh plan|run <PR number>" >&2; exit 2; }
die() { echo "apply: $*" >&2; exit 1; }

MODE="${1:-}"; PR="${2:-}"
[[ "$MODE" == plan || "$MODE" == run || "$MODE" == --locked-plan || "$MODE" == --locked-run ]] || usage
[[ "$PR" =~ ^[0-9]+$ ]] || usage

# Take the lock, then come back as --locked-*
if [[ "$MODE" == plan || "$MODE" == run ]]; then
  exec "$PY" "$MAIN/scripts/qa/lock.py" --trigger "apply-$MODE" -- bash "$MAIN/scripts/qa/apply.sh" "--locked-$MODE" "$PR"
fi
MODE="${MODE#--locked-}"

[[ -d "$WT/.git" || -f "$WT/.git" ]] || die "no QA worktree at $WT (propose.py creates it)"
cd "$WT"
git fetch -q origin || die "git fetch failed"
BRANCH="$("$PY" "$MAIN/scripts/qa/apply_steps.py" check --pr "$PR" --worktree "$WT")" || exit 1
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || die "$WT has uncommitted changes"
git switch -q -C "$BRANCH" "origin/$BRANCH" || die "cannot check out $BRANCH"
echo "apply: PR #$PR · branch $BRANCH · worktree $WT"

step() { echo; echo "── $*"; }

if [[ "$MODE" == plan ]]; then
  step "rebase onto origin/main (source changes only)"
  "$PY" "$MAIN/scripts/qa/apply_steps.py" rebase --worktree "$WT" || exit 1
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]]; then
    git push -q --force-with-lease origin "$BRANCH" || die "push of the rebased branch failed"
  fi
  step "rejects (PR comments and entries removed by hand)"
  "$PY" "$MAIN/scripts/qa/sync.py" --pr "$PR" --worktree "$WT" || exit 1
  step "what will change"
  "$PY" "$MAIN/scripts/qa/apply_steps.py" preview --worktree "$WT"
  echo
  echo "apply: plan done, no derived data written. To apply: bash scripts/qa/apply.sh run $PR"
  exit 0
fi

# ── run ────────────────────────────────────────────────────────────────────────
"$PY" -c "import sys; sys.path.insert(0, '$MAIN/scripts'); from qa.apply_steps import _is_ancestor; from pathlib import Path; sys.exit(0 if _is_ancestor(Path('$WT')) else 1)" \
  || die "the branch does not contain origin/main: run 'apply.sh plan $PR' first"

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$STATE/backups/$TS-${BRANCH//\//-}"
mkdir -p "$BACKUP"
for f in data/raw/interventions_raw.json data/entitats.json data/raw/entity_variant_map.json; do
  cp "$f" "$BACKUP/" || die "backup of $f failed"
done
echo "apply: backup in $BACKUP"
BOLD_BEFORE="$("$PY" "$MAIN/scripts/qa/apply_steps.py" bold-count --worktree "$WT")"

restore() {
  echo "apply: FAILED at '$1' — restoring" >&2
  cp "$BACKUP/interventions_raw.json" data/raw/ && cp "$BACKUP/entity_variant_map.json" data/raw/ \
    && cp "$BACKUP/entitats.json" data/
  # meta/qa/baseline.json too: prune-baseline writes it, and a failure after it (C1b, build, W6/W8)
  # left the worktree dirty, so the next 'apply.sh plan' refused to start (PR #95, #106)
  git checkout -q -- data web/public/datos meta/qa/baseline.json 2>/dev/null
  git clean -qfd -- data/plenos web/public/datos 2>/dev/null
  echo "apply: restored; nothing committed" >&2
  exit 1
}

step "apply_merges.py";        "$PY" scripts/apply_merges.py        || restore apply_merges
step "07_build_final_json.py"; "$PY" scripts/07_build_final_json.py || restore 07
step "export_dataset.py";      "$PY" scripts/export_dataset.py      || restore export_dataset
step "pytest";                 "$PY" -m pytest scripts/tests -q -p no:cacheprovider || restore pytest
step "run_checks --fast";      "$PY" scripts/qa/run_checks.py --fast --offline --no-state --strict --trigger apply || restore run_checks
# C4 is not a fast check, but a translation left in the wrong language is what reached the web
# with 2026-04-30-102: the language rule must hold on every applied PR.
step "C4: language rule";      "$PY" scripts/qa/run_checks.py --only C4 --offline --no-state --strict --trigger apply || restore C4
step "baseline: drop what the applied proposals fixed"
"$PY" "$MAIN/scripts/qa/apply_steps.py" prune-baseline --worktree "$WT" || restore prune-baseline
step "C1b: texts with ** must not drop"
BOLD_AFTER="$("$PY" "$MAIN/scripts/qa/apply_steps.py" bold-count --worktree "$WT")"
echo "texts with **: $BOLD_BEFORE → $BOLD_AFTER"
(( BOLD_AFTER >= BOLD_BEFORE )) || restore "C1b (bold markers lost)"
step "npm run build"
[[ -e web/node_modules ]] || ln -s "$MAIN/web/node_modules" web/node_modules
(cd web && npm run build >/dev/null 2>"$BACKUP/build.err") || { tail -20 "$BACKUP/build.err" >&2; restore "npm run build"; }
step "W6 page weight + W8 internal links (on the new build)"
"$PY" scripts/qa/run_checks.py --only W6,W8 --offline --no-state --strict --trigger apply || restore "W6/W8"

step "commit and push to $BRANCH"
git add -A data web/public/datos meta/qa
if git diff --cached --quiet; then
  echo "apply: nothing changed in the data"
else
  git commit -q -m "qa: apply approved corrections (PR #$PR)

apply_merges → 07 → export_dataset, regenerated by /apply-approved after confirmation.
Backup: $BACKUP

Co-Authored-By: apply.sh <noreply@laciutatparla.es>" || restore commit
  git push -q origin "$BRANCH" || die "push failed: the commit is local in $WT, push it by hand"
fi
step "data summary in the PR"
"$PY" "$MAIN/scripts/qa/apply_steps.py" summary --pr "$PR" --worktree "$WT"
echo
echo "apply: done. Review the PR and merge it (rebase and merge): merging publishes the site."

#!/usr/bin/env bash
# /publish (arquitectura-agentes.md §6.3 step 6, F1.6), adjusted to how the site is really built.
#
# Cloudflare Pages builds `main` of the private repo: merging a PR already publishes the site.
# /publish only refreshes the public mirror and checks production, in two separate commands so
# that the force-push is a step of its own, approved on its own:
#
#   bash scripts/qa/publish.sh check   # main up to date, web built, tests and checks green
#   bash scripts/qa/publish.sh push    # force-push the snapshot to the public mirror, check production
#
# push-public.sh itself asks nothing: the only confirmation is the permission prompt Claude Code
# shows for each of these commands (neither is in the guard allowlist). `push` refuses unless
# `check` passed on this exact commit.
#
# Both take the shared lock, waiting up to 10 minutes if a check or /apply-approved holds it, and
# refuse with a dirty tree or if main cannot fast-forward to origin/main. Never run from a job.
set -uo pipefail

MAIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$MAIN/scripts/.venv/bin/python"
STATE="${LCP_QA_STATE:-$HOME/.lcp-qa}"
SITE="${LCP_SITE:-https://laciutatparla.es}"
CHECKED="$STATE/publish-checked"

MODE="${1:-}"
case "$MODE" in
  check|push)
    for i in $(seq 1 20); do
      "$PY" "$MAIN/scripts/qa/lock.py" --trigger "publish-$MODE" -- bash "$MAIN/scripts/qa/publish.sh" "--locked-$MODE"
      rc=$?
      [[ $rc -ne 75 ]] && exit $rc
      echo "publish: lock taken (a check or /apply-approved is running); retry $i/20 in 30 s" >&2
      sleep 30
    done
    echo "publish: the lock stayed taken for 10 minutes; giving up" >&2
    exit 75
    ;;
  --locked-check|--locked-push) MODE="${MODE#--locked-}" ;;
  *) echo "usage: publish.sh check|push" >&2; exit 2 ;;
esac

cd "$MAIN"
die() { echo "publish: $*" >&2; exit 1; }

[[ -z "$(git status --porcelain --untracked-files=no)" ]] || die "uncommitted changes in $MAIN: refusing"
git fetch -q origin || die "git fetch failed"
git switch -q main || die "cannot switch to main"
git merge -q --ff-only origin/main || die "main cannot fast-forward to origin/main"
HEAD_SHA="$(git rev-parse HEAD)"
echo "publish: main at ${HEAD_SHA:0:7}"

if [[ "$MODE" == check ]]; then
  rm -f "$CHECKED"
  echo "── npm run build (the tests read web/dist)"
  (cd web && npm run build >/dev/null 2>"$STATE/publish-build.err") || { tail -20 "$STATE/publish-build.err" >&2; die "web build failed"; }
  echo "── pytest"
  "$PY" -m pytest scripts/tests -q -p no:cacheprovider || die "tests fail on main: not publishing"
  echo "── run_checks --fast"
  "$PY" scripts/qa/run_checks.py --fast --offline --no-state --strict --trigger publish || die "new QA findings on main"
  mkdir -p "$STATE" && echo "$HEAD_SHA" > "$CHECKED"
  echo
  echo "publish: main ${HEAD_SHA:0:7} is ready. Next, to force-push it to the public mirror: bash scripts/qa/publish.sh push"
  exit 0
fi

# ── push ───────────────────────────────────────────────────────────────────────
[[ -f "$CHECKED" && "$(cat "$CHECKED")" == "$HEAD_SHA" ]] \
  || die "'publish.sh check' has not passed on ${HEAD_SHA:0:7}: run it first"
echo "── public mirror: force-push of the snapshot (push-public.sh)"
bash push-public.sh || die "push-public.sh failed"
rm -f "$CHECKED"

TOTAL="$("$PY" -c "import json; print(len(json.load(open('data/intervencions.json'))))")"
echo "── production should show $TOTAL interventions ($SITE/val/dades/)"
# Every 30 s for 10 minutes. The page is fetched whole before grep: piped into `grep -q`, curl dies
# writing once grep has matched and exits, and pipefail turns that match into a failure.
for attempt in $(seq 1 20); do
  (( attempt > 1 )) && sleep 30
  page="$(curl -sfL --max-time 20 "$SITE/val/dades/?publish=$(date +%s)")" || page=""
  if grep -q "$TOTAL intervencions" <<<"$page"; then
    echo "publish: production shows $TOTAL interventions ✓"
    exit 0
  fi
done
echo "publish: production does not show $TOTAL after 10 minutes. The mirror is pushed, but it does not" >&2
echo "publish: deploy the site: Cloudflare Pages builds main of the private repo on merge. Check its" >&2
echo "publish: dashboard for that build. Not counted as a failure." >&2
exit 0

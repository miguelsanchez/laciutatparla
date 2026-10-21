#!/usr/bin/env bash
# Health check of the dedicated Mac (arquitectura-agentes.md §10.0b, task P.9).
#
#   bash scripts/qa/doctor.sh          # everything (P.1–P.12 + disk, FileVault, auth, sync)
#   bash scripts/qa/doctor.sh --auth   # only what expires and the daily job uses: gh, SSH
#                                      # deploy keys, SMTP (run by daily.sh; on failure it
#                                      # emails and skips the ping)
#
# The Claude subscription is checked only in the full run: the daily job runs as a
# LaunchDaemon with no login session, so it cannot unlock the login keychain where
# `claude` keeps its credentials, and F0's checks use no LLM anyway (decided in F2).
#
# Read-only: it changes nothing. Prints one ✅/❌/⚠️ line per check.
# Exit: 0 all ✅ (⚠️ allowed) · 1 at least one ❌
set -uo pipefail

LCP_ROOT="$(git rev-parse --show-toplevel)"
PY="$LCP_ROOT/scripts/.venv/bin/python"
STATE="${LCP_QA_STATE:-$HOME/.lcp-qa}"
MODE="${1:-all}"
cd "$LCP_ROOT"

fails=0
ok()   { printf '✅ %-28s %s\n' "$1" "${2:-}"; }
bad()  { printf '❌ %-28s %s\n' "$1" "${2:-}"; fails=$((fails + 1)); }
warn() { printf '⚠️  %-27s %s\n' "$1" "${2:-}"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ── Claude subscription (full run only, see header) ───────────────────────────
check_claude() {
  if have claude && out=$(cd "$STATE" 2>/dev/null || cd "$HOME"; claude -p "responde OK" --max-turns 1 2>&1) \
      && grep -qi "ok" <<<"$out"; then
    ok "claude (suscripción)" "responde"
  else
    bad "claude (suscripción)" "claude -p falla: ${out:-no instalado}"
  fi
}

# ── What expires (also --auth) ────────────────────────────────────────────────
check_auth() {
  if have gh && gh auth status >/dev/null 2>&1; then
    ok "gh auth" "$(gh auth status 2>&1 | grep -m1 -o 'Logged in to [^ ]* account [^ ]*')"
  else
    bad "gh auth" "gh auth status falla (¿token caducado? se anota en meta/qa/horizon.yml)"
  fi

  if git ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
    ok "ssh repo privado (origin)" "$(git remote get-url origin)"
  else
    bad "ssh repo privado (origin)" "git ls-remote origin falla"
  fi
  # Cloudflare Pages builds from the private repo; `public` is only the mirror that
  # /publish updates, so a failure here must not stop the daily checks: warn only.
  if git remote get-url public >/dev/null 2>&1; then
    if git ls-remote --exit-code public HEAD >/dev/null 2>&1; then
      ok "ssh repo público (public)" "$(git remote get-url public)"
    else
      warn "ssh repo público (public)" "git ls-remote public falla (solo afecta al espejo)"
    fi
  else
    warn "ssh repo público (public)" "no hay remote 'public' (P.11)"
  fi

  if "$PY" scripts/qa/notify.py --check-smtp >/dev/null 2>&1; then
    ok "smtp" "login OK"
  else
    bad "smtp" "notify.py --check-smtp falla (QA_SMTP_USER / QA_SMTP_PASS)"
  fi
}

check_all() {
  # P.1 timezone
  tz=$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')
  [[ "$tz" == "Europe/Madrid" ]] && ok "P.1 zona horaria" "$tz" || bad "P.1 zona horaria" "${tz:-?} (esperado Europe/Madrid)"

  # P.2 tools
  for t in git pdftotext node gh tmux claude; do
    have "$t" && ok "P.2 $t" "$(command -v "$t")" || bad "P.2 $t" "no está en PATH"
  done

  # P.3 clone
  n=$(git ls-files data/raw | wc -l | tr -d ' ')
  (( n >= 500 )) && ok "P.3 clon con data/raw" "$n ficheros" || bad "P.3 clon con data/raw" "$n ficheros"
  # Use origin's SSH host: on the dedicated Mac it is an alias (github-lcp-priv) that
  # selects the deploy key; plain github.com would try no deploy key at all.
  # ssh -T always exits 1 on GitHub, so read its output instead of its status.
  ssh_host=$(git remote get-url origin | sed -nE 's#^([^@]+@)?([^:/]+):.*#\2#p')
  sshout=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -T "git@${ssh_host:-github.com}" 2>&1 || true)
  if grep -q "successfully authenticated" <<<"$sshout"; then
    ok "P.3 ssh github" "$(head -1 <<<"$sshout" | cut -c1-60)"
  else
    bad "P.3 ssh github" "ssh -T git@github.com no autentica"
  fi

  # P.4 venv + web
  if "$PY" -c "import anthropic, yaml, bs4, requests, dotenv, pytest" 2>/dev/null; then
    ok "P.4 venv" "$("$PY" --version)"
  else
    bad "P.4 venv" "scripts/.venv falta o le faltan paquetes"
  fi
  [[ -d web/node_modules ]] && ok "P.4 web/node_modules" || bad "P.4 web/node_modules" "falta: cd web && npm ci"

  # P.5 .env
  if [[ -f .env ]]; then
    perm=$(stat -f %Lp .env)
    [[ "$perm" == 600 ]] && ok "P.5 .env permisos" 600 || bad "P.5 .env permisos" "$perm (esperado 600)"
    for k in ANTHROPIC QA_SMTP_USER QA_SMTP_PASS QA_HC_URL; do
      grep -qE "^$k=.+" .env && ok "P.5 .env $k" || bad "P.5 .env $k" "vacía o ausente"
    done
  else
    bad "P.5 .env" "no existe"
  fi

  # P.6 gh token scope. Any token can read public repos, so the test is that the only
  # private repo it sees is this one.
  if have gh; then
    mine=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)
    seen=$(gh repo list --visibility private --limit 50 --json nameWithOwner --jq '.[].nameWithOwner' 2>/dev/null)
    if [[ -n "$mine" && "$seen" == "$mine" ]]; then
      ok "P.6 token limitado" "solo ve $mine"
    else
      warn "P.6 token limitado" "ve $(grep -c . <<<"$seen") repos privados (p. ej. $(head -3 <<<"$seen" | paste -sd' ' -)); esperado solo $mine"
    fi
  fi

  # P.7 energy
  pm=$(pmset -g 2>/dev/null)
  grep -qE "^\s*sleep\s+0" <<<"$pm" && ok "P.7 sleep 0" || bad "P.7 sleep 0" "pmset sleep no es 0"
  grep -qE "^\s*autorestart\s+1" <<<"$pm" && ok "P.7 autorestart 1" || bad "P.7 autorestart 1" "pmset autorestart no es 1"
  fv=$(fdesetup status 2>/dev/null | head -1)
  auto=$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null || true)
  # The job is a LaunchDaemon: it needs no login session, only an unlocked disk.
  if [[ "$fv" == *"On"* ]]; then
    warn "P.7 FileVault" "activado: tras un reinicio hay que desbloquear el disco a mano (§11.7); el job no necesita sesión"
  else
    ok "P.7 FileVault" "desactivado${auto:+, autologin $auto}"
  fi

  # P.8 remote access
  if have tailscale && tailscale status >/dev/null 2>&1; then
    ok "P.8 tailscale" "$(tailscale ip -4 2>/dev/null | head -1)"
  else
    bad "P.8 tailscale" "no instalado o desconectado"
  fi
  tmux has-session -t lcp 2>/dev/null && ok "P.8 tmux lcp" || warn "P.8 tmux lcp" "no hay sesión 'lcp'"

  # P.10 main protection. Rulesets do not apply to private repos on a free personal
  # account, so the real barrier on this Mac is the local pre-push hook refusing main.
  hooks_dir=$(git rev-parse --path-format=absolute --git-path hooks 2>/dev/null)
  if [[ -x "$hooks_dir/pre-push" ]] && grep -q "main" "$hooks_dir/pre-push"; then
    ok "P.10 pre-push protege main" "$hooks_dir/pre-push"
  else
    bad "P.10 pre-push protege main" "no hay hook pre-push ejecutable que mencione main en $hooks_dir"
  fi
  if have gh; then
    if rs=$(gh api "repos/{owner}/{repo}/rulesets" --jq 'length' 2>/dev/null) && [[ "$rs" =~ ^[0-9]+$ ]] && (( rs > 0 )); then
      ok "P.10 ruleset en GitHub" "$rs ruleset(s)"
    else
      warn "P.10 ruleset en GitHub" "sin efecto en este plan (requiere GitHub Team/Pro)"
    fi
  fi

  # P.12 state + backup
  [[ -d "$STATE/backups" ]] && ok "P.12 $STATE/backups" || bad "P.12 $STATE/backups" "no existe"
  if tmutil destinationinfo 2>/dev/null | grep -q "Name"; then
    ok "P.12 Time Machine" "$(tmutil destinationinfo | grep -m1 Name | sed 's/.*: //')"
  else
    warn "P.12 Time Machine" "sin destino configurado"
  fi

  # Disk
  free_gb=$(df -g "$LCP_ROOT" | awk 'NR==2 {print $4}')
  (( free_gb > 10 )) && ok "disco libre" "${free_gb} GB" || bad "disco libre" "${free_gb} GB (< 10)"

  # launchd: a LaunchDaemon in the system domain, running as this user, never bypassing
  plist=/Library/LaunchDaemons/es.laciutatparla.qa.plist
  if [[ -f "$plist" ]]; then
    if grep -qE "dangerously|bypass|acceptEdits" "$plist"; then
      bad "plist sin bypass" "$plist contiene dangerously/bypass/acceptEdits"
    else
      ok "plist sin bypass" "$plist"
    fi
    runs_as=$(plutil -extract UserName raw -o - "$plist" 2>/dev/null)
    [[ "$runs_as" == "$(id -un)" ]] && ok "launchd UserName" "$runs_as" \
      || bad "launchd UserName" "${runs_as:-?} (esperado $(id -un))"
    if launchctl print system/es.laciutatparla.qa >/dev/null 2>&1; then
      ok "launchd system/" "es.laciutatparla.qa cargado"
    else
      bad "launchd system/" "el plist existe pero no está cargado: bash scripts/qa/install_launchd.sh"
    fi
  else
    warn "launchd" "job aún no instalado (F0.10)"
  fi
  if ls "$HOME"/Library/LaunchAgents/es.laciutatparla.* >/dev/null 2>&1; then
    warn "LaunchAgent antiguo" "queda en ~/Library/LaunchAgents; install_launchd.sh lo retira"
  fi

  # main in fast-forward with origin, clean tree
  git fetch --quiet origin 2>/dev/null
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    bad "árbol limpio" "hay cambios sin commit"
  else
    ok "árbol limpio"
  fi
  if git merge-base --is-ancestor main origin/main 2>/dev/null; then
    ok "main fast-forward" "main ⊆ origin/main"
  else
    bad "main fast-forward" "main local tiene commits que no están en origin/main"
  fi
}

if [[ "$MODE" != "--auth" ]]; then
  check_all
  check_claude
fi
check_auth

echo
if (( fails )); then
  echo "doctor: $fails problema(s)"
  exit 1
fi
echo "doctor: todo ✅"

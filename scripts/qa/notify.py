#!/usr/bin/env python3
"""Sentinel notifications: email via smtplib and the healthchecks.io dead-man ping.

Design: meta/docs/arquitectura-agentes.md §6.4. Deterministic, no LLM.

    "$PY" scripts/qa/notify.py                   # after run_checks: email the delta, then ping
    "$PY" scripts/qa/notify.py --test            # test email + success ping
    "$PY" scripts/qa/notify.py --alert "repo divergente" --body "…"   # email only, no ping
    "$PY" scripts/qa/notify.py --fail "run_checks crashed"            # ping /fail with a message
    "$PY" scripts/qa/notify.py --check-smtp      # log in and out, send nothing (doctor.sh)
    add --dry-run to print instead of sending

Rules (§6.4):
  - Email only when the last run has NEW findings at P0/P1, or a new acta / session (S1).
    No delta, no email. Never more than one email a day (--alert and --test included,
    unless --force).
  - The success ping goes out only after a run that finished (exit 0 or 1). A crash pings /fail.
    If this machine or launchd dies, the missing ping is what makes healthchecks.io write to you.

Configuration in $LCP_ROOT/.env (see .env.example): QA_SMTP_USER, QA_SMTP_PASS,
QA_HC_URL, and optionally QA_MAIL_TO (default: QA_SMTP_USER), QA_SMTP_HOST, QA_SMTP_PORT.
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import urllib.request
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa.model import REPO_ROOT, SEVERITIES, state_dir  # noqa: E402

ALERT_SEVERITIES = {"P0", "P1"}
ALWAYS_ALERT_KEYS = {"acta-published", "new-session"}  # S1: an acta to ingest is the point


def load_env() -> dict:
    from dotenv import dotenv_values
    env = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v is not None}
    return {**env, **{k: v for k, v in os.environ.items() if k.startswith("QA_")}}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── Content ──────────────────────────────────────────────────────────────────

def alertable(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("new") and (
        f["severity"] in ALERT_SEVERITIES or f.get("key") in ALWAYS_ALERT_KEYS)]


def subject_for(items: list[dict]) -> str:
    counts = [f"{s}×{n}" for s in SEVERITIES if (n := sum(f["severity"] == s for f in items))]
    actas = sorted({f["subject"] for f in items if f.get("key") == "acta-published"})
    tail = f" · acta nueva {', '.join(actas)}" if actas else ""
    return f"[LCP] {' '.join(counts)}{tail}"


def body_for(items: list[dict], last: dict) -> str:
    lines = [f"Ejecución {last.get('ts')} ({last.get('trigger')}): {len(items)} hallazgo(s) nuevo(s).", ""]
    order = {s: i for i, s in enumerate(SEVERITIES)}
    for f in sorted(items, key=lambda f: (order[f["severity"]], f["check"], f["subject"])):
        lines.append(f"{f['severity']} {f['check']} {f['subject']}: {f['message']}")
        url = (f.get("details") or {}).get("url_acta")
        if url:
            lines.append(f"    {url}")
        lines.append(f"    fp {f['fp']}")
    lines += ["", "Estado completo: ~/.lcp-qa/last_run.json · para pausar: touch ~/.lcp-qa/PAUSE"]
    return "\n".join(lines)


# ── Delivery ─────────────────────────────────────────────────────────────────

class Notifier:
    def __init__(self, env: dict, state: Path, dry_run: bool = False, force: bool = False) -> None:
        self.env, self.state, self.dry_run, self.force = env, state, dry_run, force

    def _require(self, *keys: str) -> None:
        missing = [k for k in keys if not self.env.get(k)]
        if missing:
            raise SystemExit(f"missing in .env: {', '.join(missing)}")

    def _sent_today(self) -> bool:
        p = self.state / "notify.json"
        return p.exists() and json.loads(p.read_text()).get("last_email") == date.today().isoformat()

    def _mark_sent(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "notify.json").write_text(json.dumps({"last_email": date.today().isoformat()}))

    def _smtp(self):
        host = self.env.get("QA_SMTP_HOST", "smtp.gmail.com")
        port = int(self.env.get("QA_SMTP_PORT", "465"))
        s = smtplib.SMTP_SSL(host, port, timeout=30)
        s.login(self.env["QA_SMTP_USER"], self.env["QA_SMTP_PASS"])
        return s

    def email(self, subject: str, body: str) -> bool:
        if self._sent_today() and not self.force:
            print("an email already went out today; skipping (anti-noise rule)")
            return False
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.env.get("QA_SMTP_USER", "lcp-qa@localhost")
        msg["To"] = self.env.get("QA_MAIL_TO") or self.env.get("QA_SMTP_USER", "")
        msg.set_content(body)
        if self.dry_run:
            print(f"--- email (dry run)\n{msg}")
            return True
        self._require("QA_SMTP_USER", "QA_SMTP_PASS")
        with self._smtp() as s:
            s.send_message(msg)
        self._mark_sent()
        print(f"email sent: {subject}")
        return True

    def check_smtp(self) -> None:
        self._require("QA_SMTP_USER", "QA_SMTP_PASS")
        if self.dry_run:
            print("smtp check (dry run)")
            return
        with self._smtp():
            pass
        print("smtp login OK")

    def ping(self, suffix: str = "", message: str = "") -> bool:
        url = self.env.get("QA_HC_URL", "").rstrip("/")
        if self.dry_run:
            print(f"--- ping (dry run): {url or '<QA_HC_URL>'}{suffix} {message!r}")
            return True
        self._require("QA_HC_URL")
        req = urllib.request.Request(url + suffix, data=message.encode() or None,
                                     method="POST" if message else "GET")
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = 200 <= r.status < 300
        print(f"ping{suffix or ' success'}: {'OK' if ok else 'FAILED'}")
        return ok

    def log(self, **fields) -> None:
        if self.dry_run:
            return
        self.state.mkdir(parents=True, exist_ok=True)
        with open(self.state / "runs.jsonl", "a") as fh:
            fh.write(json.dumps({"ts": now(), "trigger": "notify", **fields}, ensure_ascii=False) + "\n")


def after_run(n: Notifier) -> int:
    p = n.state / "last_run.json"
    if not p.exists():
        n.ping("/fail", "notify: no last_run.json, run_checks did not run")
        return 1
    last = json.loads(p.read_text())
    runs = n.state / "runs.jsonl"
    exit_code = None
    if runs.exists():
        for line in reversed(runs.read_text().splitlines()):
            rec = json.loads(line)
            if rec.get("ts") == last.get("ts") and rec.get("trigger") != "notify":
                exit_code = rec.get("exit")
                break
    items = alertable(last.get("findings", []))
    sent = n.email(subject_for(items), body_for(items, last)) if items else False
    if not items:
        print("no new P0/P1 findings and no new acta: no email")
    if exit_code == 3:
        pinged = n.ping("/fail", "run_checks: a check crashed; see ~/.lcp-qa/last_run.json")
    else:
        pinged = n.ping()
    n.log(alerts=len(items), emailed=sent, pinged=pinged)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sentinel email + healthchecks.io ping")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--test", action="store_true", help="send a test email and a success ping")
    g.add_argument("--alert", metavar="SUBJECT", help="send one email, no ping")
    g.add_argument("--fail", metavar="MESSAGE", help="ping the /fail endpoint with a message")
    g.add_argument("--check-smtp", action="store_true", help="log in to SMTP and out, send nothing")
    ap.add_argument("--body", default="", help="body for --alert")
    ap.add_argument("--dry-run", action="store_true", help="print instead of sending")
    ap.add_argument("--force", action="store_true", help="ignore the one-email-a-day rule")
    args = ap.parse_args(argv)

    n = Notifier(load_env(), state_dir(), dry_run=args.dry_run, force=args.force)
    if args.check_smtp:
        n.check_smtp()
        return 0
    if args.test:
        n.force = True
        n.email("[LCP] prueba de notify.py", f"Correo de prueba del sentinel, {now()}.\n"
                "Si lo lees, el canal de email funciona.")
        n.ping()
        return 0
    if args.alert:
        n.email(f"[LCP] {args.alert}", args.body or args.alert)
        n.log(alert=args.alert)
        return 0
    if args.fail:
        n.ping("/fail", args.fail)
        n.log(fail=args.fail)
        return 0
    return after_run(n)


if __name__ == "__main__":
    sys.exit(main())

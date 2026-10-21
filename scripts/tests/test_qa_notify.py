"""notify.py: what triggers an email, the subject line, and the one-email-a-day rule."""

import json

from qa import notify


def f(sev, new=True, key="", subject="2026-09-29", check="E1"):
    return {"fp": f"{check}-{sev}{key}", "check": check, "severity": sev, "subject": subject,
            "key": key, "message": "m", "new": new}


def test_only_new_p0_p1_or_new_acta_alert():
    items = [f("P0"), f("P1"), f("P2"), f("P3"), f("P1", new=False),
             f("P3", key="acta-published", check="S1"), f("P3", key="acta-pending", check="S1")]
    got = notify.alertable(items)
    assert [(i["severity"], i["key"]) for i in got] == [("P0", ""), ("P1", ""), ("P3", "acta-published")]


def test_subject():
    assert notify.subject_for([f("P1"), f("P1", key="acta-published", check="S1")]) == \
        "[LCP] P1×2 · acta nueva 2026-09-29"


def test_one_email_a_day(tmp_path, monkeypatch):
    sent = []

    class FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, msg):
            sent.append(msg["Subject"])

    n = notify.Notifier({"QA_SMTP_USER": "u", "QA_SMTP_PASS": "p"}, tmp_path)
    monkeypatch.setattr(n, "_smtp", lambda: FakeSMTP())
    assert n.email("a", "b") is True
    assert n.email("c", "d") is False
    n.force = True
    assert n.email("e", "f") is True
    assert sent == ["a", "e"]


def test_after_run_without_delta_only_pings(tmp_path):
    (tmp_path / "last_run.json").write_text(json.dumps({"ts": "t", "findings": [f("P2")]}))
    pings, mails = [], []
    n = notify.Notifier({}, tmp_path)
    n.ping = lambda suffix="", message="": pings.append(suffix) or True
    n.email = lambda s, b: mails.append(s) or True
    assert notify.after_run(n) == 0
    assert mails == [] and pings == [""]


def test_after_run_crash_pings_fail(tmp_path):
    (tmp_path / "last_run.json").write_text(json.dumps({"ts": "t", "findings": []}))
    (tmp_path / "runs.jsonl").write_text(json.dumps({"ts": "t", "trigger": "launchd", "exit": 3}) + "\n")
    pings = []
    n = notify.Notifier({}, tmp_path)
    n.ping = lambda suffix="", message="": pings.append(suffix) or True
    notify.after_run(n)
    assert pings == ["/fail"]

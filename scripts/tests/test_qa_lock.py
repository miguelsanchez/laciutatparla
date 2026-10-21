"""lock.py: with the lock held by hand, a job does not start and the attempt is logged."""

import json
import subprocess
import sys
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "qa" / "lock.py"


def test_job_does_not_start_while_lock_is_held(tmp_path):
    env = {"LCP_QA_STATE": str(tmp_path), "PATH": "/usr/bin:/bin"}
    holder = subprocess.Popen([sys.executable, str(LOCK), "hold"], env=env,
                              stdout=subprocess.PIPE, text=True)
    try:
        assert "holding" in holder.stdout.readline()
        marker = tmp_path / "ran"
        r = subprocess.run([sys.executable, str(LOCK), "--trigger", "launchd", "--",
                            "touch", str(marker)], env=env, capture_output=True, text=True)
        assert r.returncode == 75
        assert not marker.exists()
        rec = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])
        assert rec["trigger"] == "launchd" and rec["exit"] == "locked"
    finally:
        holder.terminate()
        holder.wait(timeout=10)
    r = subprocess.run([sys.executable, str(LOCK), "--", "touch", str(tmp_path / "ran")], env=env)
    assert r.returncode == 0 and (tmp_path / "ran").exists()


def test_pause_skips_the_command(tmp_path):
    (tmp_path / "PAUSE").touch()
    r = subprocess.run([sys.executable, str(LOCK), "--", "touch", str(tmp_path / "ran")],
                       env={"LCP_QA_STATE": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and not (tmp_path / "ran").exists()


def test_plist_template_never_bypasses_permissions():
    tmpl = LOCK.parent / "launchd" / "es.laciutatparla.qa.plist.tmpl"
    text = tmpl.read_text()
    for bad in ("dangerously", "bypass", "acceptEdits"):
        assert bad not in text
    assert "/Users/" not in text  # no machine paths in versioned files

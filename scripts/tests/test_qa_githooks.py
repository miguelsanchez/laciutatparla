"""Versioned git hooks: pre-push decisions."""

import subprocess
from pathlib import Path

import pytest

PRE_PUSH = Path(__file__).resolve().parents[1] / "qa" / "githooks" / "pre-push"
Z = "0" * 40


def push(remote, url, remote_ref, local_sha="abc"):
    line = f"refs/heads/x {local_sha} {remote_ref} {Z}\n"
    return subprocess.run(["bash", str(PRE_PUSH), remote, url], input=line,
                          capture_output=True, text=True).returncode


@pytest.mark.parametrize("remote,url,ref,code", [
    ("origin", "git@github-lcp-priv:miguelsanchez/laciutatparla-priv.git", "refs/heads/main", 1),
    ("origin", "git@github.com:miguelsanchez/laciutatparla-priv.git", "refs/heads/main", 1),
    ("priv", "git@github.com:miguelsanchez/laciutatparla-priv.git", "refs/heads/main", 1),
    ("public", "git@github-lcp-pub:miguelsanchez/laciutatparla.git", "refs/heads/main", 0),
    # fails closed: any other remote, or a push straight to a URL, is blocked on main
    ("backup", "git@example.com:someone/else.git", "refs/heads/main", 1),
    ("git@github-lcp-pub:miguelsanchez/laciutatparla.git",
     "git@github-lcp-pub:miguelsanchez/laciutatparla.git", "refs/heads/main", 1),
    ("origin", "git@github-lcp-priv:miguelsanchez/laciutatparla-priv.git", "refs/heads/qa/2026-10", 0),
    ("origin", "git@github-lcp-priv:miguelsanchez/laciutatparla-priv.git", "refs/heads/ingest/2026-09-29", 0),
])
def test_pre_push(remote, url, ref, code):
    assert push(remote, url, ref) == code


def test_pre_push_blocks_deleting_main():
    assert push("origin", "x", "refs/heads/main", local_sha=Z) == 1

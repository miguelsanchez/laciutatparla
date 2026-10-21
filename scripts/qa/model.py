"""Core types of the QA sentinel: findings, the check registry and the run context.

Design: meta/docs/arquitectura-agentes.md §5 (state) and §6.1 (finding format).
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent

SEVERITIES = ("P0", "P1", "P2", "P3")


@dataclass
class Finding:
    """One problem found by one check.

    The fingerprint depends only on check + subject + key, so the same problem
    keeps the same fp from run to run while it stays unchanged (§5).
    """

    check: str
    severity: str
    subject: str            # canonical subject: a pleno_id, iv_id, "file|figure"…
    message: str
    key: str = ""           # the value that makes it a distinct problem (e.g. the wrong figure)
    details: dict = field(default_factory=dict)
    subject_hash: str = ""  # content hash, for `until_changed` suppressions
    family: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.check}: unknown severity {self.severity!r}")

    @property
    def fp(self) -> str:
        raw = f"{self.check}|{self.subject}|{self.key}"
        return f"{self.check}-{hashlib.sha1(raw.encode()).hexdigest()[:10]}"

    @property
    def ref(self) -> str:
        """Human-readable form of what the fp hashes."""
        return "|".join(p for p in (self.check, self.subject, self.key) if p)

    def to_dict(self) -> dict:
        return {"fp": self.fp, "ref": self.ref, **asdict(self)}


@dataclass(frozen=True)
class Check:
    id: str
    family: str
    title: str
    fn: Callable[["Context"], Iterable[Finding]]
    network: bool = False
    fast: bool = False


REGISTRY: dict[str, Check] = {}


def check(id: str, *, family: str, title: str, network: bool = False, fast: bool = False):
    """Register a check function `fn(ctx) -> Iterable[Finding]`."""
    def deco(fn):
        if id in REGISTRY:
            raise ValueError(f"check {id} registered twice")
        REGISTRY[id] = Check(id, family, title, fn, network, fast)
        return fn
    return deco


def load_script(filename: str):
    """Import a pipeline script by file name (they start with digits). Only pure functions are used."""
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"_qa_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Context:
    """What a check may read. Everything comes from `data_dir`, so backtests can swap it."""

    def __init__(self, data_dir: Path, repo_root: Path = REPO_ROOT,
                 offline: bool = False, memory: dict | None = None) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.raw_dir = self.data_dir / "raw"
        self.texts_dir = self.raw_dir / "texts"
        self.pdfs_dir = self.raw_dir / "pdfs"
        self.corrections_dir = self.data_dir / "corrections"
        self.web_dir = self.repo_root / "web"
        self.offline = offline
        # Small values a check wants to compare with its previous run (e.g. index size).
        # Loaded from and saved to the state dir by run_checks; {} when running stateless.
        self.memory = memory if memory is not None else {}

    def _json(self, rel: str):
        p = self.data_dir / rel
        return json.loads(p.read_text()) if p.exists() else None

    @functools.cached_property
    def interventions_raw(self) -> list[dict]:
        return self._json("raw/interventions_raw.json") or []

    @functools.cached_property
    def intervencions(self) -> list[dict]:
        return self._json("intervencions.json") or []

    @functools.cached_property
    def entitats(self) -> list[dict]:
        return self._json("entitats.json") or []

    @functools.cached_property
    def sessions_index(self) -> list[dict]:
        return self._json("raw/sessions_index.json") or []

    @functools.cached_property
    def sessions_metadata(self) -> list[dict]:
        return self._json("raw/sessions_metadata.json") or []

    def corrections(self, name: str):
        import yaml
        p = self.corrections_dir / name
        return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None

    def text(self, pleno_id: str) -> str | None:
        p = self.texts_dir / f"{pleno_id}.txt"
        return p.read_text(errors="replace") if p.exists() else None


def state_dir() -> Path:
    """$LCP_QA_STATE, by default ~/.lcp-qa (outside git, §5)."""
    return Path(os.environ.get("LCP_QA_STATE") or Path.home() / ".lcp-qa").expanduser()

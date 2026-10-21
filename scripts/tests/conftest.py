"""Shared fixtures for the test suite."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).parent.parent
REPO_ROOT = SCRIPTS_DIR.parent
DATA_DIR = REPO_ROOT / "data"
CORRECTIONS_DIR = DATA_DIR / "corrections"
BASELINE_PATH = REPO_ROOT / "meta" / "qa" / "baseline.json"

# Add scripts/ to path so lib.* imports work inside tested modules
sys.path.insert(0, str(SCRIPTS_DIR))


def pytest_configure(config):
    # The pre-commit hook skips these (-m "not slow") to stay under its 20 s budget; /publish,
    # /apply-approved and a plain `pytest scripts/tests` run everything.
    config.addinivalue_line("markers", "slow: runs apply_merges or the agents' context on the full data/")
    # Skipped by the pre-commit hook too: a data PR commits a correction long before /apply-approved
    # regenerates the derived data it is checked against (a cession that changes the registered
    # entity, #90 and #100). /apply-approved runs them on the regenerated data, CI's check-derived
    # flags a PR whose derived data is stale, and a plain `pytest scripts/tests` runs them.
    config.addinivalue_line("markers", "derived: compares data/corrections/ with the derived data")


def _load_module(filename: str):
    """Load a script module by filename (handles leading digits)."""
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def mod_04():
    return _load_module("04_extract_text.py")


@pytest.fixture(scope="session")
def mod_05():
    return _load_module("05_parse_interventions.py")


@pytest.fixture(scope="session")
def intervencions():
    return json.loads((DATA_DIR / "intervencions.json").read_text())


@pytest.fixture(scope="session")
def entitats():
    return json.loads((DATA_DIR / "entitats.json").read_text())


@pytest.fixture(scope="session")
def entity_variant_map():
    return json.loads((DATA_DIR / "raw" / "entity_variant_map.json").read_text())


@pytest.fixture(scope="session")
def deletions():
    """data/corrections/deletions.yml — interventions/entities removed by apply_merges."""
    return yaml.safe_load((CORRECTIONS_DIR / "deletions.yml").read_text()) or {}


@pytest.fixture(scope="session")
def reassignments():
    """data/corrections/reassignments.yml — floor-cession re-attributions."""
    return yaml.safe_load((CORRECTIONS_DIR / "reassignments.yml").read_text()) or []


@pytest.fixture(scope="session")
def baseline():
    """meta/qa/baseline.json — accepted known issues, keyed by issue name."""
    return json.loads(BASELINE_PATH.read_text())


@pytest.fixture(scope="session")
def known_issue(baseline):
    """Return the set of ids accepted for a known issue in baseline.json."""
    def _ids(name: str) -> set[str]:
        return set(baseline["known_issues"][name]["ids"])
    return _ids


@pytest.fixture
def data_without_patches(tmp_path):
    """Return a data dir in tmp_path without any patches.yml entry for the given iv_ids.

    Tests that propose a patch for a real intervention must not depend on data/corrections/: once
    a real correction lands for that intervention, N7 rejects the proposal as a duplicate.
    corrections/ is copied, everything else linked, like the verifier's own overlay."""
    def _make(*iv_ids: str) -> Path:
        root = tmp_path / "data"
        root.mkdir()
        for child in DATA_DIR.iterdir():
            if child.name != "corrections":
                (root / child.name).symlink_to(child)
        (root / "corrections").mkdir()
        for f in CORRECTIONS_DIR.iterdir():
            if f.is_file():
                (root / "corrections" / f.name).write_bytes(f.read_bytes())
        patches = root / "corrections" / "patches.yml"
        ours = re.compile(r"- iv_id: ['\"]?(%s)['\"]?\n" % "|".join(map(re.escape, iv_ids)))
        blocks = re.split(r"(?m)^(?=- )", patches.read_text())
        patches.write_text("".join(b for b in blocks if not ours.match(b)))
        return root
    return _make

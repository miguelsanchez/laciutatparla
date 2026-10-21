"""
apply_merges.py refactor (arquitectura-agentes F2.1): the importable version must behave exactly
like the old top-level script.

Both run on their own copy of data/ under tmp_path, never on the real one. The old script is the
last version before the refactor, pinned by commit; it resolves data/ next to its own scripts/
directory, so it is copied into a fake repo layout.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.slow   # three full apply_merges runs

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OLD_SHA = "acf7cad2e02f913e8a2dbeff46075bc90573def5"   # last apply_merges.py before the refactor
OUTPUTS = ["raw/interventions_raw.json", "entitats.json", "raw/entity_variant_map.json"]
INPUTS = OUTPUTS + ["corrections"]


def _copy_data(dest: Path) -> Path:
    for rel in INPUTS:
        src = DATA / rel
        if src.is_dir():
            shutil.copytree(src, dest / rel)
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    return dest


def _inject_corrections(data: Path) -> None:
    """Exercise the branches the current data no longer hits (its deletions, text merges and
    manual inserts are already applied in interventions_raw.json): one correction of each kind,
    written identically into both copies."""
    import json
    ivs = json.loads((data / "raw/interventions_raw.json").read_text())
    a, b, c, d = ivs[10], ivs[11], ivs[12], ivs[20]
    corr = data / "corrections"

    def edit(name, fn):
        path = corr / name
        cur = yaml.safe_load(path.read_text()) or []
        path.write_text(yaml.safe_dump(fn(cur), allow_unicode=True, sort_keys=False))

    def add_deletions(cur):
        cur = dict(cur or {})
        cur["interventions"] = list(cur.get("interventions") or []) + [{"iv_id": c["id"]}]
        cur["entities"] = list(cur.get("entities") or []) + [{"entity_id": "golden-spurious"}]
        return cur

    edit("deletions.yml", add_deletions)
    edit("text_merges.yml", lambda cur: cur + [{"base_id": a["id"], "merge_ids": [b["id"], "missing-id"]},
                                               {"base_id": "missing-base", "merge_ids": [a["id"]]}])
    edit("manual_interventions.yml", lambda cur: cur + [dict(d, id="9999-01-01-001", entitat="Golden Spurious"),
                                                        dict(d, id="9999-01-01-002", entitat="Entitat Golden Nova")])
    edit("new_entities.yml", lambda cur: cur + [{"id": "entitat-golden-nova", "nom_cas": "Entidad Golden Nueva",
                                                 "nom_val": "Entitat Golden Nova", "tipus": "altres"}])
    edit("entity_merges.yml", lambda cur: cur + [{"canonical_id": "golden-sin-match", "nom_cas": "X", "nom_val": "X",
                                                  "tipus": "altres", "match_texts": ["texto que no existe"]}])


def _old_script() -> str:
    try:
        return subprocess.run(["git", "show", f"{OLD_SHA}:scripts/apply_merges.py"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip(f"commit {OLD_SHA[:7]} not available (shallow clone?)")


@pytest.fixture(scope="module", params=["current", "injected"])
def runs(request, tmp_path_factory):
    if not (DATA / "raw" / "interventions_raw.json").exists():
        pytest.skip("data/ not present")
    base = tmp_path_factory.mktemp(f"golden-{request.param}")
    prepare = _inject_corrections if request.param == "injected" else (lambda _d: None)

    old_repo = base / "old"
    prepare(_copy_data(old_repo / "data"))
    (old_repo / "scripts").mkdir()
    (old_repo / "scripts" / "apply_merges.py").write_text(_old_script())
    old = subprocess.run([sys.executable, "scripts/apply_merges.py"], cwd=old_repo,
                         capture_output=True, text=True)

    new_data = _copy_data(base / "new" / "data")
    prepare(new_data)
    new = subprocess.run([sys.executable, str(ROOT / "scripts" / "apply_merges.py"),
                          "--data-dir", str(new_data)], capture_output=True, text=True)
    return old_repo / "data", old, new_data, new


def test_both_succeed(runs):
    _, old, _, new = runs
    assert old.returncode == 0, old.stderr
    assert new.returncode == 0, new.stderr


@pytest.mark.parametrize("rel", OUTPUTS)
def test_outputs_identical_byte_for_byte(runs, rel):
    old_data, _, new_data, _ = runs
    assert (old_data / rel).read_bytes() == (new_data / rel).read_bytes(), rel


def test_log_identical(runs):
    _, old, _, new = runs
    assert old.stdout == new.stdout


def test_injected_scenario_hits_every_branch(runs):
    _, old, new_data, new = runs
    if "9999-01-01-001" not in (new_data / "corrections/manual_interventions.yml").read_text():
        pytest.skip("current-data scenario")
    for marker in ("MANUAL INSERT", "TEXT_MERGE", "WARNING: merge source", "WARNING: merge base",
                   "DELETE:", "DELETE (spurious entity", "WARNING: No entity IDs", "PATCH", "REASSIGN"):
        assert marker in new.stdout, marker


def test_dry_run_writes_nothing(tmp_path):
    if not (DATA / "raw" / "interventions_raw.json").exists():
        pytest.skip("data/ not present")
    data = _copy_data(tmp_path / "data")
    before = {rel: (data / rel).read_bytes() for rel in OUTPUTS}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "apply_merges.py"),
                        "--data-dir", str(data), "--dry-run"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "dry run: nothing written" in r.stdout
    assert {rel: (data / rel).read_bytes() for rel in OUTPUTS} == before


def test_importable_in_memory():
    """The verifier's path: load, override one correction file in memory, apply, no I/O."""
    if not (DATA / "raw" / "interventions_raw.json").exists():
        pytest.skip("data/ not present")
    sys.path.insert(0, str(ROOT / "scripts"))
    import apply_merges

    inputs = apply_merges.load_inputs(DATA)
    victim = inputs["interventions"][0]["id"]
    deletions = dict(inputs["deletions"])
    deletions["interventions"] = list(deletions.get("interventions") or []) + [{"iv_id": victim}]
    result = apply_merges.apply_corrections(apply_merges.load_inputs(DATA, {"deletions": deletions}),
                                            log=lambda *_: None)
    assert victim not in {iv["id"] for iv in result["interventions"]}

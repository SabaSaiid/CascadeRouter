"""Detect reproducibility drift without downloads, execution or lock substitution."""
import json
from pathlib import Path
import shutil

import pytest
from frontend.scripts.check_offline_inputs import audit, satisfies

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def test_current_lock_scripts_and_static_imports_are_consistent():
    result = audit()
    assert result["status"] == "consistent" and result["locked_packages"] == 121
    assert result["production_build_verified"] is False


@pytest.mark.parametrize("change,expected", [
    ("declaration", "root_contract_drift"), ("version", "locked_version_mismatch"),
    ("integrity", "missing_lock_integrity"), ("script", "script_contract_drift"),
    ("missing_import", "unresolved_relative_import"), ("remote", "remote_import"),
    ("undeclared", "undeclared_import"),
])
def test_offline_guard_detects_real_input_drift(tmp_path, change, expected):
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(FRONTEND / name, tmp_path / name)
    shutil.copytree(FRONTEND / "src", tmp_path / "src")
    package = json.loads((tmp_path / "package.json").read_text())
    lock = json.loads((tmp_path / "package-lock.json").read_text())
    if change == "declaration":
        package["devDependencies"]["typescript"] = "~5.0.0"
    elif change == "version":
        lock["packages"]["node_modules/vite"]["version"] = "8.0.0"
    elif change == "integrity":
        del lock["packages"]["node_modules/vite"]["integrity"]
    elif change == "script":
        package["scripts"]["test"] += " || true"
    elif change == "missing_import":
        (tmp_path / "src/services/api.ts").unlink()
    else:
        (tmp_path / "src/invalid.ts").write_text("import '" + ("https://external.invalid/module.js" if change == "remote" else "undeclared-provider") + "';\n")
    (tmp_path / "package.json").write_text(json.dumps(package))
    (tmp_path / "package-lock.json").write_text(json.dumps(lock))
    assert expected in audit(tmp_path)["errors"]


@pytest.mark.parametrize("version,spec,expected", [("8.3.5","^8.3.4",True),("6.0.3","~6.0.3",True),
    ("6.1.0","~6.0.3",False),("0.2.9","^0.2.3",True),("0.3.0","^0.2.3",False),
    ("0.0.4","^0.0.3",False),("19.3.0","^19.3.1",False),("8.3.5",">=8",False)])
def test_only_supported_ordinary_semver_ranges_establish_consistency(version, spec, expected):
    assert satisfies(version, spec) is expected

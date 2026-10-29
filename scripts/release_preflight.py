"""Offline prerequisite diagnostics only. Does not install, build or run targets."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

from frontend.scripts.check_offline_inputs import audit

ROOT = Path(__file__).resolve().parents[1]


def tool_version(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        value = result.stdout.strip().removeprefix("v")
        return value if result.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+", value) else None
    except (OSError, subprocess.SubprocessError):
        return None


def observe(root=ROOT):
    node = shutil.which("node")
    npm = shutil.which("npm")
    npm_script = Path(node).parent / "node_modules/npm/bin/npm-cli.js" if node else None
    if npm and not npm.lower().endswith(".cmd"):
        npm_script = Path(npm).resolve()
    versions = {"python": platform.python_version(), "node": tool_version([node, "--version"]) if node else None,
                "npm": tool_version([node, str(npm_script), "--version"]) if node and npm_script and npm_script.is_file() else None}
    packages = {}
    for name in ("fastapi", "uvicorn", "pydantic", "PyYAML", "pytest-cov"):
        try: packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name] = None
    locked = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))["packages"]
    declarations = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    missing = []
    for name in {**declarations["dependencies"], **declarations["devDependencies"]}:
        try: installed = json.loads((root / "frontend/node_modules" / name / "package.json").read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError): installed = None
        if installed != locked.get("node_modules/" + name, {}).get("version"):
            missing.append(name)
    bins = root / "frontend/node_modules/.bin"
    for name in ("tsc", "vite", "oxlint"):
        if not (bins / name).is_file() and not (bins / (name + ".cmd")).is_file():
            missing.append("bin:" + name)
    return {"versions": versions, "packages": packages, "frontend_missing_or_mismatched": sorted(missing), "inputs": audit(root / "frontend")}


def assess(observed, profile):
    checks = []
    def add(name, passed, required, remedy):
        checks.append(dict(id=name, status="passed" if passed else "blocked", required=required, remediation=remedy))
    versions = observed["versions"]
    python = tuple(map(int, versions["python"].split(".")[:2]))
    add("python_runtime", python == (3, 11) if profile != "backend" else python >= (3, 11), True,
        "Use an approved preinstalled Python 3.11 interpreter for release/CI; no interpreter is downloaded.")
    add("node_runtime", versions["node"] is not None and int(versions["node"].split(".")[0]) >= 24, profile != "backend",
        "Use an approved preinstalled Node 24+ runtime; Node client acceptance is separate from backend-only startup.")
    add("npm_runtime", versions["npm"] is not None and int(versions["npm"].split(".")[0]) >= 9, profile == "release",
        "Use an approved npm capable of lockfile v3; no package installation is performed here.")
    add("backend_package_presence", all(observed["packages"][name] for name in ("fastapi", "uvicorn", "pydantic", "PyYAML")), True,
        "Provision declared backend packages from an approved offline wheelhouse; presence is not clean resolution or compatibility proof.")
    add("static_frontend_inputs", observed["inputs"]["status"] == "consistent", True, "Review manifest, lock, script and import drift; do not substitute locked versions.")
    add("exact_frontend_installation", not observed["frontend_missing_or_mismatched"], profile == "release",
        "Provision required locked artifacts and install offline, then run typecheck, build and lint. Metadata/bin presence does not prove those commands passed.")
    add("optional_coverage_plugin", bool(observed["packages"]["pytest-cov"]), False, "Coverage is optional; no coverage result or threshold is claimed.")
    return {"profile": profile, "versions": versions, "package_versions": observed["packages"], "checks": checks,
            "frontend_missing_or_mismatched": observed["frontend_missing_or_mismatched"],
            "prerequisites_satisfied": all(c["status"] == "passed" for c in checks if c["required"]),
            "production_build_verified": False, "release_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("release", "backend", "ci-backend"), default="release")
    args = parser.parse_args()
    try: result = assess(observe(), args.profile)
    except (OSError, ValueError, KeyError, TypeError):
        result = {"prerequisites_satisfied": False, "error": "preflight_inputs_unavailable", "production_build_verified": False, "release_verified": False}
    print(json.dumps(result, sort_keys=True))
    return int(not result["prerequisites_satisfied"])


if __name__ == "__main__":
    raise SystemExit(main())

"""Static consistency check only; never installs packages or proves a Vite build."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = {"build": "tsc -b && vite build", "lint": "oxlint", "test": "node --test tests/*.test.mjs",
            "typecheck": "node scripts/typecheck.mjs"}


def satisfies(version, requirement):
    match = re.fullmatch(r"([~^]?)(\d+)\.(\d+)\.(\d+)", requirement)
    actual = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None or actual is None:
        return False  # Unsupported ranges cannot establish consistency.
    floor = tuple(map(int, match.groups()[1:]))
    value = tuple(map(int, actual.groups()))
    if not match[1]:
        return value == floor
    if match[1] == "~":
        ceiling = (floor[0], floor[1] + 1, 0)
    elif floor[0]:
        ceiling = (floor[0] + 1, 0, 0)
    elif floor[1]:
        ceiling = (0, floor[1] + 1, 0)
    else:
        ceiling = (0, 0, floor[2] + 1)
    return floor <= value < ceiling


def audit(frontend=ROOT / "frontend"):
    errors = set()
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    entries = lock.get("packages", {})
    original = entries.get("", {})
    if lock.get("lockfileVersion") != 3 or any(package.get(key) != original.get(key) for key in ("name", "version", "dependencies", "devDependencies")):
        errors.add("root_contract_drift")
    declared = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    for name, spec in declared.items():
        pinned = entries.get("node_modules/" + name, {})
        if not satisfies(pinned.get("version", ""), spec):
            errors.add("locked_version_mismatch")
    for name, entry in entries.items():
        if name and (not isinstance(entry.get("integrity"), str) or not entry["integrity"].startswith("sha512-")):
            errors.add("missing_lock_integrity")
    if any(package.get("scripts", {}).get(name) != command for name, command in COMMANDS.items()):
        errors.add("script_contract_drift")
    sources = sorted((frontend / "src").rglob("*.ts*"))
    for source in sources:
        for spec in re.findall(r"(?:from\s*|import\s*)['\"]([^'\"]+)['\"]", source.read_text(encoding="utf-8")):
            if spec.startswith(("http:", "https:", "//")):
                errors.add("remote_import")
            elif spec.startswith("."):
                path = source.parent / spec
                candidates = [path, *[Path(str(path) + suffix) for suffix in (".ts", ".tsx", ".js", "/index.ts", "/index.tsx")]]
                if not any(candidate.is_file() and candidate.resolve().is_relative_to(frontend.resolve()) for candidate in candidates):
                    errors.add("unresolved_relative_import")
            else:
                name = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if name not in declared:
                    errors.add("undeclared_import")
    return {"status": "consistent" if not errors else "invalid", "errors": sorted(errors),
            "locked_packages": max(0, len(entries) - 1), "source_files": len(sources), "production_build_verified": False}


if __name__ == "__main__":
    try:
        result = audit()
    except (OSError, ValueError, TypeError, KeyError):
        result = {"status": "invalid", "errors": ["unreadable_input"], "production_build_verified": False}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "consistent" else 1)

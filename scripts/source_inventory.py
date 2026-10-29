"""Hash selected committed source blobs, never a target repository or built package."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/source-inventory.json"
PREFIXES = ("backend/", "frontend/src/", "frontend/scripts/")
FILES = {"requirements.txt", "frontend/package.json", "frontend/package-lock.json", "frontend/index.html",
         "frontend/vite.config.ts", "frontend/tsconfig.json", "frontend/tsconfig.app.json", "frontend/tsconfig.node.json"}


def allowed(path):
    pure = PurePosixPath(path)
    return (bool(path) and not pure.is_absolute() and not any(part in {".", ".."} or part.startswith(".") for part in pure.parts)
            and ":" not in path and "\\" not in path and (path in FILES or path.startswith(PREFIXES))
            and pure.suffix in {".py", ".ts", ".tsx", ".mjs", ".css", ".svg", ".json", ".html", ".txt"})


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def snapshot(revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("invalid_revision")
    names = git("ls-tree", "-rz", "--name-only", revision).decode("utf-8").split("\0")
    artifacts = []
    for name in sorted(path for path in names if allowed(path)):
        raw = git("cat-file", "blob", revision + ":" + name)
        artifacts.append(dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    return artifacts


def valid_entries(entries):
    return (bool(entries) and len({item["path"] for item in entries}) == len(entries)
            and all(allowed(item["path"]) and type(item.get("bytes")) is int and item["bytes"] >= 0
                    and re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) for item in entries))


def verify(value):
    if (value.get("schema_version") != "cascaderouter.source-inventory.v1" or value.get("version") is not None
            or not re.fullmatch(r"[0-9a-f]{40}", value.get("source_commit", "")) or not valid_entries(value.get("artifacts", []))):
        raise ValueError("invalid_manifest")
    current = git("rev-parse", "HEAD").decode().strip()
    git("merge-base", "--is-ancestor", value["source_commit"], current)
    scoped = ["backend", "frontend/src", "frontend/scripts", *sorted(FILES)]
    if git("status", "--porcelain=v1", "--untracked-files=all", "--", *scoped).strip():
        raise ValueError("uncommitted_source_changes")
    if value["artifacts"] != snapshot(value["source_commit"]) or value["artifacts"] != snapshot(current):
        raise ValueError("source_inventory_mismatch")
    return {"source_inventory_verified": True, "artifacts": len(value["artifacts"]),
            "canonical_source_bytes": sum(item["bytes"] for item in value["artifacts"]), "production_build_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write the verified committed-source inventory to its fixed docs path")
    args = parser.parse_args()
    try:
        if args.write:
            head = git("rev-parse", "HEAD").decode().strip()
            value = {"schema_version": "cascaderouter.source-inventory.v1", "version": None, "source_commit": head,
                     "scope": "Selected tracked runtime/frontend/contract/build inputs; canonical Git blob bytes, not a built distribution or target-source snapshot",
                     "artifacts": snapshot(head)}
        else:
            value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        result = verify(value)
        if args.write:
            MANIFEST.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print(json.dumps({"source_inventory_verified": False, "error": "source_inventory_unavailable_or_mismatched", "production_build_verified": False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

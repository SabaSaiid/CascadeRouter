"""Credential-free subprocess sandbox shared by prompt capture and regression runs.

Guarantees: the target repository is copied into a fresh temp directory, the
child process gets a minimal environment (no API keys or host secrets), runs in
its own process group, and is killed (with its children) on timeout.
This is credential isolation, not an OS-level jail.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

MAX_OUTPUT_BYTES = 1024 * 1024
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".hg", ".svn", "venv", ".venv", "node_modules", "__pycache__", "*.pyc",
    ".pytest_cache", ".mypy_cache", ".tox", ".env", ".env.*",
)


@dataclass(frozen=True)
class ProcessResult:
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool


def scrubbed_env(home: Path) -> dict[str, str]:
    """Minimal environment: nothing from the host except PATH and locale."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "CASCADE_OFFLINE": "1",
    }
    for key in ("LANG", "LC_ALL", "SYSTEMROOT"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


@contextmanager
def sandbox_copy(repo_root: Path, prefix: str = "temp_patch_") -> Iterator[Path]:
    """Copy `repo_root` into a fresh temp dir; always removed afterwards."""
    base = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        work = base / "repo"
        shutil.copytree(repo_root, work, symlinks=True, ignore=_COPY_IGNORE)
        (base / "home").mkdir()
        yield work
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _read_tail(fh) -> str:
    """Read a captured stream, keeping the *end* (result lines and summaries live there)."""
    fh.seek(0, os.SEEK_END)
    size = fh.tell()
    fh.seek(max(0, size - MAX_OUTPUT_BYTES))
    data = fh.read()
    if size > MAX_OUTPUT_BYTES:
        data = b"[output truncated]\n" + data
    return data.decode("utf-8", errors="replace")


def run_python(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
    stdin: str = "",
    home: Optional[Path] = None,
) -> ProcessResult:
    """Run `python <args>` with the backend interpreter in a scrubbed environment.

    Output goes to temp files, not pipes, and we wait on the process itself, so
    background helpers that inherit stdout can neither hang us nor turn a
    finished run into a false timeout.
    """
    env = scrubbed_env(home or cwd.parent / "home")
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as inp:
        inp.write(stdin.encode("utf-8"))
        inp.seek(0)
        proc = subprocess.Popen(
            [sys.executable, *args],
            cwd=cwd,
            env=env,
            stdin=inp,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        # Always reap the whole process group (stray helpers included).
        _kill_group(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL is not ignorable
            pass
        return ProcessResult(
            None if timed_out else proc.returncode, _read_tail(out), _read_tail(err), timed_out
        )


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass

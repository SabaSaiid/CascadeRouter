"""Run the target repository's own test suite against the patched code.

The repo is copied to a temp sandbox, patched files and the policy are written,
the CascadeRouter runtime is vendored as `cascaderouter.py`, and `pytest` runs
with a scrubbed environment (no API keys) and a hard timeout. A patch is only
"verified" when the suite actually ran and every test passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.compiler.patch_generator import RUNTIME_MODULE, PatchSet
from backend.compiler.policy_generator import POLICY_FILENAME
from backend.compiler.sandbox import run_python, sandbox_copy

RUNTIME_SOURCE = Path(__file__).resolve().parent.parent / "runtime" / "cascade_router.py"

# pytest exit codes: 0 ok, 1 tests failed, 2 interrupted, 3 internal, 4 usage, 5 no tests
_NO_TESTS = 5
_RESULT_RE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(\S+)", re.M)
# Matches both "6 passed in 0.12s" (-q) and "==== 1 failed, 5 passed in 0.3s ====".
_SUMMARY_RE = re.compile(
    r"^(?:=+ )?((?:\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected)(?:, )?)+"
    r" in [\d.]+s(?: \([^)]*\))?|no tests ran in [\d.]+s)(?: =+)?$",
    re.M,
)
MAX_LOG_CHARS = 20_000


@dataclass
class RegressionResult:
    passed: bool
    summary: str
    log: str
    outcomes: dict[str, str] = field(default_factory=dict)  # test id -> PASSED/FAILED/...
    timed_out: bool = False

    def log_for(self, function_name: Optional[str]) -> str:
        """Test outcomes most relevant to a node, falling back to the overall summary."""
        tokens = [t for t in (function_name or "").lower().split("_") if len(t) > 3]
        lines = [
            f"{test} {outcome}"
            for test, outcome in self.outcomes.items()
            if tokens and any(t in test.lower() for t in tokens)
        ]
        return "\n".join(lines) if lines else self.summary


def parse_pytest_output(stdout: str) -> tuple[dict[str, str], str]:
    outcomes = {test: outcome for outcome, test in _RESULT_RE.findall(stdout)}
    summaries = _SUMMARY_RE.findall(stdout)
    return outcomes, (summaries[-1].strip() if summaries else "")


def run_regression(
    repo_root: Path,
    patches: PatchSet,
    policy_text: str,
    timeout: float,
) -> RegressionResult:
    with sandbox_copy(repo_root, prefix="temp_patch_") as work:
        for path, file_patch in patches.files.items():
            target = (work / path).resolve()
            if work.resolve() not in target.parents:
                return RegressionResult(False, "refused to write outside the sandbox", f"bad path {path}")
            target.write_text(file_patch.patched, encoding="utf-8")
        (work / POLICY_FILENAME).write_text(policy_text, encoding="utf-8")
        (work / f"{RUNTIME_MODULE}.py").write_text(RUNTIME_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        proc = run_python(
            ["-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", "--color=no"],
            cwd=work,
            timeout=timeout,
        )

    log = (proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else ""))[-MAX_LOG_CHARS:]
    if proc.timed_out:
        return RegressionResult(False, f"regression suite timed out after {timeout:g}s", log, timed_out=True)
    outcomes, summary = parse_pytest_output(proc.stdout)
    if proc.returncode == _NO_TESTS:
        return RegressionResult(False, "no tests were collected; patch is unverified", log, outcomes)
    passed = proc.returncode == 0 and bool(outcomes) and all(
        o in ("PASSED", "SKIPPED", "XFAIL") for o in outcomes.values()
    )
    if not summary:
        summary = f"pytest exited with code {proc.returncode}"
    return RegressionResult(passed, summary, log, outcomes)

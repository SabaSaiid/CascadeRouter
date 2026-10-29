"""Local failure/error/skip reporting evidence; no hosted CI success is implied."""
from pathlib import Path
import subprocess
import sys

import pytest
from scripts.summarize_tests import counts_from_report, render_summary


def test_nested_report_counts_actual_cases_without_double_counting(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text('<testsuites><testsuite tests="5"><testcase/><testcase><failure/></testcase><testsuite><testcase><error/></testcase><testcase><skipped/></testcase><testcase><skipped/></testcase></testsuite></testsuite></testsuites>')
    assert counts_from_report(path) == dict(tests=5, passed=1, failures=1, errors=1, skipped=2)
    text, code = render_summary(path, "failure", "Backend")
    assert "| 5 | 1 | 1 | 1 | 2 |" in text and "`failure`" in text and code == 0


@pytest.mark.parametrize("data", [None, "<broken", "<other/>", '<!DOCTYPE data><testsuites/>', '<testsuite><testcase><failure/><error/></testcase></testsuite>'])
@pytest.mark.parametrize("outcome,code", [("success", 1), ("failure", 0)])
def test_missing_invalid_or_ambiguous_reports_never_invent_passing_counts(tmp_path, data, outcome, code):
    path = tmp_path / "report.xml"
    if data is not None:
        path.write_text(data)
    text, actual = render_summary(path, outcome, "Frontend")
    assert actual == code and "unavailable or invalid" in text and "| Passed |" not in text


def test_successful_step_with_failed_cases_is_reported_as_contradiction(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text('<testsuite><testcase><failure/></testcase></testsuite>')
    text, code = render_summary(path, "success", "Frontend")
    assert code == 1 and "contradicts" in text and "| 1 | 0 | 1 | 0 | 0 |" in text


def test_real_summary_cli_appends_without_hiding_failed_step_outcome(tmp_path):
    source = tmp_path / "report.xml"
    output = tmp_path / "summary.md"
    source.write_text('<testsuite><testcase/></testsuite>')
    output.write_text("Earlier job evidence\n")
    script = Path(__file__).resolve().parents[2] / "scripts/summarize_tests.py"
    completed = subprocess.run([sys.executable, "-B", str(script), "--report", str(source), "--outcome", "failure", "--label", "Backend", "--output", str(output)], capture_output=True, text=True)
    assert completed.returncode == 0
    assert output.read_text().startswith("Earlier job evidence\n")
    assert "`failure`" in output.read_text() and "| 1 | 1 | 0 | 0 | 0 |" in output.read_text()

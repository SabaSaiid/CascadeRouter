"""Report observed JUnit cases without replacing the test command's exit status."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def counts_from_report(path):
    raw = path.read_bytes()
    if len(raw) > 8 * 1024 * 1024 or b"<!DOCTYPE" in raw.upper():
        raise ValueError("unsupported_report")
    root = ET.fromstring(raw)
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("unsupported_report")
    counts = dict(tests=0, passed=0, failures=0, errors=0, skipped=0)
    for case in root.iter("testcase"):
        counts["tests"] += 1
        kinds = [key for key, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")) if case.find(tag) is not None]
        if len(kinds) > 1:
            raise ValueError("ambiguous_case")
        counts[kinds[0] if kinds else "passed"] += 1
    return counts


def render_summary(path, outcome, label):
    if label not in {"Backend", "Frontend"} or outcome not in {"success", "failure", "cancelled", "skipped", "not run"}:
        raise ValueError("unsupported_summary")
    text = f"### {label} tests\n\nTest step outcome: `{outcome}`.\n\n"
    try:
        counts = counts_from_report(path)
    except (OSError, ValueError, ET.ParseError):
        return text + "JUnit report unavailable or invalid. No passing counts can be established; inspect the original job logs.\n", int(outcome == "success")
    text += "| Reported tests | Passed | Failures | Errors | Skipped |\n| ---: | ---: | ---: | ---: | ---: |\n"
    text += "| {tests} | {passed} | {failures} | {errors} | {skipped} |\n".format(**counts)
    text += "\nThese are reported cases, not a substitute for the test step outcome. See original logs for skip reasons and failure details.\n"
    contradictory = outcome == "success" and counts["failures"] + counts["errors"] > 0
    if contradictory:
        text += "\nThe successful step outcome contradicts failing report cases; inspect the job.\n"
    return text, int(contradictory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--outcome", default="not run", choices=("success", "failure", "cancelled", "skipped", "not run", ""))
    parser.add_argument("--label", required=True, choices=("Backend", "Frontend"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    text, status = render_summary(args.report, args.outcome or "not run", args.label)
    try:
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(text)
    except OSError:
        print("Test summary output unavailable.")
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())

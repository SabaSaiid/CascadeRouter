import pytest

from backend.compiler.cases import CASES_FILENAME, BenchmarkCase, CasesError, load_cases, parse_cases
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def test_sample_repo_cases():
    cases = load_cases(SAMPLE)
    assert set(cases) == {
        "node_classify_customer_intent",
        "node_extract_ticket_metadata",
        "node_generate_support_resolution",
    }
    assert len(cases["node_classify_customer_intent"]) == 3
    first = cases["node_classify_customer_intent"][0]
    assert first.expected == {"category": "billing"}
    assert "charged twice" in first.vars["query"]
    synth = cases["node_generate_support_resolution"][0]
    assert synth.must_include == ["1.", "2."]
    assert (synth.min_chars, synth.max_chars) == (80, 4000)
    assert synth.vars["intent"] == {"category": "tech_support"}


def test_missing_file_means_no_cases(tmp_path):
    assert load_cases(tmp_path) == {}


def test_empty_file(tmp_path):
    (tmp_path / CASES_FILENAME).write_text("")
    assert load_cases(tmp_path) == {}


def test_invalid_yaml(tmp_path):
    (tmp_path / CASES_FILENAME).write_text("a: [unclosed")
    with pytest.raises(CasesError, match="not valid YAML"):
        load_cases(tmp_path)


def test_symlinked_cases_file_ignored(tmp_path):
    real = tmp_path / "real.yaml"
    real.write_text("n: [{vars: {}}]")
    (tmp_path / CASES_FILENAME).symlink_to(real)
    assert load_cases(tmp_path) == {}


def test_defaults():
    assert parse_cases({"n": [{}]}) == {"n": [BenchmarkCase(vars={})]}


@pytest.mark.parametrize(
    "data,msg",
    [
        ([], "top level"),
        ({"n": []}, "non-empty list"),
        ({"n": "x"}, "non-empty list"),
        ({1: [{}]}, "invalid node id"),
        ({"n": ["x"]}, "must be a mapping"),
        ({"n": [{"bogus": 1}]}, "unknown keys"),
        ({"n": [{"vars": [1]}]}, "vars"),
        ({"n": [{"vars": {"client": 1}}]}, "injected"),
        ({"n": [{"must_include": "x"}]}, "list of non-empty strings"),
        ({"n": [{"must_include": [""]}]}, "list of non-empty strings"),
        ({"n": [{"min_chars": -1}]}, "non-negative"),
        ({"n": [{"max_chars": True}]}, "non-negative"),
        ({"n": [{"min_chars": 5, "max_chars": 2}]}, "min_chars > max_chars"),
        ({"n": [{}] * 21}, "at most"),
    ],
)
def test_parse_errors(data, msg):
    with pytest.raises(CasesError, match=msg):
        parse_cases(data)

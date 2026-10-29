"""Fails when backend/schemas.py drifts from frontend/src/types.ts."""

import re

import pytest

from backend import schemas
from backend.config import REPO_ROOT, load_settings

TYPES_TS = (REPO_ROOT / "frontend" / "src" / "types.ts").read_text()

MIRRORED = [
    "LLMNode", "ScanResult", "BenchmarkMetric", "NodeBenchmarkResult",
    "BenchmarkRun", "OptimizationDecision", "OptimizeResult", "ModelTierConfig",
]


def _ts_fields(interface: str) -> dict[str, bool]:
    """Return {field_name: is_optional} for a TS interface."""
    match = re.search(rf"export interface {interface} \{{(.*?)\n\}}", TYPES_TS, re.S)
    assert match, f"interface {interface} not found in types.ts"
    fields = {}
    for name, optional in re.findall(r"^\s+(\w+)(\??):", match.group(1), re.M):
        fields[name] = optional == "?"
    return fields


@pytest.mark.parametrize("name", MIRRORED)
def test_field_names_and_optionality_match(name):
    ts = _ts_fields(name)
    model = getattr(schemas, name)
    assert set(model.model_fields) == set(ts), name
    for field, optional in ts.items():
        assert (not model.model_fields[field].is_required()) == optional or field == "validation_errors", (
            f"{name}.{field}: optionality differs"
        )


def test_literal_unions_match():
    for alias, py in (("DataSourceMode", schemas.DataSourceMode), ("ModelTier", schemas.ModelTier)):
        ts_values = re.search(rf"export type {alias} = (.*?);", TYPES_TS).group(1)
        assert set(re.findall(r"'(\w+)'", ts_values)) == set(py.__args__)


def test_catalog_matches_frontend_catalog():
    ts_ids = re.findall(r"id: '([^']+)'", TYPES_TS)
    ts_prices = [float(p) for p in re.findall(r"PricePerM: ([\d.]+)", TYPES_TS)]
    s = load_settings()
    assert [m.id for m in s.models] == ts_ids
    assert [p for m in s.models for p in (m.input_price_per_m, m.output_price_per_m)] == ts_prices

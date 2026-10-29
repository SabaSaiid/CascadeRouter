"""Fails when backend/schemas.py drifts from frontend/src/types.ts."""

import re
import typing

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


_PRIMITIVES = {"string": {str}, "number": {int, float}, "boolean": {bool}}


def _ts_types(interface: str) -> dict[str, str]:
    match = re.search(rf"export interface {interface} \{{(.*?)\n\}}", TYPES_TS, re.S)
    return {n: t.strip() for n, t in re.findall(r"^\s+(\w+)\??:\s*([^;]+);", match.group(1), re.M)}


def _resolve_alias(ts_type: str) -> str:
    alias = re.search(rf"export type {re.escape(ts_type)} = (.*?);", TYPES_TS)
    return alias.group(1).strip() if alias else ts_type


def _py_leaf_types(annotation) -> set:
    """Flatten Optional/Union and return the leaf python types or Literal values."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        out = set()
        for arg in typing.get_args(annotation):
            if arg is not type(None):
                out |= _py_leaf_types(arg)
        return out
    if origin is typing.Literal:
        return {("literal", v) for v in typing.get_args(annotation)}
    return {annotation}


@pytest.mark.parametrize("name", MIRRORED)
def test_literal_and_primitive_types_match(name):
    model = getattr(schemas, name)
    for field, ts_type in _ts_types(name).items():
        resolved = _resolve_alias(ts_type)
        py = _py_leaf_types(model.model_fields[field].annotation)
        literals = re.findall(r"'([^']+)'", resolved)
        if literals and re.fullmatch(r"(\s*'[^']+'\s*\|?)+", resolved):
            assert py == {("literal", v) for v in literals}, f"{name}.{field}: {resolved} vs {py}"
        elif resolved in _PRIMITIVES:
            assert py and py <= _PRIMITIVES[resolved] | {int}, f"{name}.{field}: {resolved} vs {py}"
            if resolved == "number":
                assert bool not in py

import math

import pytest

from backend.compiler.metrics import (
    aggregate_totals,
    cost_savings_pct,
    estimate_cost,
    estimate_tokens,
    latency_reduction_pct,
    percentile,
    reduction_pct,
    summarize_latencies,
)
from backend.config import load_settings


@pytest.fixture
def catalog():
    return {m.tier + ("_alt" if "Lightning" in m.id else ""): m for m in load_settings().models}


def test_estimate_cost_formula(catalog):
    # 312 in / 48 out on Nano: 312e-6*0.06 + 48e-6*0.24
    assert estimate_cost(catalog["efficient"], 312, 48) == pytest.approx(0.00003024)
    # 840 in / 345 out on Ultra
    assert estimate_cost(catalog["powerful"], 840, 345) == pytest.approx(0.001875)
    assert estimate_cost(catalog["balanced"], 0, 0) == 0.0
    assert estimate_cost(catalog["powerful"], 1_000_000, 1_000_000) == pytest.approx(4.0)


def test_estimate_cost_rejects_negative(catalog):
    with pytest.raises(ValueError):
        estimate_cost(catalog["efficient"], -1, 0)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


@pytest.mark.parametrize(
    "base,opt,expected",
    [
        (100, 25, 75.0),
        (100, 100, 0.0),
        (100, 150, -50.0),
        (0, 10, None),
        (-5, 1, None),
        (None, 1, None),
        (1, None, None),
        (math.nan, 1, None),
        (math.inf, 1, None),
    ],
)
def test_reduction_pct(base, opt, expected):
    result = reduction_pct(base, opt)
    assert result == (pytest.approx(expected) if expected is not None else None)
    assert cost_savings_pct(base, opt) == result
    assert latency_reduction_pct(base, opt) == result


def test_percentile_matches_linear_interpolation():
    vals = [10, 20, 30, 40]
    assert percentile(vals, 0) == 10
    assert percentile(vals, 100) == 40
    assert percentile(vals, 50) == 25
    assert percentile(vals, 95) == pytest.approx(38.5)
    assert percentile([7], 95) == 7
    assert percentile([3, 1, 2], 50) == 2  # unsorted input


@pytest.mark.parametrize("vals,p", [([], 50), ([1], -1), ([1], 101)])
def test_percentile_errors(vals, p):
    with pytest.raises(ValueError):
        percentile(vals, p)


def test_summarize_latencies():
    s = summarize_latencies([100, 200, 300])
    assert (s.median_ms, s.mean_ms, s.samples) == (200, 200, 3)
    assert s.p95_ms == pytest.approx(290)
    with pytest.raises(ValueError):
        summarize_latencies([])
    with pytest.raises(ValueError):
        summarize_latencies([1, -2])


def test_aggregate_totals():
    t = aggregate_totals([(0.000456, 0.00003024, 1145, 138), (0.00075, 0.00004992, 1310, 125)])
    assert t.total_baseline_cost_usd == pytest.approx(0.001206)
    assert t.total_optimized_cost_usd == pytest.approx(0.00008016)
    assert t.total_cost_reduction_pct == pytest.approx((0.001206 - 0.00008016) / 0.001206 * 100)
    expected_lat = ((1145 - 138) / 1145 * 100 + (1310 - 125) / 1310 * 100) / 2
    assert t.avg_latency_reduction_pct == pytest.approx(expected_lat)


def test_aggregate_totals_undefined_is_none_not_zero():
    t = aggregate_totals([])
    assert t.total_baseline_cost_usd == 0
    assert t.total_cost_reduction_pct is None and t.avg_latency_reduction_pct is None
    t = aggregate_totals([(0.0, 0.5, 100, 50)])
    assert t.total_cost_reduction_pct is None
    assert t.avg_latency_reduction_pct == pytest.approx(50.0)


@pytest.mark.parametrize("item", [(-1, 0, 1, 1), (1, math.nan, 1, 1), (1, 1, math.inf, 1)])
def test_aggregate_totals_rejects_bad_values(item):
    with pytest.raises(ValueError):
        aggregate_totals([item])

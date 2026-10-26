// ==============================================================================
// CascadeRouter IDE – Derived Metrics Utilities
// All display calculations live here so they are unit-testable.
// ==============================================================================

/**
 * Compute cost savings percentage.
 * Returns null when baseline is missing or zero (never shows "0" as a fake value).
 */
export function costSavingsPct(
  baselineCost: number | undefined | null,
  optimizedCost: number | undefined | null,
): number | null {
  if (baselineCost == null || optimizedCost == null) return null;
  if (baselineCost === 0) return null;
  return 100 * (baselineCost - optimizedCost) / baselineCost;
}

/**
 * Format a cost value as a $-prefixed string with appropriate decimal places.
 * Unknown values render as an em-dash, never 0.
 */
export function fmtCost(value: number | undefined | null, places = 6): string {
  if (value == null) return '—';
  return `$${value.toFixed(places)}`;
}

/**
 * Format a percentage with a sign prefix, e.g. "-79.3%".
 * Unknown values render as an em-dash.
 */
export function fmtPct(value: number | undefined | null, sign = true): string {
  if (value == null) return '—';
  const prefix = sign && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(1)}%`;
}

/**
 * Format latency in ms. Unknown → em-dash.
 */
export function fmtMs(value: number | undefined | null): string {
  if (value == null) return '—';
  return `${value} ms`;
}

/**
 * Compute the summed baseline cost across all decisions in a run.
 */
export function totalBaselineCost(
  decisions: Array<{ baseline_cost_usd: number }>,
): number {
  return decisions.reduce((acc, d) => acc + d.baseline_cost_usd, 0);
}

/**
 * Compute the summed optimised cost across all decisions.
 */
export function totalOptimizedCost(
  decisions: Array<{ optimized_cost_usd: number }>,
): number {
  return decisions.reduce((acc, d) => acc + d.optimized_cost_usd, 0);
}

/**
 * Return a human-readable short name from a full Nemotron model ID.
 */
export function shortModelName(modelId: string): string {
  const last = modelId.split('/').pop() ?? modelId;
  // e.g. "NVIDIA-Nemotron-3-Nano-30B-A3B" → "Nano"
  if (/nano/i.test(last)) return 'Nano';
  if (/lightning/i.test(last)) return 'Lightning';
  if (/super/i.test(last)) return 'Super';
  if (/ultra/i.test(last)) return 'Ultra';
  return last;
}

/**
 * Generate the per-row verdict sentence from benchmark data.
 */
export function verdictSentence(
  nodeName: string,
  modelMetrics: Array<{
    name: string;
    passes: boolean;
    cost: number;
    quality: number;
    latency: number;
  }>,
  recommendedName: string | null,
  qualityThreshold: number,
): string {
  const passing = modelMetrics.filter((m) => m.passes);
  const failing = modelMetrics.filter((m) => !m.passes);

  if (passing.length === 0) {
    return `No tier passes the quality threshold of ${qualityThreshold} for ${nodeName}.`;
  }

  // Sort passing by cost ascending
  const sorted = [...passing].sort((a, b) => a.cost - b.cost);
  const cheapest = sorted[0];
  const ultraMetric = modelMetrics.find((m) => /ultra/i.test(m.name));

  if (failing.length > 0) {
    const failNames = failing.map((m) => m.name).join(' and ');
    if (sorted.length === 1) {
      return `${failNames} fail the quality check, so ${cheapest.name} is the cheapest passing tier.`;
    }
  }

  if (cheapest && ultraMetric) {
    const savings = costSavingsPct(ultraMetric.cost, cheapest.cost);
    if (savings != null && Math.abs(savings) >= 1) {
      return `${cheapest.name} is the cheapest tier that passes (quality ${cheapest.quality.toFixed(2)} ≥ ${qualityThreshold}). Saves ${savings.toFixed(0)}% vs Ultra.`;
    }
  }

  // Tie-break on latency
  if (sorted.length >= 2) {
    const first = sorted[0];
    const second = sorted[1];
    const costDiffPct = Math.abs((second.cost - first.cost) / first.cost) * 100;
    if (costDiffPct < 2) {
      return `${first.name} and ${second.name} are within 2% on cost; ${first.latency < second.latency ? first.name : second.name} chosen for lower latency.`;
    }
  }

  return recommendedName
    ? `${recommendedName} is the recommended tier for ${nodeName}.`
    : `${cheapest.name} is the recommended tier for ${nodeName}.`;
}

/**
 * Presentation helpers for the new workbench UI.
 * All functions are pure and free of hard-coded model names.
 * Unknown / unavailable values always return an em dash, never 0.
 */
import type { Job, Optimization, Scan, Backend_RoutingDecision as Decision, Health } from './contracts.ts';
import type { Backend_OptimizationCandidate as Candidate } from './contracts.ts';

// ---------------------------------------------------------------------------
// Model name
// ---------------------------------------------------------------------------

/**
 * Strip a vendor prefix (anything before and including the first "/") to yield
 * a readable short name.  Falls back to the full ID.
 *
 * Examples:
 *   "nvidia/NVIDIA-Nemotron-3-Nano-3B-A3B" → "NVIDIA-Nemotron-3-Nano-3B-A3B"
 *   "meta-llama/Meta-Llama-3.1-70B-Instruct" → "Meta-Llama-3.1-70B-Instruct"
 *   "nemotron-nano" → "nemotron-nano"
 */
export function shortModelName(modelId: string): string {
  const slash = modelId.indexOf('/');
  return slash !== -1 ? modelId.slice(slash + 1) : modelId;
}

// ---------------------------------------------------------------------------
// Cost bar
// ---------------------------------------------------------------------------

/**
 * Returns a 0–100 percentage for an inline cost bar scaled to the most
 * expensive row in the table.
 *
 * @param costUsd   The cost string for this row (e.g. "0.000459")
 * @param maxCostUsd  The maximum cost across all rows in the table
 * @returns 0–100 number, or 0 when either value is unavailable
 */
export function costBarScale(
  costUsd: string | null | undefined,
  maxCostUsd: string | null | undefined,
): number {
  if (!costUsd || !maxCostUsd) return 0;
  const c = parseFloat(costUsd);
  const m = parseFloat(maxCostUsd);
  if (!isFinite(c) || !isFinite(m) || m === 0) return 0;
  return Math.min(100, Math.round((c / m) * 1000) / 10);
}

// ---------------------------------------------------------------------------
// Savings sentence
// ---------------------------------------------------------------------------

export interface SavingsSentenceInput {
  decision: Decision;
  /** All candidates including baseline (from decision.candidates) */
  candidates: readonly Candidate[];
  /** The model ID chosen by the backend */
  selectedModelId: string | null | undefined;
  /** Baseline model ID */
  baselineModelId: string;
}

/** Returns one generated sentence summarising the cheapest passing model,
 *  the saving vs baseline, and any close alternative.  Never hard-codes names.
 *  Returns an em dash when data is unavailable. */
export function savingsSentence(input: SavingsSentenceInput): string {
  const { decision, candidates, selectedModelId, baselineModelId } = input;
  if (!selectedModelId) return '—';

  const selected = candidates.find(c => c.model.identifier === selectedModelId);
  const baseline = candidates.find(c => c.model.identifier === baselineModelId);

  const selectedCost = selected?.cost_total_usd ? parseFloat(selected.cost_total_usd) : null;
  const baselineCost = baseline?.cost_total_usd ? parseFloat(baseline.cost_total_usd) : null;

  const selectedName = shortModelName(selectedModelId);
  const baselineName = shortModelName(baselineModelId);

  let sentence = `${selectedName} is the cheapest model that passes all checks`;

  if (selectedCost !== null && baselineCost !== null && baselineCost > 0) {
    const pct = Math.round((1 - selectedCost / baselineCost) * 100);
    sentence += `; ${pct}% less than ${baselineName} on this benchmark`;
  }

  // Look for a close alternative (eligible, different from selected, within 10% of selected cost)
  if (selectedCost !== null) {
    const alternatives = candidates.filter(c =>
      c.eligibility === 'eligible' &&
      c.model.identifier !== selectedModelId &&
      c.model.identifier !== baselineModelId &&
      c.cost_total_usd !== null
    );
    const close = alternatives.find(c => {
      const alt = parseFloat(c.cost_total_usd!);
      return Math.abs(alt - selectedCost) / selectedCost < 0.10;
    });
    if (close) {
      sentence += `. ${shortModelName(close.model.identifier)} costs about the same and may be a close second`;
    }
  }

  // Record savings note
  if (decision.recorded_savings_usd != null) {
    const savings = parseFloat(decision.recorded_savings_usd);
    if (isFinite(savings) && savings > 0) {
      sentence += `. Recorded saving: \$${savings.toFixed(6)} per run`;
    }
  }

  return sentence + '.';
}

// ---------------------------------------------------------------------------
// Data-source chip label
// ---------------------------------------------------------------------------

export type DataSourceLabel = {
  text: string;
  kind: 'live' | 'recorded' | 'mock' | 'emulated';
};

/** Derives the data-source chip text from health and scan data sources. */
export function dataSourceLabel(
  scanSource?: Scan['data_source'] | null,
  healthProvenance?: Health['benchmark_provenance'],
  scanTimestamp?: string | null,
): DataSourceLabel {
  if (scanSource === 'mock') {
    return { text: 'Mock data', kind: 'mock' };
  }
  if (scanSource === 'recorded') {
    const date = scanTimestamp ? formatShortDate(scanTimestamp) : null;
    return { text: date ? `Recorded run, ${date}` : 'Recorded run', kind: 'recorded' };
  }
  if (scanSource === 'live') {
    const provenance = healthProvenance === 'recorded' ? 'Nebius' : healthProvenance ?? '';
    return { text: provenance ? `Live, ${provenance}` : 'Live', kind: 'live' };
  }
  // No scan yet
  return { text: 'No data', kind: 'live' };
}

function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

// ---------------------------------------------------------------------------
// Headline for right pane
// ---------------------------------------------------------------------------

export interface HeadlineResult {
  headline: string;
  subline: string;
  kind: 'recommended' | 'retained' | 'inconclusive' | 'unavailable' | 'none';
}

/** Generates the headline sentence for a routing decision. */
export function decisionHeadline(
  decision: Decision | null | undefined,
  selectedNodeName?: string,
): HeadlineResult {
  if (!decision) {
    return { headline: 'Scan and benchmark a call to get a recommendation.', subline: '', kind: 'none' };
  }

  const baseline = shortModelName(decision.baseline_model_id);
  const selected = decision.selected_model_id ? shortModelName(decision.selected_model_id) : null;

  if (decision.status === 'recommended' && selected && decision.selected_model_id !== decision.baseline_model_id) {
    const savings = decision.recorded_savings_usd != null
      ? ` and pay ${formatSavingPct(decision)}% less`
      : '';
    const headline = `Move ${selectedNodeName ?? 'this call'} to ${selected}${savings}.`;
    const subline = buildCostSubline(decision);
    return { headline, subline, kind: 'recommended' };
  }

  if (decision.status === 'baseline_retained') {
    return {
      headline: `Keep ${baseline} — it is already the lowest-cost passing model.`,
      subline: `Reason: ${humanReason(decision.reason)}.`,
      kind: 'retained',
    };
  }

  if (decision.status === 'inconclusive') {
    return {
      headline: 'Inconclusive',
      subline: `Reason: ${humanReason(decision.reason)}.`,
      kind: 'inconclusive',
    };
  }

  return {
    headline: 'Unavailable',
    subline: `Reason: ${humanReason(decision.reason)}.`,
    kind: 'unavailable',
  };
}

function formatSavingPct(decision: Decision): string | null {
  if (decision.recorded_savings_usd == null) return null;
  const eligible = decision.candidates.find(
    c => c.model.identifier === decision.selected_model_id
  );
  const baseline = decision.candidates.find(
    c => c.model.identifier === decision.baseline_model_id
  );
  if (!eligible?.cost_total_usd || !baseline?.cost_total_usd) return null;
  const pct = Math.round(
    (1 - parseFloat(eligible.cost_total_usd) / parseFloat(baseline.cost_total_usd)) * 100
  );
  return String(pct);
}

function buildCostSubline(decision: Decision): string {
  const baselineC = decision.candidates.find(c => c.model.identifier === decision.baseline_model_id);
  const selectedC = decision.candidates.find(c => c.model.identifier === decision.selected_model_id);
  const before = baselineC?.cost_total_usd ? `\$${parseFloat(baselineC.cost_total_usd).toFixed(6)}` : '—';
  const after = selectedC?.cost_total_usd ? `\$${parseFloat(selectedC.cost_total_usd).toFixed(6)}` : '—';
  const movers = decision.candidates.filter(c =>
    c.eligibility === 'eligible' && c.model.identifier !== decision.baseline_model_id
  ).length;
  const moverText = movers > 0 ? `. ${movers} call${movers > 1 ? 's' : ''} can move` : '';
  return `Per run, this call drops from ${before} to ${after}${moverText}.`;
}

function humanReason(reason: string): string {
  const map: Record<string, string> = {
    lowest_recorded_cost: 'baseline already has the lowest recorded cost',
    baseline_lowest_cost: 'baseline already has the lowest cost',
    no_eligible_alternative: 'no eligible alternative found',
    baseline_ineligible: 'baseline is ineligible',
    candidate_evidence_incomplete: 'candidate evidence is incomplete',
    quality_failed: 'quality checks failed',
    quality_unavailable: 'quality data unavailable',
    cost_unavailable: 'cost data unavailable',
    threshold_not_met: 'quality threshold not met',
    evidence_unavailable: 'evidence unavailable',
    test_evidence: 'synthetic test evidence cannot authorise production routing',
    approval_unavailable: 'approval unavailable',
    threshold_unconfigured: 'quality threshold not configured',
    benchmark_incomplete: 'benchmark incomplete',
  };
  return map[reason] ?? reason;
}

// ---------------------------------------------------------------------------
// Check label helper (for the checks list)
// ---------------------------------------------------------------------------
export type CheckStatus = 'passed' | 'failed' | 'not_checked' | 'not_applicable' | 'not_run';

export function checkLabel(status: CheckStatus): { text: string; kind: 'pass' | 'fail' | 'neutral' } {
  if (status === 'passed' || status === 'not_applicable') {
    return { text: status === 'passed' ? 'Passed' : 'Not applicable', kind: 'pass' };
  }
  if (status === 'failed') return { text: 'Failed', kind: 'fail' };
  if (status === 'not_run') return { text: 'Not run', kind: 'neutral' };
  return { text: 'Not checked', kind: 'neutral' };
}

// ---------------------------------------------------------------------------
// Job per-node model summary for call list
// ---------------------------------------------------------------------------
export interface CallResult {
  /** e.g. "Ultra to Nano" */
  change: string | null;
  /** "recommended" | "retained" | null */
  kind: 'recommended' | 'retained' | null;
  baselineName?: string;
  selectedName?: string;
}

export function callResult(nodeId: string, optimization?: Optimization): CallResult {
  if (!optimization) return { change: null, kind: null };
  const d = optimization.result.decisions.find(d => d.node_id === nodeId);
  if (!d) return { change: null, kind: null };
  if (d.status === 'recommended' && d.selected_model_id && d.selected_model_id !== d.baseline_model_id) {
    const base = shortModelName(d.baseline_model_id);
    const sel = shortModelName(d.selected_model_id);
    return {
      change: `${base} to ${sel}`,
      kind: 'recommended',
      baselineName: base,
      selectedName: sel,
    };
  }
  if (d.status === 'baseline_retained') {
    return {
      change: `Stays on ${shortModelName(d.baseline_model_id)}`,
      kind: 'retained',
    };
  }
  return { change: null, kind: null };
}

// ---------------------------------------------------------------------------
// Readable call name from node
// ---------------------------------------------------------------------------
import type { Backend_LLMNode as LLMNode } from './contracts.ts';

export function callName(node: LLMNode): string {
  if (node.function_name) return node.function_name;
  // Derive from file + line
  const file = node.file_path.split('/').pop() ?? node.file_path;
  return `${file}:${node.line_number}`;
}

// ---------------------------------------------------------------------------
// Workflow step
// ---------------------------------------------------------------------------
export type WorkflowStep = 'scan' | 'benchmark' | 'recommend' | 'patch';

export function deriveStep(
  analysis?: Scan,
  job?: Job,
  optimization?: Optimization,
): WorkflowStep {
  if (!analysis) return 'scan';
  if (!job || job.status !== 'complete') return 'benchmark';
  if (!optimization) return 'recommend';
  return 'patch';
}

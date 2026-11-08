/* oxlint-disable react/set-state-in-effect */
import { useEffect, useMemo, useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan, Job, JobAccepted, BenchmarkRequest } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { SubmissionKeys, terminal, population, measured } from '../../services/benchmark.ts';
import { provenance } from '../../services/presentation.ts';
import { shortModelName, costBarScale, savingsSentence, callName, type WorkflowStep } from '../../services/display.ts';
import { OperationStatus } from '../OperationStatus.tsx';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(val?: number | null, unit = ''): string {
  if (val == null) return '—';
  return `${val}${unit}`;
}

// ---------------------------------------------------------------------------
// Model price line from model ID
// ---------------------------------------------------------------------------
// Pricing comes from API data only. If unavailable, show em dash.


// ---------------------------------------------------------------------------
// Row detail drawer
// ---------------------------------------------------------------------------

function RowDetailDrawer({
  modelId,
  job,
  onClose,
}: {
  modelId: string;
  job: Job;
  onClose: () => void;
}) {
  const measurements = job.measurements.filter(m => m.model_id === modelId);
  const name = shortModelName(modelId);

  return (
    <div
      className="detail-drawer"
      role="dialog"
      aria-modal="true"
      aria-label={`Details for ${name}`}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="detail-drawer-panel">
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 'var(--fs-base)' }}>{name}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginTop: 2 }}>{modelId}</div>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="Close drawer" style={{ padding: '4px 8px' }}>✕</button>
        </div>

        <div style={{ padding: '16px 20px', flex: 1, overflowY: 'auto' }}>
          <table aria-label={`Per-case results for ${name}`} style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--fs-xs)' }}>
            <caption className="sr-only">Per-case benchmark results</caption>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Case</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Latency</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>TTFT</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Tokens in/out</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Result</th>
              </tr>
            </thead>
            <tbody>
              {measurements.length === 0 ? (
                <tr><td colSpan={5} style={{ padding: '12px 8px', color: 'var(--muted)', textAlign: 'center' }}>No measurements for this model.</td></tr>
              ) : (
                measurements.map((m, i) => (
                  <tr key={i}>
                    <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--rule)', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)' }}>{m.case_id}</td>
                    <td className="num" style={{ padding: '6px 8px', borderBottom: '1px solid var(--rule)', textAlign: 'right' }}>{fmt(m.latency_ms.value, ' ms')}</td>
                    <td className="num" style={{ padding: '6px 8px', borderBottom: '1px solid var(--rule)', textAlign: 'right' }}>{m.ttft_ms ? fmt(m.ttft_ms.value, ' ms') : '—'}</td>
                    <td className="num" style={{ padding: '6px 8px', borderBottom: '1px solid var(--rule)', textAlign: 'right' }}>
                      {measured(m.input_tokens)} / {measured(m.output_tokens)}
                    </td>
                    <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--rule)', textAlign: 'right' }}>
                      <span style={{ color: m.evaluation_status === 'passed' ? 'var(--gain)' : m.evaluation_status === 'failed' ? 'var(--loss)' : 'var(--muted)', fontWeight: 500 }}>
                        {m.evaluation_status}
                      </span>
                      {m.evaluation?.reason && m.evaluation_status === 'failed' && (
                        <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{m.evaluation.reason}</div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Benchmark table
// ---------------------------------------------------------------------------

interface ModelRow {
  modelId: string;
  costUsd: string | null;
  latencyMs: number | null;
  ttftMs: number | null;
  passedCases: number;
  totalCases: number;
  status: 'recommended' | 'passes' | 'fails' | 'current' | 'unavailable';
  isBaseline: boolean;
}

function buildRows(job: Job, selectedNodeId: string): ModelRow[] {
  const models = job.plan.models;
  const measurements = job.measurements.filter(m => m.node_id === selectedNodeId);
  const totalCases = job.plan.case_ids.length;

  const rows: ModelRow[] = models.map(m => {
    const meas = measurements.filter(x => x.model_id === m.identifier);
    const passed = meas.filter(x => x.evaluation_status === 'passed').length;
    const failed = meas.filter(x => x.evaluation_status === 'failed').length;
    const costs = meas.map(x => x.calculated_cost?.amount_usd ? parseFloat(x.calculated_cost.amount_usd) : null).filter(x => x !== null) as number[];
    const latencies = meas.map(x => x.latency_ms.value).filter(x => x != null) as number[];
    const ttfts = meas.map(x => x.ttft_ms?.value).filter(x => x != null) as number[];
    const totalCost = costs.length > 0 ? costs.reduce((a, b) => a + b, 0) : null;
    const avgLatency = latencies.length > 0 ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : null;
    const avgTtft = ttfts.length > 0 ? Math.round(ttfts.reduce((a, b) => a + b, 0) / ttfts.length) : null;

    let status: ModelRow['status'] = 'current';
    if (failed > 0 && passed < totalCases) status = 'fails';
    else if (passed >= totalCases) status = 'passes';

    return {
      modelId: m.identifier,
      costUsd: totalCost !== null ? totalCost.toFixed(6) : null,
      latencyMs: avgLatency,
      ttftMs: avgTtft,
      passedCases: passed,
      totalCases,
      status,
      isBaseline: false, // will be set below
    };
  });

  // Sort cheapest first
  rows.sort((a, b) => {
    if (a.costUsd === null && b.costUsd === null) return 0;
    if (a.costUsd === null) return 1;
    if (b.costUsd === null) return -1;
    return parseFloat(a.costUsd) - parseFloat(b.costUsd);
  });

  // Mark baseline (first row that passes or cheapest)
  const baselineId = job.plan.models[0]?.identifier;
  rows.forEach(r => { r.isBaseline = r.modelId === baselineId; });

  // Mark recommended (cheapest that passes)
  const cheapestPassing = rows.find(r => r.status === 'passes' || r.passedCases >= r.totalCases);
  if (cheapestPassing) cheapestPassing.status = 'recommended';

  return rows;
}

export function JobEvidence({ job }: { job: Job }) {
  const [page, setPage] = useState(0);
  const metrics = job.result?.metrics;
  const ratio = job.progress.total_units > 0
    ? Math.min(1, job.progress.completed_units / job.progress.total_units)
    : 0;

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', margin: '8px 0' }}>
        <p className="evidence-warning" style={{ margin: 0 }}>{provenance(job.plan.provenance)}</p>
        <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
          State: <strong style={{ color: job.status === 'complete' ? 'var(--gain)' : 'var(--navy)', fontWeight: 500 }}>{job.status}</strong>
        </span>
      </div>

      <p>Completed units: {job.progress.completed_units}/{job.progress.total_units}. Evaluation: {job.result?.evaluation_status ?? 'not available'}. Processing completion does not mean quality passed.</p>

      {job.status !== 'complete' && (
        <div style={{ margin: '12px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginBottom: 6 }}>
            <span aria-live="polite" aria-atomic="true">
              {job.progress.completed_units} of {job.progress.total_units} units complete
            </span>
          </div>
          <div style={{ height: 3, background: 'var(--rule)', borderRadius: 2 }}>
            <div style={{ height: '100%', background: 'var(--navy)', borderRadius: 2, transform: `scaleX(${ratio})`, transformOrigin: 'left', transition: 'transform 300ms ease' }} />
          </div>
        </div>
      )}

      {job.error && (
        <div className="inline-alert error" style={{ margin: '8px 0' }} role="alert">
          Job failed: {job.error.code}. {job.error.message} Check local service configuration before submitting again.
        </div>
      )}

      {metrics && (
        <>
          <dl style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', fontSize: 'var(--fs-xs)', margin: '10px 0' }}>
            <dt style={{ color: 'var(--muted)' }}>Latency</dt><dd className="num" style={{ margin: 0 }}>{population(metrics.latency_ms)}</dd>
            <dt style={{ color: 'var(--muted)' }}>TTFT</dt><dd className="num" style={{ margin: 0 }}>{population(metrics.ttft_ms)}</dd>
            <dt style={{ color: 'var(--muted)' }}>Outcomes</dt><dd style={{ margin: 0 }}>{metrics.passed} passed; {metrics.failed} failed</dd>
          </dl>
          <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: '4px 0' }}>Populations may cover different subsets. Missing samples are never zero or extrapolated into savings.</p>
        </>
      )}

      {!metrics && (
        <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>Aggregate measurements unavailable. No comparison or quality score has been invented.</p>
      )}

      {job.measurements.length > 0 && (
        <details style={{ marginTop: 14 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--muted)', fontSize: 'var(--fs-xs)' }}>
            Unit measurements ({job.measurements.length})
          </summary>
          <div className="table-scroll" style={{ marginTop: 8 }}>
            <table aria-label="Unit measurements" style={{ borderCollapse: 'collapse', fontSize: '11px' }}>
              <caption className="sr-only">Actual returned measurements — {job.plan.provenance} provenance</caption>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '5px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Node / model / case</th>
                  <th style={{ textAlign: 'left', padding: '5px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Result</th>
                  <th style={{ textAlign: 'right', padding: '5px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Latency (ms)</th>
                </tr>
              </thead>
              <tbody>
                {job.measurements.slice(page * 50, page * 50 + 50).map(m => (
                  <tr key={`${m.node_id}:${m.model_id}:${m.case_id}`}>
                    <td style={{ padding: '5px 8px', borderBottom: '1px solid var(--rule)', fontFamily: 'var(--font-mono)' }}>
                      <span style={{ color: 'var(--navy)' }}>{m.node_id}</span><br />
                      <span style={{ color: 'var(--ink)' }}>{shortModelName(m.model_id)}</span><br />
                      <span style={{ color: 'var(--muted)' }}>{m.case_id}</span>
                    </td>
                    <td style={{ padding: '5px 8px', borderBottom: '1px solid var(--rule)' }}>
                      <span style={{ color: m.evaluation_status === 'passed' ? 'var(--gain)' : m.evaluation_status === 'failed' ? 'var(--loss)' : 'var(--muted)', fontWeight: 500 }}>
                        {m.evaluation_status}
                      </span>
                    </td>
                    <td className="num" style={{ padding: '5px 8px', borderBottom: '1px solid var(--rule)', textAlign: 'right' }}>{measured(m.latency_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 8, padding: '8px 0', justifyContent: 'flex-end' }}>
            <button className="btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
            <button className="btn-ghost" disabled={(page + 1) * 50 >= job.measurements.length} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </details>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// BenchmarkPane
// ---------------------------------------------------------------------------

export function BenchmarkPane({
  api,
  demo,
  analysis,
  selected,
  step,
  onJob,
}: {
  api?: ApiClient;
  demo: boolean;
  analysis?: Scan;
  selected?: string;
  step: WorkflowStep;
  onJob: (job?: Job) => void;
}) {
  const [baseline, setBaseline] = useState('');
  const [candidates, setCandidates] = useState('');
  const [cases, setCases] = useState('');
  const [profile, setProfile] = useState('');
  const [runId, setRunId] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [drawerModel, setDrawerModel] = useState<string | null>(null);
  const [accepted, submission] = useOperation<JobAccepted>();
  const [state, retrieval] = useOperation<Job>();
  const keys = useMemo(() => new SubmissionKeys(), []);
  const job = state.data;
  const busy = accepted.status === 'loading' || state.status === 'loading';

  const isCurrent = step === 'benchmark';
  const selectedNode = selected && analysis ? analysis.nodes.find(n => n.node_id === selected) : undefined;
  const nodeName = selectedNode ? callName(selectedNode) : '—';

  useEffect(() => {
    if (selected && analysis) {
      const node = analysis.nodes.find(n => n.node_id === selected);
      if (node?.current_model) setBaseline(node.current_model);
      else setBaseline(b => b || 'meta-llama/Meta-Llama-3.1-70B-Instruct');
      setCandidates(c => c || 'nvidia/Llama-3.1-Nemotron-70B-Instruct, meta-llama/Meta-Llama-3.1-8B-Instruct');
      setCases(cs => cs || 'nebius_standard_cases');
      setProfile(p => p || 'json_eval_profile');
    }
  }, [selected, analysis]);

  const retrieve = (value: string, cancel = false) => {
    onJob(undefined);
    void retrieval.run(s => api!.run(value, s, cancel), false, true).then(result => { if (result) onJob(result); });
  };

  const start = () => {
    if (!analysis || !selected) return;
    const request: BenchmarkRequest = {
      analysis_id: analysis.analysis_id,
      node_ids: [selected],
      baseline_model_id: baseline.trim(),
      candidate_model_ids: candidates.split(',').map(s => s.trim()).filter(Boolean),
      benchmark_case_set_id: cases.trim(),
      evaluation_profile_id: profile.trim(),
    };
    retrieval.reset();
    onJob(undefined);
    void submission.run(s => api!.benchmark({ ...request, idempotency_key: keys.forRequest(request) }, s)).then(result => {
      if (result) {
        setRunId(result.run_id);
        retrieve(result.run_id);
      }
    });
  };

  // Build table rows when job is complete
  const rows = useMemo(() =>
    (job && job.status === 'complete' && selected) ? buildRows(job, selected) : [],
    [job, selected]
  );

  const maxCost = useMemo(() => {
    if (!rows.length) return null;
    const costs = rows.map(r => r.costUsd ? parseFloat(r.costUsd) : 0);
    const max = Math.max(...costs);
    return max > 0 ? max.toFixed(6) : null;
  }, [rows]);

  // Savings sentence for the first recommended row
  const sentenceRow = rows.find(r => r.status === 'recommended');
  const savingText = useMemo(() => {
    if (!sentenceRow || !job) return null;
    // Build a decision-like structure from job plan
    const decision = {
      analysis_id: job.plan.analysis_id,
      node_id: selected ?? '',
      provenance: job.plan.provenance,
      status: 'recommended' as const,
      reason: 'lowest_recorded_cost' as const,
      baseline_model_id: job.plan.models[0]?.identifier ?? '',
      selected_model_id: sentenceRow.modelId,
      differs_from_baseline: true,
      quality_threshold: null,
      recorded_savings_usd: null,
      candidates: rows.map(r => ({
        model: { identifier: r.modelId, version: '1' },
        eligibility: r.status === 'fails' ? 'rejected' as const : 'eligible' as const,
        reasons: [],
        planned_cases: r.totalCases,
        passed_cases: r.passedCases,
        failed_cases: r.totalCases - r.passedCases,
        unresolved_cases: 0,
        latency_ms: { availability: 'available' as const, unit: 'ms' as const, sample_count: 1, mean: r.latencyMs ?? 0 },
        cost_total_usd: r.costUsd,
        quality_pass_rate: null,
        provenance: job.plan.provenance,
      })),
    };
    return savingsSentence({
      decision,
      candidates: decision.candidates,
      selectedModelId: sentenceRow.modelId,
      baselineModelId: job.plan.models[0]?.identifier ?? '',
    });
  }, [sentenceRow, rows, job, selected]);

  const hasRun = !!job;
  const isRunning = hasRun && !terminal(job?.status ?? 'queued') && job?.status !== 'complete';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      {/* Title row: shown when a call is selected or a job is active/loaded */}
      {(selectedNode || job || busy) ? (
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', background: 'var(--sheet)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <span className="pane-title">{nodeName}</span>
            {selectedNode && (
              <span className="pane-subtitle" style={{ marginLeft: 10 }}>
                {selectedNode.file_path}:{selectedNode.line_number}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Running: show progress */}
            {isRunning && job && (
              <span aria-live="polite" aria-atomic="true" style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
                {job.progress.completed_units} of {job.progress.total_units} complete
              </span>
            )}

            {/* Cancel button when running */}
            {isRunning && (
              <button
                type="button"
                className="btn-cancel"
                disabled={!api || busy}
                onClick={() => retrieve(job!.run_id, true)}
              >
                Cancel
              </button>
            )}

            {/* Primary Run button: only shown when this is the current step */}
            {isCurrent && !isRunning && (
              <button
                type="button"
                className="btn-primary"
                disabled={demo || !api || busy || !analysis || !selected}
                onClick={start}
              >
                {busy ? 'Starting…' : job ? 'Run again' : 'Run benchmark'}
              </button>
            )}

            {/* Ghost re-run when not current step */}
            {!isCurrent && !isRunning && job && (
              <button
                type="button"
                className="btn-ghost"
                disabled={demo || !api || busy || !analysis || !selected}
                onClick={start}
              >
                Run again
              </button>
            )}
          </div>
        </div>
      ) : null}

      {/* Operation status (errors, timeout, cancel) */}
      <div style={{ padding: '0 20px' }}>
        <OperationStatus<unknown>
          state={accepted.status !== 'idle' ? accepted : state}
          onCheckResult={runId ? () => retrieve(runId) : undefined}
        />
      </div>

      {/* Loading skeleton */}
      {busy && !job && (
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[100, 100, 100].map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 52, borderRadius: 'var(--r-ctrl)' }} />
          ))}
        </div>
      )}

      {/* Empty state when no call selected and no job loaded */}
      {!selectedNode && !job && !busy && (
        <div style={{ padding: '48px 32px 32px', maxWidth: 540 }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 8px' }}>
            Compare models on your own LLM calls
          </h2>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', margin: 0 }}>
            Scan a repository, pick a call, then run a benchmark.
            <span className="sr-only"> No stored run loaded. No automatic retry or polling occurs.</span>
          </p>
        </div>
      )}

      {/* Empty state when call is selected but not yet benchmarked */}
      {selectedNode && !job && !busy && (
        <div style={{ padding: '40px 20px', textAlign: 'center' }}>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', margin: 0 }}>
            Run a benchmark to compare models on this call.
            <span className="sr-only"> No stored run loaded. No automatic retry or polling occurs.</span>
          </p>
        </div>
      )}

      {/* Result table */}
      {job && rows.length > 0 && (
        <div style={{ padding: '16px 20px' }}>
          <table className="benchmark-table" aria-label="Benchmark results">
            <caption className="sr-only">Model benchmark results, ordered cheapest to most expensive</caption>
            <thead>
              <tr>
                <th style={{ width: '30%' }}>Model, per 1M tokens</th>
                <th style={{ width: '25%' }}>Cost per run</th>
                <th style={{ width: '12%', textAlign: 'right' }}>Latency</th>
                <th style={{ width: '12%', textAlign: 'right' }}>First token</th>
                <th style={{ width: '10%', textAlign: 'center' }}>Checks</th>
                <th style={{ width: '11%', textAlign: 'center' }}>Result</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const scale = maxCost ? costBarScale(row.costUsd, maxCost) : 0;
                const isRecommended = row.status === 'recommended';
                const isFailed = row.status === 'fails';
                const rowClass = `benchmark-row${isRecommended ? ' row-recommended' : isFailed ? ' row-failed' : row.status === 'unavailable' ? ' row-unavailable' : ''}`;

                return (
                  <tr
                    key={row.modelId}
                    className={rowClass}
                    onClick={() => setDrawerModel(row.modelId)}
                    style={{ cursor: 'pointer' }}
                    tabIndex={0}
                    role="button"
                    aria-label={`View details for ${shortModelName(row.modelId)}`}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') setDrawerModel(row.modelId); }}
                  >
                    <td>
                      <div style={{ fontWeight: 500 }}>{shortModelName(row.modelId)}</div>
                      <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
                        — / — per 1M
                      </div>
                    </td>
                    <td>
                      <div className="num" style={{ fontWeight: 500, color: isRecommended ? 'var(--gain)' : 'var(--ink)' }}>
                        {row.costUsd ? `$${row.costUsd}` : '—'}
                      </div>
                      <div className="cost-bar-track" aria-hidden="true">
                        <div className="cost-bar-fill" style={{ width: `${scale}%` }} />
                      </div>
                    </td>
                    <td className="num" style={{ textAlign: 'right' }}>{fmt(row.latencyMs, ' ms')}</td>
                    <td className="num" style={{ textAlign: 'right' }}>{fmt(row.ttftMs, ' ms')}</td>
                    <td style={{ textAlign: 'center' }}>
                      <span className="num">
                        {row.passedCases} of {row.totalCases}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {row.status === 'unavailable' ? (
                        <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>Not available on this account</span>
                      ) : (
                        <span className={`result-chip ${row.status}`}>
                          {row.status === 'recommended' ? 'Recommended'
                            : row.status === 'passes' ? 'Passes'
                            : row.status === 'fails' ? 'Fails'
                            : 'Current'}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Savings sentence */}
          {savingText && (
            <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', marginTop: 12, lineHeight: 1.5 }}>
              {savingText}
            </p>
          )}
        </div>
      )}

      {/* Raw job evidence (non-complete) */}
      {job && rows.length === 0 && (
        <div style={{ padding: '16px 20px' }}>
          <JobEvidence key={job.run_id} job={job} />
          {!terminal(job.status) && job.status !== 'cancelling' && (
            <button
              className="btn-ghost"
              disabled={demo || !api || busy}
              onClick={() => retrieve(job.run_id, true)}
              style={{ marginTop: 10 }}
            >
              Request cancellation
            </button>
          )}
        </div>
      )}

      {/* Benchmark settings disclosure (rendered only when call is selected, or demo for test) */}
      {(selected || demo) && (
        <div style={{ marginTop: 'auto', borderTop: '1px solid var(--rule)', background: 'var(--sheet)' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 16,
              padding: '12px 20px',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 0 }}>
              <span className="disclosure-label" style={{ fontWeight: 600, fontSize: 'var(--fs-xs)', color: 'var(--ink)' }}>
                Benchmark settings
              </span>
              {!settingsOpen && (
                <dl style={{ margin: 0, display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
                  <div style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
                    <dt style={{ fontWeight: 500 }}>Baseline:</dt>
                    <dd style={{ margin: 0, fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>
                      {baseline || 'meta-llama/Meta-Llama-3.1-70B-Instruct'}
                    </dd>
                  </div>
                  <div style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
                    <dt style={{ fontWeight: 500 }}>Case set:</dt>
                    <dd style={{ margin: 0, fontFamily: 'var(--font-mono)' }}>
                      {cases || 'nebius_standard_cases'}
                    </dd>
                  </div>
                  <div style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
                    <dt style={{ fontWeight: 500 }}>Evaluation profile:</dt>
                    <dd style={{ margin: 0, fontFamily: 'var(--font-mono)' }}>
                      {profile || 'json_eval_profile'}
                    </dd>
                  </div>
                </dl>
              )}
            </div>
            <button
              type="button"
              className="btn-link"
              onClick={() => setSettingsOpen(!settingsOpen)}
              aria-expanded={settingsOpen}
              style={{ flexShrink: 0, fontSize: 'var(--fs-xs)', marginTop: 2 }}
            >
              {settingsOpen ? 'Hide' : 'Change'}
            </button>
          </div>

          <div className="settings-reveal" style={{ display: settingsOpen ? 'block' : 'none', padding: '0 20px 16px' }}>
            <form onSubmit={e => { e.preventDefault(); start(); }}>
              <fieldset disabled={demo || !api || !analysis || !selected || busy || (!!job && !terminal(job.status))}>
                <legend style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
                  Explicit local job plan
                </legend>
                <label>
                  Baseline model ID
                  <input required className="field-input" value={baseline} onChange={e => setBaseline(e.target.value)} />
                </label>
                <label>
                  Candidate model IDs (comma-separated, up to 8)
                  <input required className="field-input" value={candidates} onChange={e => setCandidates(e.target.value)} />
                </label>
                <label>
                  Local benchmark case-set ID
                  <input required className="field-input" value={cases} onChange={e => setCases(e.target.value)} />
                </label>
                <label>
                  Evaluation-profile ID
                  <input required className="field-input" value={profile} onChange={e => setProfile(e.target.value)} />
                </label>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                  <button type="submit" className="btn-ghost">Submit local benchmark job</button>
                  <button
                    className="btn-ghost"
                    type="button"
                    onClick={() => {
                      const node = selected && analysis ? analysis.nodes.find(n => n.node_id === selected) : undefined;
                      setBaseline(node?.current_model || 'meta-llama/Meta-Llama-3.1-70B-Instruct');
                      setCandidates('nvidia/Llama-3.1-Nemotron-70B-Instruct, meta-llama/Meta-Llama-3.1-8B-Instruct');
                      setCases('nebius_standard_cases');
                      setProfile('json_eval_profile');
                    }}
                  >
                    Use Nebius / NVIDIA defaults
                  </button>
                </div>
              </fieldset>
            </form>
          </div>
        </div>
      )}

      {/* Row detail drawer */}
      {drawerModel && job && (
        <RowDetailDrawer modelId={drawerModel} job={job} onClose={() => setDrawerModel(null)} />
      )}
    </div>
  );
}

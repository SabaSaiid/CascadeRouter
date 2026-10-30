import { useEffect, useMemo, useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan, Job, JobAccepted, BenchmarkRequest } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { SubmissionKeys, terminal, population, measured } from '../../services/benchmark.ts';
import { provenance } from '../../services/presentation.ts';
import { OperationStatus } from '../OperationStatus.tsx';

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
        <span style={{ fontSize: '12px', color: 'var(--cr-subtle)' }}>
          State: <strong style={{ color: job.status === 'complete' ? 'var(--cr-pass)' : 'var(--cr-accent)' }}>{job.status}</strong>
        </span>
      </div>

      <div style={{ background: 'var(--cr-surface-2)', padding: '14px 18px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)', margin: '12px 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--cr-text)' }}>Benchmark Execution Progress</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--cr-muted)' }}>
            {job.progress.completed_units} / {job.progress.total_units} units
          </span>
        </div>
        <div className="job-progress-bar">
          <div
            className="job-progress-bar-inner"
            style={{ transform: `scaleX(${ratio})` }}
          />
        </div>
      </div>

      <p><code>{job.run_id}</code> — processing state: <strong>{job.status}</strong>. This is a stored snapshot; refresh for current progress.</p>
      <p>Completed units: {job.progress.completed_units}/{job.progress.total_units}. Evaluation: {job.result?.evaluation_status ?? 'not available'}. Processing completion does not mean quality passed.</p>
      <p>Updated {new Date(job.updated_at).toLocaleString()}; deadline {new Date(job.deadline_at).toLocaleString()}{job.finished_at && `; finished ${new Date(job.finished_at).toLocaleString()}`}.</p>
      {job.error && <p role="alert">Job failure: {job.error.code}. Check local service configuration before submitting again.</p>}
      {job.cancellation_reason && <p>Cancellation reason: {job.cancellation_reason}. Only the backend confirms cancellation.</p>}

      {metrics ? (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', margin: '12px 0' }}>
            <span style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(52, 211, 153, 0.12)', border: '1px solid rgba(52, 211, 153, 0.3)', color: 'var(--cr-pass)', fontSize: '12px', fontWeight: 600 }}>
              ✓ {metrics.passed} passed
            </span>
            <span style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(248, 113, 113, 0.12)', border: '1px solid rgba(248, 113, 113, 0.3)', color: 'var(--cr-fail)', fontSize: '12px', fontWeight: 600 }}>
              ✕ {metrics.failed} failed
            </span>
            <span style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(251, 191, 36, 0.12)', border: '1px solid rgba(251, 191, 36, 0.3)', color: 'var(--cr-warn)', fontSize: '12px', fontWeight: 600 }}>
              ⚠ {metrics.skipped} skipped
            </span>
            <span style={{ padding: '4px 10px', borderRadius: '6px', background: 'var(--cr-surface-2)', border: '1px solid var(--cr-line)', color: 'var(--cr-subtle)', fontSize: '12px' }}>
              ? {metrics.inconclusive} inconclusive
            </span>
          </div>
          <dl>
            <dt>Evaluation coverage</dt>
            <dd>{metrics.evaluation_complete ? 'complete' : 'incomplete'} — evaluated {metrics.evaluated_units}/{metrics.planned_units}</dd>
            <dt>Outcomes</dt>
            <dd>{metrics.passed} passed; {metrics.failed} failed; {metrics.skipped} skipped; {metrics.inconclusive} inconclusive; {metrics.not_run} not run</dd>
            <dt>Latency</dt>
            <dd>{population(metrics.latency_ms)}</dd>
            <dt>Time to first token</dt>
            <dd>{population(metrics.ttft_ms)}</dd>
            <dt>Input usage</dt>
            <dd>{population(metrics.input_tokens)}</dd>
            <dt>Output usage</dt>
            <dd>{population(metrics.output_tokens)}</dd>
            <dt>Verified population cost</dt>
            <dd>{population(metrics.cost_usd)}</dd>
          </dl>
          <p>Populations may cover different subsets. Missing samples are never zero or extrapolated into savings.</p>
        </>
      ) : (
        <p>Aggregate measurements unavailable. No comparison or quality score has been invented.</p>
      )}

      {job.measurements.length > 0 && (
        <details style={{ marginTop: '14px' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--cr-muted)', fontSize: 'var(--cr-fs-xs)' }}>
            Unit measurements ({job.measurements.length}; 50 per page)
          </summary>
          <div className="table-scroll">
            <table>
              <caption>Actual returned measurements — {job.plan.provenance} provenance</caption>
              <thead>
                <tr>
                  <th>Node / model / case</th>
                  <th>Evaluation</th>
                  <th>Latency (ms)</th>
                  <th>Input / output tokens</th>
                  <th>Calculated cost</th>
                </tr>
              </thead>
              <tbody>
                {job.measurements.slice(page * 50, page * 50 + 50).map(m => (
                  <tr key={`${m.node_id}:${m.model_id}:${m.case_id}`}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                      <span style={{ color: 'var(--cr-accent)' }}>{m.node_id}</span>
                      <br />
                      <span style={{ color: 'var(--cr-text)' }}>{m.model_id}</span>
                      <br />
                      <span style={{ color: 'var(--cr-subtle)' }}>{m.case_id}</span>
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: m.evaluation_status === 'passed' ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 191, 36, 0.12)',
                          color: m.evaluation_status === 'passed' ? 'var(--cr-pass)' : 'var(--cr-warn)',
                        }}
                      >
                        {m.evaluation_status}
                      </span>
                      ; quality {m.quality_score ?? 'Unavailable'}
                    </td>
                    <td className="num">{measured(m.latency_ms)}</td>
                    <td className="num">{measured(m.input_tokens)} / {measured(m.output_tokens)}</td>
                    <td>
                      {m.calculated_cost?.availability === 'available'
                        ? <span className="num" style={{ color: 'var(--cr-pass)' }}>{m.calculated_cost.amount_usd} USD</span>
                        : 'Unavailable'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="control-row">
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous measurements</button>
            <button disabled={(page + 1) * 50 >= job.measurements.length} onClick={() => setPage(page + 1)}>Next measurements</button>
          </div>
        </details>
      )}
    </>
  );
}

export function BenchmarkPane({ api, demo, analysis, selected, onJob }: { api?: ApiClient; demo: boolean; analysis?: Scan; selected?: string; onJob: (job?: Job) => void }) {
  const [baseline, setBaseline] = useState('');
  const [candidates, setCandidates] = useState('');
  const [cases, setCases] = useState('');
  const [profile, setProfile] = useState('');
  const [runId, setRunId] = useState('');
  const [accepted, submission] = useOperation<JobAccepted>();
  const [state, retrieval] = useOperation<Job>();
  const keys = useMemo(() => new SubmissionKeys(), []);
  const job = state.data;
  const busy = accepted.status === 'loading' || state.status === 'loading';

  useEffect(() => {
    if (selected && analysis) {
      const node = analysis.nodes.find(n => n.node_id === selected);
      if (node && node.current_model) {
        setBaseline(node.current_model);
      } else {
        setBaseline(b => b || 'meta-llama/Meta-Llama-3.1-70B-Instruct');
      }
      setCandidates(c => c || 'nvidia/Llama-3.1-Nemotron-70B-Instruct, meta-llama/Meta-Llama-3.1-8B-Instruct');
      setCases(cs => cs || 'nebius_standard_cases');
      setProfile(p => p || 'json_eval_profile');
    }
  }, [selected, analysis]);

  const fillNebiusDefaults = () => {
    const node = selected && analysis ? analysis.nodes.find(n => n.node_id === selected) : undefined;
    setBaseline(node?.current_model || 'meta-llama/Meta-Llama-3.1-70B-Instruct');
    setCandidates('nvidia/Llama-3.1-Nemotron-70B-Instruct, meta-llama/Meta-Llama-3.1-8B-Instruct');
    setCases('nebius_standard_cases');
    setProfile('json_eval_profile');
  };

  const retrieve = (value: string, cancel = false) => {
    onJob(undefined);
    void retrieval.run(s => api!.run(value, s, cancel), false, true).then(result => { if (result) onJob(result); });
  };

  const start = () => {
    const request: BenchmarkRequest = {
      analysis_id: analysis!.analysis_id,
      node_ids: [selected!],
      baseline_model_id: baseline.trim(),
      candidate_model_ids: candidates.split(',').map(s => s.trim()).filter(Boolean),
      benchmark_case_set_id: cases.trim(),
      evaluation_profile_id: profile.trim()
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

  return (
    <section aria-labelledby="benchmark-title">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <h2 id="benchmark-title">2. Local model benchmark</h2>
        {job && (
          <span style={{ fontSize: '11px', fontWeight: 600, color: job.status === 'complete' ? 'var(--cr-pass)' : 'var(--cr-accent)', background: 'var(--cr-surface-2)', padding: '3px 8px', borderRadius: '4px', border: '1px solid var(--cr-line)' }}>
            Status: {job.status}
          </span>
        )}
      </div>
      <p>Supply identifiers from your operator-configured local registry. Preloaded Nebius and NVIDIA models and standard evaluation suites are available below.</p>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '6px 12px', background: 'var(--cr-surface-2)', borderRadius: 'var(--cr-r-chip)', border: '1px solid var(--cr-line)', margin: '6px 0' }}>
        <span style={{ fontSize: '12px', color: 'var(--cr-subtle)' }}>Selected finding:</span>
        <code style={{ color: selected ? 'var(--cr-accent)' : 'var(--cr-warn)' }}>
          {selected ?? 'none — select a discovered call'}
        </code>
      </div>
      <p>Each submission benchmarks this one finding.</p>

      <form onSubmit={e => { e.preventDefault(); start(); }}>
        <fieldset disabled={demo || !api || !analysis || !selected || busy || (!!job && !terminal(job.status))}>
          <legend style={{ fontSize: '12px', fontWeight: 600, color: 'var(--cr-subtle)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Explicit local job plan
          </legend>
          <label>
            Baseline model ID
            <input required value={baseline} onChange={e => setBaseline(e.target.value)} />
          </label>
          <label>
            Candidate model IDs (comma separated, up to 8)
            <input required value={candidates} onChange={e => setCandidates(e.target.value)} />
          </label>
          <label>
            Local benchmark case-set ID
            <input required value={cases} onChange={e => setCases(e.target.value)} />
          </label>
          <label>
            Evaluation-profile ID
            <input required value={profile} onChange={e => setProfile(e.target.value)} />
          </label>
          <div className="control-row">
            <button>Submit local benchmark job</button>
            <button type="button" onClick={fillNebiusDefaults}>Use Nebius / NVIDIA Defaults</button>
          </div>
        </fieldset>
      </form>

      <OperationStatus state={accepted} cancel={submission.cancel} />
      {accepted.data && (
        <p>
          Backend accepted <code>{accepted.data.run_id}</code> in state {accepted.data.status}. {provenance(accepted.data.provenance)}. Acceptance is not a completed evaluation.
        </p>
      )}

      <form onSubmit={e => { e.preventDefault(); retrieve(runId.trim()); }}>
        <label>
          Stored run ID
          <input
            value={runId}
            onChange={e => setRunId(e.target.value)}
            required
            pattern="run_[0-9a-f]{32}"
            disabled={demo}
            placeholder="run_0123456789abcdef0123456789abcdef"
          />
        </label>
        <button disabled={demo || !api || busy}>Retrieve / refresh run</button>
      </form>

      <OperationStatus state={state} cancel={retrieval.cancel} />

      {job && (
        <>
          <JobEvidence key={job.run_id} job={job} />
          <button
            disabled={demo || !api || busy || terminal(job.status) || job.status === 'cancelling'}
            onClick={() => retrieve(job.run_id, true)}
            style={{ marginTop: '10px' }}
          >
            Request backend cancellation
          </button>
        </>
      )}

      {!job && (
        <p>
          No stored run loaded. Unknown submission outcome? Retry the same plan to reuse its idempotency key, or retrieve the known run ID. No automatic retry or polling occurs.
        </p>
      )}
    </section>
  );
}

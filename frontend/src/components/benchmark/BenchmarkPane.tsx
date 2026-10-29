import { useMemo, useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan, Job, JobAccepted, BenchmarkRequest } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { SubmissionKeys, terminal, population, measured } from '../../services/benchmark.ts';
import { provenance } from '../../services/presentation.ts';
import { OperationStatus } from '../OperationStatus.tsx';

export function JobEvidence({ job }: { job: Job }) {
  const [page, setPage] = useState(0); const metrics = job.result?.metrics;
  return <><p className="evidence-warning">{provenance(job.plan.provenance)}</p>
    <p><code>{job.run_id}</code> — processing state: <strong>{job.status}</strong>. This is a stored snapshot; refresh for current progress.</p>
    <p>Completed units: {job.progress.completed_units}/{job.progress.total_units}. Evaluation: {job.result?.evaluation_status ?? 'not available'}. Processing completion does not mean quality passed.</p>
    <p>Updated {new Date(job.updated_at).toLocaleString()}; deadline {new Date(job.deadline_at).toLocaleString()}{job.finished_at && `; finished ${new Date(job.finished_at).toLocaleString()}`}.</p>
    {job.error && <p role="alert">Job failure: {job.error.code}. Check local service configuration before submitting again.</p>}
    {job.cancellation_reason && <p>Cancellation reason: {job.cancellation_reason}. Only the backend confirms cancellation.</p>}
    {metrics ? <><dl><dt>Evaluation coverage</dt><dd>{metrics.evaluation_complete ? 'complete' : 'incomplete'} — evaluated {metrics.evaluated_units}/{metrics.planned_units}</dd><dt>Outcomes</dt><dd>{metrics.passed} passed; {metrics.failed} failed; {metrics.skipped} skipped; {metrics.inconclusive} inconclusive; {metrics.not_run} not run</dd>
      <dt>Latency</dt><dd>{population(metrics.latency_ms)}</dd><dt>Time to first token</dt><dd>{population(metrics.ttft_ms)}</dd><dt>Input usage</dt><dd>{population(metrics.input_tokens)}</dd><dt>Output usage</dt><dd>{population(metrics.output_tokens)}</dd><dt>Verified population cost</dt><dd>{population(metrics.cost_usd)}</dd></dl><p>Populations may cover different subsets. Missing samples are never zero or extrapolated into savings.</p></> : <p>Aggregate measurements unavailable. No comparison or quality score has been invented.</p>}
    {job.measurements.length > 0 && <details><summary>Unit measurements ({job.measurements.length}; 50 per page)</summary><div className="table-scroll"><table><caption>Actual returned measurements — {job.plan.provenance} provenance</caption><thead><tr><th>Node / model / case</th><th>Evaluation</th><th>Latency (ms)</th><th>Input / output tokens</th><th>Calculated cost</th></tr></thead><tbody>
      {job.measurements.slice(page * 50, page * 50 + 50).map(m => <tr key={`${m.node_id}:${m.model_id}:${m.case_id}`}><td>{m.node_id}<br />{m.model_id}<br />{m.case_id}</td><td>{m.evaluation_status}; quality {m.quality_score ?? 'Unavailable'}</td><td>{measured(m.latency_ms)}</td><td>{measured(m.input_tokens)} / {measured(m.output_tokens)}</td><td>{m.calculated_cost?.availability === 'available' ? `${m.calculated_cost.amount_usd} USD` : 'Unavailable'}</td></tr>)}
    </tbody></table></div><button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous measurements</button><button disabled={(page + 1) * 50 >= job.measurements.length} onClick={() => setPage(page + 1)}>Next measurements</button></details>}
  </>;
}
export function BenchmarkPane({ api, demo, analysis, selected, onJob }: { api?: ApiClient; demo: boolean; analysis?: Scan; selected?: string; onJob: (job?: Job) => void }) {
  const [baseline, setBaseline] = useState(''); const [candidates, setCandidates] = useState(''); const [cases, setCases] = useState(''); const [profile, setProfile] = useState(''); const [runId, setRunId] = useState('');
  const [accepted, submission] = useOperation<JobAccepted>(); const [state, retrieval] = useOperation<Job>();
  const keys = useMemo(() => new SubmissionKeys(), []); const job = state.data; const busy = accepted.status === 'loading' || state.status === 'loading';
  const retrieve = (value: string, cancel = false) => { onJob(undefined); void retrieval.run(s => api!.run(value, s, cancel), false, true).then(result => { if (result) onJob(result); }); };
  const start = () => {
    const request: BenchmarkRequest = { analysis_id: analysis!.analysis_id, node_ids: [selected!], baseline_model_id: baseline.trim(), candidate_model_ids: candidates.split(',').map(s => s.trim()).filter(Boolean), benchmark_case_set_id: cases.trim(), evaluation_profile_id: profile.trim() };
    retrieval.reset(); onJob(undefined);
    void submission.run(s => api!.benchmark({ ...request, idempotency_key: keys.forRequest(request) }, s)).then(result => { if (result) { setRunId(result.run_id); retrieve(result.run_id); } });
  };
  return <section aria-labelledby="benchmark-title"><h2 id="benchmark-title">2. Local benchmark evidence</h2>
    <p>No model provider is called by this UI. Supply identifiers from your operator-configured local registry. The API has no model or case catalog endpoint. Starting a job requires backend authorization and genuine local cases or recordings.</p>
    <p>Selected finding: <code>{selected ?? 'none — select a discovered call'}</code>. Each submission benchmarks this one finding.</p>
    <form onSubmit={e => { e.preventDefault(); start(); }}><fieldset disabled={demo || !api || !analysis || !selected || busy || !!job && !terminal(job.status)}><legend>Explicit local job plan</legend>
      <label>Baseline model ID<input required value={baseline} onChange={e => setBaseline(e.target.value)} /></label><label>Candidate model IDs (comma separated, up to 8)<input required value={candidates} onChange={e => setCandidates(e.target.value)} /></label>
      <label>Local benchmark case-set ID<input required value={cases} onChange={e => setCases(e.target.value)} /></label><label>Evaluation-profile ID<input required value={profile} onChange={e => setProfile(e.target.value)} /></label><button>Submit local benchmark job</button></fieldset></form>
    <OperationStatus state={accepted} cancel={submission.cancel} />
    {accepted.data && <p>Backend accepted <code>{accepted.data.run_id}</code> in state {accepted.data.status}. {provenance(accepted.data.provenance)}. Acceptance is not a completed evaluation.</p>}
    <form onSubmit={e => { e.preventDefault(); retrieve(runId.trim()); }}><label>Stored run ID<input value={runId} onChange={e => setRunId(e.target.value)} required pattern="run_[0-9a-f]{32}" disabled={demo} /></label><button disabled={demo || !api || busy}>Retrieve / refresh run</button></form>
    <OperationStatus state={state} cancel={retrieval.cancel} />
    {job && <><JobEvidence key={job.run_id} job={job} /><button disabled={demo || !api || busy || terminal(job.status) || job.status === 'cancelling'} onClick={() => retrieve(job.run_id, true)}>Request backend cancellation</button></>}
    {!job && <p>No stored run loaded. Unknown submission outcome? Retry the same plan to reuse its idempotency key, or retrieve the known run ID. No automatic retry or polling occurs.</p>}
  </section>;
}

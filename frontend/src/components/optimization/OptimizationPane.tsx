import type { ApiClient } from '../../services/api.ts';
import type { Scan, Job, Optimization } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { population } from '../../services/benchmark.ts';
import { provenance } from '../../services/presentation.ts';
import { OperationStatus } from '../OperationStatus.tsx';
export function OptimizationEvidence({ value }: { value: Optimization }) {
  const r = value.result;
  return <><p className="evidence-warning">{provenance(r.provenance)}</p><p>Optimization: <strong>{r.status}</strong>; decisions {r.decisions_complete ? 'complete' : 'incomplete'}. Objective: {r.objective_version ?? 'all-checks-then-cost.v1'}. Quality threshold: {r.quality_threshold ?? 'unconfigured'}.</p>
    <p>Approval manifest: {r.approval_manifest_digest ? 'bound by backend' : 'unavailable'}. Recording dataset: {r.recording_dataset_digest ? 'bound by backend' : 'unavailable'}.</p>
    <p>Persisted optimization ID: <code>{value.optimization_id ?? 'unavailable — cannot create a production proposal'}</code></p>
    {r.decisions.length === 0 && <p>No decisions available. Configure approved recorded evidence; synthetic test runs cannot authorize production routing.</p>}
    {r.decisions.map(d => <details key={d.node_id}><summary>{d.node_id}: {d.status} — {d.reason}</summary><p>Baseline {d.baseline_model_id}; selected {d.selected_model_id ?? 'unavailable'}; verified recorded savings {d.recorded_savings_usd == null ? 'Unavailable' : `${d.recorded_savings_usd} USD`}.</p><div className="table-scroll"><table><caption>Backend eligibility for {d.node_id}</caption><thead><tr><th>Model</th><th>Eligibility / restrictions</th><th>Observed pass rate</th><th>Verified cost</th><th>Descriptive latency</th></tr></thead><tbody>{d.candidates.map(c => <tr key={c.model.identifier}><td>{c.model.identifier}@{c.model.version}</td><td>{c.eligibility}: {c.reasons.join(', ')}</td><td>{c.quality_pass_rate ?? 'Unavailable'}</td><td>{c.cost_total_usd == null ? 'Unavailable' : `${c.cost_total_usd} USD`}</td><td>{population(c.latency_ms)}</td></tr>)}</tbody></table></div></details>)}
    <p>Routing policy: {value.policy.status}; {value.policy.route_count} eligible routes. {value.policy.reason ?? ''}</p>
    {value.policy.yaml_content && <details><summary>Review backend policy artifact (not activated)</summary><pre>{value.policy.yaml_content}</pre></details>}
  </>;
}
export function OptimizationPane({ api, demo, analysis, job, onOptimization }: { api?: ApiClient; demo: boolean; analysis?: Scan; job?: Job; onOptimization: (value?: Optimization) => void }) {
  const [state, operation] = useOperation<Optimization>();
  const ready = !!job && job.status === 'complete' && job.plan.analysis_id === analysis?.analysis_id;
  return <section aria-labelledby="optimization-title"><h2 id="optimization-title">3. Evidence-based optimization</h2><p>The backend alone evaluates eligibility, approval and verified cost. Latency is descriptive; this UI does not choose winners or invent comparisons. No routing policy is activated here.</p>
    {!ready && <p>Load a completed run and its matching analysis to request optimization. Failed, cancelled, interrupted or incomplete runs do not enable this action.</p>}
    <button disabled={demo || !api || !ready || state.status === 'loading'} onClick={() => { onOptimization(undefined); void operation.run(s => api!.optimize({ analysis_id: analysis!.analysis_id, run_id: job!.run_id, case_set: job!.plan.case_set, evaluation_profile: job!.plan.evaluation_profile }, s)).then(result => { if (result) onOptimization(result); }); }}>Request backend optimization</button>
    <OperationStatus state={state} cancel={operation.cancel} />
    {state.data && <OptimizationEvidence value={state.data} />}
  </section>;
}

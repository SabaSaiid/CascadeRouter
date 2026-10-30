import { useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan, Job, Optimization } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { population } from '../../services/benchmark.ts';
import { provenance } from '../../services/presentation.ts';
import { OperationStatus } from '../OperationStatus.tsx';

export function OptimizationEvidence({ value }: { value: Optimization }) {
  const r = value.result;
  const [copied, setCopied] = useState(false);

  const copyYaml = () => {
    if (value.policy.yaml_content) {
      navigator.clipboard?.writeText(value.policy.yaml_content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', margin: '8px 0' }}>
        <p className="evidence-warning" style={{ margin: 0 }}>{provenance(r.provenance)}</p>
        <span style={{ fontSize: '12px', color: 'var(--cr-subtle)' }}>
          Status: <strong style={{ color: r.status === 'complete' ? 'var(--cr-pass)' : 'var(--cr-accent)' }}>{r.status}</strong>
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px', margin: '14px 0' }}>
        <div style={{ background: 'var(--cr-surface-2)', padding: '12px 14px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <div style={{ fontSize: '11px', color: 'var(--cr-subtle)', textTransform: 'uppercase' }}>Objective</div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--cr-text)', marginTop: '4px' }}>
            {r.objective_version ?? 'all-checks-then-cost.v1'}
          </div>
        </div>
        <div style={{ background: 'var(--cr-surface-2)', padding: '12px 14px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <div style={{ fontSize: '11px', color: 'var(--cr-subtle)', textTransform: 'uppercase' }}>Decisions Coverage</div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: r.decisions_complete ? 'var(--cr-pass)' : 'var(--cr-warn)', marginTop: '4px' }}>
            {r.decisions_complete ? 'Complete' : 'Incomplete'} ({r.decisions.length} decisions)
          </div>
        </div>
        <div style={{ background: 'var(--cr-surface-2)', padding: '12px 14px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <div style={{ fontSize: '11px', color: 'var(--cr-subtle)', textTransform: 'uppercase' }}>Quality Threshold</div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--cr-text)', marginTop: '4px' }}>
            {r.quality_threshold ?? 'unconfigured'}
          </div>
        </div>
      </div>

      <p>Optimization: <strong>{r.status}</strong>; decisions {r.decisions_complete ? 'complete' : 'incomplete'}. Objective: {r.objective_version ?? 'all-checks-then-cost.v1'}. Quality threshold: {r.quality_threshold ?? 'unconfigured'}.</p>
      <p>Backend observations and restrictions: {r.diagnostics?.join(', ') || 'none reported'}.</p>
      <p>Approval manifest: {r.approval_manifest_digest ? 'bound by backend' : 'unavailable'}. Recording dataset: {r.recording_dataset_digest ? 'bound by backend' : 'unavailable'}.</p>
      <p>Persisted optimization ID: <code>{value.optimization_id ?? 'unavailable — cannot create a production proposal'}</code></p>

      {r.decisions.length === 0 && (
        <div style={{ padding: '14px', background: 'var(--cr-surface-2)', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)', margin: '12px 0' }}>
          <p style={{ margin: 0 }}>No decisions available. Configure approved recorded evidence; synthetic test runs cannot authorize production routing.</p>
        </div>
      )}

      {r.decisions.map(d => (
        <details
          key={d.node_id}
          style={{
            background: 'var(--cr-surface-2)',
            border: '1px solid var(--cr-line)',
            borderRadius: 'var(--cr-r-control)',
            padding: '12px 16px',
            margin: '10px 0',
          }}
        >
          <summary style={{ cursor: 'pointer', fontWeight: 600, color: 'var(--cr-text)', fontSize: '13px' }}>
            {d.node_id}: {d.status} — {d.reason}
          </summary>
          <div style={{ marginTop: '10px' }}>
            <p style={{ margin: '4px 0' }}>
              Baseline {d.baseline_model_id}; selected {d.selected_model_id ?? 'unavailable'}; verified recorded savings {d.recorded_savings_usd == null ? 'Unavailable' : `${d.recorded_savings_usd} USD`}.
            </p>
            <div className="table-scroll">
              <table>
                <caption>Backend eligibility for {d.node_id}</caption>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Eligibility / restrictions</th>
                    <th>Observed pass rate</th>
                    <th>Verified cost</th>
                    <th>Descriptive latency</th>
                  </tr>
                </thead>
                <tbody>
                  {d.candidates.map(c => (
                    <tr key={c.model.identifier}>
                      <td><code>{c.model.identifier}@{c.model.version}</code></td>
                      <td>
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: c.eligibility === 'eligible' ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 191, 36, 0.12)',
                            color: c.eligibility === 'eligible' ? 'var(--cr-pass)' : 'var(--cr-warn)',
                            marginRight: '6px',
                          }}
                        >
                          {c.eligibility}
                        </span>
                        : {c.reasons.join(', ')}
                      </td>
                      <td className="num">{c.quality_pass_rate ?? 'Unavailable'}</td>
                      <td>{c.cost_total_usd == null ? 'Unavailable' : <span className="num" style={{ color: 'var(--cr-pass)' }}>{c.cost_total_usd} USD</span>}</td>
                      <td className="num">{population(c.latency_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      ))}

      <p style={{ marginTop: '14px' }}>
        Routing policy: {value.policy.status}; {value.policy.route_count} eligible routes. {value.policy.reason ?? ''}
      </p>

      {value.policy.yaml_content && (
        <details style={{ marginTop: '10px' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--cr-accent)', fontSize: 'var(--cr-fs-xs)' }}>
            Review backend policy artifact (not activated)
          </summary>
          <div style={{ position: 'relative', marginTop: '8px' }}>
            <button
              type="button"
              onClick={copyYaml}
              style={{
                position: 'absolute',
                top: '10px',
                right: '10px',
                padding: '4px 10px',
                fontSize: '11px',
                background: 'var(--cr-surface-3)',
                borderColor: 'var(--cr-line)',
              }}
            >
              {copied ? '✓ Copied' : 'Copy Policy YAML'}
            </button>
            <pre>{value.policy.yaml_content}</pre>
          </div>
        </details>
      )}
    </>
  );
}

export function OptimizationPane({ api, demo, analysis, job, onOptimization }: { api?: ApiClient; demo: boolean; analysis?: Scan; job?: Job; onOptimization: (value?: Optimization) => void }) {
  const [state, operation] = useOperation<Optimization>();
  const ready = !!job && job.status === 'complete' && job.plan.analysis_id === analysis?.analysis_id;

  return (
    <section aria-labelledby="optimization-title">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <h2 id="optimization-title">3. Evidence-based optimization</h2>
        {ready && (
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cr-pass)', background: 'rgba(52, 211, 153, 0.1)', padding: '3px 8px', borderRadius: '4px' }}>
            ✓ Ready for optimization
          </span>
        )}
      </div>
      <p>The backend alone evaluates eligibility, approval and verified cost. Latency is descriptive; this UI does not choose winners or invent comparisons. No routing policy is activated here.</p>

      {!ready && (
        <div style={{ padding: '12px 16px', background: 'var(--cr-surface-2)', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)', margin: '12px 0' }}>
          <p style={{ margin: 0, fontSize: '13px' }}>
            Load a completed run and its matching analysis to request optimization. Failed, cancelled, interrupted or incomplete runs do not enable this action.
          </p>
        </div>
      )}

      <button
        disabled={demo || !api || !ready || state.status === 'loading'}
        onClick={() => {
          onOptimization(undefined);
          void operation.run(s => api!.optimize({
            analysis_id: analysis!.analysis_id,
            run_id: job!.run_id,
            case_set: job!.plan.case_set,
            evaluation_profile: job!.plan.evaluation_profile
          }, s)).then(result => {
            if (result) onOptimization(result);
          });
        }}
        style={{ margin: '8px 0' }}
      >
        Request backend optimization
      </button>

      <OperationStatus state={state} cancel={operation.cancel} />
      {state.data && <OptimizationEvidence value={state.data} />}
    </section>
  );
}

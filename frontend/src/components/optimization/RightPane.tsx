import { useMemo, useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan, Job, Optimization, Patch, PatchAccepted, Validation } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { provenance } from '../../services/presentation.ts';
import { canPropose } from '../../services/patches.ts';
import { shortModelName, decisionHeadline, callName, type WorkflowStep } from '../../services/display.ts';
import { OperationStatus } from '../OperationStatus.tsx';

// ---------------------------------------------------------------------------
// Diff viewer
// ---------------------------------------------------------------------------

function DiffViewer({ content }: { content: string }) {
  const lines = content.split('\n');
  let lineNum = 0;

  return (
    <div className="diff-viewer" role="region" aria-label="Diff preview">
      {lines.map((line, i) => {
        let type: 'add' | 'del' | 'hdr' | 'ctx' = 'ctx';
        let gutter = ' ';

        if (line.startsWith('@@')) { type = 'hdr'; gutter = ' '; }
        else if (line.startsWith('+') && !line.startsWith('+++')) { type = 'add'; gutter = '+'; lineNum++; }
        else if (line.startsWith('-') && !line.startsWith('---')) { type = 'del'; gutter = '−'; }
        else { lineNum++; }

        return (
          <div key={i} className={`diff-line ${type}`} style={{ padding: '0 8px' }}>
            <span className="diff-line-num">{type === 'del' || type === 'hdr' ? '' : lineNum}</span>
            <span className="diff-line-gutter" aria-hidden="true">{gutter}</span>
            <span className="diff-line-content">{line || '\u00A0'}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// YAML display with syntax colouring
// ---------------------------------------------------------------------------

function YamlDisplay({ content }: { content: string }) {
  const coloured = content
    .replace(/^(\s*)([\w-]+):/gm, '$1<span class="yaml-key">$2</span>:')
    .replace(/:\s*"([^"]*)"/g, ': <span class="yaml-str">"$1"</span>')
    .replace(/:\s*(\d+\.?\d*)/g, ': <span class="yaml-num">$1</span>')
    .replace(/#.*/g, '<span class="yaml-com">$&</span>');

  return (
    <pre
      style={{ margin: 0, fontSize: 'var(--fs-xs)', lineHeight: 1.6, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: coloured }}
    />
  );
}

// ---------------------------------------------------------------------------
// Checks list
// ---------------------------------------------------------------------------

type CheckEntry = {
  label: string;
  status: 'Passed' | 'Failed' | 'Not run' | 'Not checked' | 'Not applicable';
  kind: 'pass' | 'fail' | 'neutral';
};

function ChecksList({ checks }: { checks: CheckEntry[] }) {
  return (
    <div role="list" aria-label="Pre-apply checks">
      {checks.map((c, i) => (
        <div key={i} className="check-item" role="listitem">
          <span style={{ flex: 1, fontSize: 'var(--fs-sm)', color: 'var(--ink)' }}>{c.label}</span>
          <span className={`check-status ${c.kind}`}>{c.status}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Patch tab content
// ---------------------------------------------------------------------------

function PatchTab({
  proposal,
  validation,
  api,
  demo,
  step,
  onApplySuccess,
}: {
  proposal: Patch;
  validation?: { report: Validation; historical: boolean };
  api?: ApiClient;
  demo: boolean;
  step: WorkflowStep;
  onApplySuccess: (result: { patch_id: string; applied_files: { file_path: string; backup_path: string; edits_count: number }[] }) => void;
}) {
  const m = proposal.manifest;
  const f = m.files[0];
  const [applied, applyOperation] = useOperation<{ patch_id: string; status: string; applied_at: string; applied_files: { file_path: string; backup_path: string; edits_count: number }[] }>();
  const [copiedDiff, setCopiedDiff] = useState(false);

  const copyDiff = () => {
    if (proposal.review_diff) {
      void navigator.clipboard?.writeText(proposal.review_diff);
      setCopiedDiff(true);
      setTimeout(() => setCopiedDiff(false), 2000);
    }
  };

  // Build checks from validation
  const checks: CheckEntry[] = [
    {
      label: 'Only the model name changes',
      status: (validation?.report.result.files?.[0]?.ast_preservation === 'verified') ? 'Passed'
        : (validation?.report.result.files?.[0]?.ast_preservation === 'failed') ? 'Failed'
        : 'Not checked',
      kind: (validation?.report.result.files?.[0]?.ast_preservation === 'verified') ? 'pass'
        : (validation?.report.result.files?.[0]?.ast_preservation === 'failed') ? 'fail'
        : 'neutral',
    },
    {
      label: 'Python syntax is valid',
      status: (validation?.report.result.files?.[0]?.syntax === 'passed') ? 'Passed'
        : (validation?.report.result.files?.[0]?.syntax === 'failed') ? 'Failed'
        : 'Not checked',
      kind: (validation?.report.result.files?.[0]?.syntax === 'passed') ? 'pass'
        : (validation?.report.result.files?.[0]?.syntax === 'failed') ? 'fail'
        : 'neutral',
    },
    {
      label: 'Tests on the sample app',
      // Backend validates statically only; never imply tests ran
      status: 'Not run',
      kind: 'neutral',
    },
  ];

  const isCurrent = step === 'patch';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, flex: 1 }}>
      {/* File path + Copy diff */}
      {f && (
        <div style={{ padding: '10px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
            {f.file_path}
          </span>
          {proposal.review_diff && (
            <button
              type="button"
              className="btn-ghost"
              onClick={copyDiff}
              style={{ fontSize: 'var(--fs-xs)', padding: '2px 8px' }}
              title="Copy diff to clipboard"
            >
              {copiedDiff ? 'Copied' : 'Copy diff'}
            </button>
          )}
        </div>
      )}

      {/* Diff viewer */}
      {proposal.review_diff ? (
        <div style={{ padding: '12px 20px' }}>
          <DiffViewer content={proposal.review_diff} />
        </div>
      ) : (
        <p style={{ padding: '12px 20px', fontSize: 'var(--fs-sm)', color: 'var(--muted)' }}>
          No editable spans available.
        </p>
      )}

      {/* Checks before applying */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid var(--rule)' }}>
        <p style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink)', marginBottom: 8 }}>Checks before applying</p>
        <ChecksList checks={checks} />
      </div>

      {/* Footer */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid var(--rule)', background: 'var(--paper)', marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {applied.data ? (
          <div className="inline-alert success" role="status">
            Patch applied. Backup saved at <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)' }}>{applied.data.applied_files[0]?.backup_path ?? '—'}</code>
            <div style={{ marginTop: 6, fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
              Rollback command: <code style={{ userSelect: 'all', fontFamily: 'var(--font-mono)' }}>cp {applied.data.applied_files[0]?.backup_path} {applied.data.applied_files[0]?.file_path}</code>
            </div>
          </div>
        ) : applied.error ? (
          <div className="inline-alert error" role="alert">
            {applied.error.kind}: {applied.error.message}
            {applied.error.code === 'source_conflict' && (
              <div style={{ marginTop: 4 }}>Source conflict (409): the file has changed since the patch was created. Rescan before applying.</div>
            )}
          </div>
        ) : null}

        {m.files.length > 0 && !applied.data && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {/* Only one filled primary button when this is the current step */}
            <button
              className={isCurrent ? 'btn-primary' : 'btn-ghost'}
              disabled={demo || !api || applied.status === 'loading'}
              onClick={() => {
                if (window.confirm(`Apply model changes to ${m.files.length} file(s)?`)) {
                  void applyOperation.run(s => api!.applyPatch(m.patch_id, s)).then(result => {
                    if (result) onApplySuccess(result);
                  });
                }
              }}
            >
              {applied.status === 'loading' ? 'Applying…' : 'Apply patch'}
            </button>
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
              Saves {f?.file_path ? `${f.file_path.split('/').pop()}.bak` : 'a .bak file'} first
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Policy tab content
// ---------------------------------------------------------------------------

function PolicyTab({ yaml }: { yaml: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard?.writeText(yaml);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadYaml = () => {
    const blob = new Blob([yaml], { type: 'text/yaml;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'cascaderouter.yaml';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '12px 20px', flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 8 }}>
        <button type="button" className="btn-ghost" onClick={downloadYaml} style={{ fontSize: 'var(--fs-xs)' }} title="Download as cascaderouter.yaml">
          Download YAML
        </button>
        <button type="button" className="btn-ghost" onClick={copy} style={{ fontSize: 'var(--fs-xs)' }}>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <div style={{ background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 'var(--r-ctrl)', padding: '10px 12px' }}>
        <YamlDisplay content={yaml} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ROI & Impact Calculator
// ---------------------------------------------------------------------------

function RoiCalculatorCard({
  baselineCost,
  selectedCost,
  baselineName,
  selectedName,
}: {
  baselineCost: number;
  selectedCost: number;
  baselineName: string;
  selectedName: string;
}) {
  const [monthlyVolume, setMonthlyVolume] = useState(100000);

  if (baselineCost <= selectedCost) return null;

  const costPerRunDiff = baselineCost - selectedCost;
  const pctSavings = Math.round((costPerRunDiff / baselineCost) * 100);
  const monthlySavings = costPerRunDiff * monthlyVolume;
  const annualSavings = monthlySavings * 12;

  const fmtCurrency = (n: number) => {
    if (n >= 1000) return `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
    return `$${n.toFixed(2)}`;
  };

  return (
    <div className="roi-calculator-card" style={{ marginTop: 12, padding: '12px 14px', background: 'var(--sheet)', border: '1px solid var(--rule)', borderRadius: 'var(--r-ctrl)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink)' }}>
          Projected Impact
        </span>
        <span className="chip" style={{ background: 'var(--gain-tint)', color: 'var(--gain)', fontSize: '11px', fontWeight: 600 }}>
          {pctSavings}% cost reduction
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
        <div style={{ padding: '6px 8px', background: 'var(--paper)', borderRadius: 'var(--r-ctrl)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Monthly Savings</div>
          <div className="num" style={{ fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--gain)' }}>
            {fmtCurrency(monthlySavings)}
          </div>
        </div>
        <div style={{ padding: '6px 8px', background: 'var(--paper)', borderRadius: 'var(--r-ctrl)' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Annual Savings</div>
          <div className="num" style={{ fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--gain)' }}>
            {fmtCurrency(annualSavings)}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--muted)' }}>
          <span>Throughput: <strong className="num" style={{ color: 'var(--ink)' }}>{monthlyVolume.toLocaleString()} calls/mo</strong></span>
          <span>{shortModelName(baselineName)} → {shortModelName(selectedName)}</span>
        </div>
        <input
          type="range"
          min={10000}
          max={1000000}
          step={10000}
          value={monthlyVolume}
          onChange={e => setMonthlyVolume(Number(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--navy)', cursor: 'pointer' }}
          aria-label="Monthly call volume"
        />
        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
          {[10000, 50000, 100000, 500000, 1000000].map(v => (
            <button
              key={v}
              type="button"
              className={`filter-pill${monthlyVolume === v ? ' active' : ''}`}
              onClick={() => setMonthlyVolume(v)}
              style={{ fontSize: '10px', padding: '2px 4px', flex: 1, textAlign: 'center' }}
            >
              {v >= 1000000 ? `${v / 1000000}M` : `${v / 1000}k`}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RightPane = Optimization + Patch combined
// ---------------------------------------------------------------------------

export function RightPane({
  api,
  demo,
  analysis,
  job,
  step,
  onOptimization,
}: {
  api?: ApiClient;
  demo: boolean;
  analysis?: Scan;
  job?: Job;
  step: WorkflowStep;
  onOptimization: (value?: Optimization) => void;
}) {
  const [optState, optOperation] = useOperation<Optimization>();
  const [patchState, patchOperation] = useOperation<PatchAccepted>();
  const [reviewState, reviewOperation] = useOperation<Patch>();
  const [validationState, validationOperation] = useOperation<{ report: Validation; historical: boolean }>();
  const [patchId, setPatchId] = useState('');
  const [tab, setTab] = useState<'patch' | 'policy'>('patch');
  const [_applyResult, setApplyResult] = useState<null | { patch_id: string; applied_files: { file_path: string; backup_path: string; edits_count: number }[] }>(null);
  void _applyResult;

  const optimization = optState.data;
  const patch = reviewState.data;
  const ready = !!job && job.status === 'complete' && job.plan.analysis_id === analysis?.analysis_id;
  const isCurrent = step === 'recommend';
  const isPatchCurrent = step === 'patch';
  const busy = optState.status === 'loading';

  // Find the decision for the first node in the job, if present
  const firstDecision = optimization?.result.decisions[0];
  const selectedNodeId = firstDecision?.node_id;
  const selectedNode = selectedNodeId && analysis ? analysis.nodes.find(n => n.node_id === selectedNodeId) : undefined;
  const headline = decisionHeadline(firstDecision, selectedNode ? callName(selectedNode) : undefined);

  const costImpact = useMemo(() => {
    if (!job || !firstDecision || firstDecision.status !== 'recommended' || !firstDecision.selected_model_id) return null;
    const bMeas = job.measurements.filter(m => m.node_id === firstDecision.node_id && m.model_id === firstDecision.baseline_model_id);
    const sMeas = job.measurements.filter(m => m.node_id === firstDecision.node_id && m.model_id === firstDecision.selected_model_id);
    const bCosts = bMeas.map(m => m.calculated_cost?.amount_usd ? parseFloat(m.calculated_cost.amount_usd) : null).filter(c => c !== null) as number[];
    const sCosts = sMeas.map(m => m.calculated_cost?.amount_usd ? parseFloat(m.calculated_cost.amount_usd) : null).filter(c => c !== null) as number[];
    const bTotal = bCosts.length > 0 ? bCosts.reduce((a, b) => a + b, 0) : null;
    const sTotal = sCosts.length > 0 ? sCosts.reduce((a, b) => a + b, 0) : null;
    if (bTotal !== null && sTotal !== null && bTotal > sTotal) {
      return {
        baselineCost: bTotal,
        selectedCost: sTotal,
        baselineName: firstDecision.baseline_model_id,
        selectedName: firstDecision.selected_model_id,
      };
    }
    return null;
  }, [job, firstDecision]);

  const startOptimize = () => {
    onOptimization(undefined);
    void optOperation.run(s => api!.optimize({
      analysis_id: analysis!.analysis_id,
      run_id: job!.run_id,
      case_set: job!.plan.case_set,
      evaluation_profile: job!.plan.evaluation_profile,
    }, s)).then(result => { if (result) onOptimization(result); });
  };

  const createAndReadPatch = () => {
    if (!canPropose(analysis, optimization)) return;
    reviewOperation.reset();
    validationOperation.reset();
    setApplyResult(null);
    void patchOperation.run(s => api!.createPatch({
      analysis_id: analysis!.analysis_id,
      optimization_id: optimization!.optimization_id!,
      transformation: 'literal_model_id.v1',
    }, s)).then(result => {
      if (result) {
        setPatchId(result.patch_id);
        void reviewOperation.run(s => api!.patch(result.patch_id, s));
      }
    });
  };

  const validatePatch = () => {
    if (!/^patch_[0-9a-f]{32}$/.test(patchId)) return;
    void validationOperation.run(async s => ({
      report: await api!.validate(patchId, s),
      historical: false,
    }));
  };

  return (
    <aside className="right-pane" aria-label="Recommendation and patch">
      {/* Headline */}
      <div style={{ padding: '16px 20px', borderBottom: (ready || optimization) ? '1px solid var(--rule)' : 'none' }}>
        {!optimization && !ready && (
          <div>
            <h2 className="pane-title" style={{ margin: '0 0 6px', fontSize: 'var(--fs-base)', fontWeight: 600 }}>
              Recommendation
            </h2>
            <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', margin: 0 }}>
              Run a benchmark to see which model each call can move to.
            </p>
          </div>
        )}

        {!optimization && ready && (
          <>
            <p className="pane-title" style={{ marginBottom: 4 }}>
              Ready for optimization.
            </p>
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: '4px 0 0' }}>
              The backend evaluates eligibility and verified cost. No routing policy is activated here.
            </p>

            {/* Operation status */}
            <OperationStatus state={optState} onCheckResult={startOptimize} />

            {/* Primary button when this is the current step */}
            <div style={{ marginTop: 12 }}>
              <button
                className={isCurrent ? 'btn-primary' : 'btn-ghost'}
                disabled={demo || !api || busy}
                onClick={startOptimize}
              >
                {busy ? 'Working…' : 'Get recommendation'}
              </button>
            </div>
          </>
        )}

        {optimization && (
          <>
            {/* Headline sentence */}
            <p style={{
              fontSize: 'var(--fs-lg)',
              fontWeight: 600,
              color: headline.kind === 'recommended' ? 'var(--ink)' : 'var(--muted)',
              lineHeight: 1.3,
              margin: '0 0 6px',
            }}>
              {headline.headline}
            </p>
            {headline.subline && (
              <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', margin: '0 0 8px', lineHeight: 1.5 }}>
                {headline.subline}
              </p>
            )}

            {/* ROI & Impact Calculator */}
            {costImpact && (
              <RoiCalculatorCard
                baselineCost={costImpact.baselineCost}
                selectedCost={costImpact.selectedCost}
                baselineName={costImpact.baselineName}
                selectedName={costImpact.selectedName}
              />
            )}

            {/* Per-node decisions */}
            {optimization.result.decisions.map(d => (
              d.node_id !== firstDecision?.node_id && (
                <div key={d.node_id} style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginTop: 2 }}>
                  {d.node_id}: {d.status === 'baseline_retained'
                    ? `Stays on ${shortModelName(d.baseline_model_id)}`
                    : d.selected_model_id ? `→ ${shortModelName(d.selected_model_id)}` : d.status}
                </div>
              )
            ))}

            {/* Re-optimize ghost */}
            <button
              className="btn-ghost"
              disabled={demo || !api || !ready || busy}
              onClick={startOptimize}
              style={{ marginTop: 8 }}
            >
              Run again
            </button>
          </>
        )}
      </div>

      {/* Loading */}
      {busy && (
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[80, 60].map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 24, borderRadius: 'var(--r-ctrl)' }} />
          ))}
        </div>
      )}

      {/* Patch / Policy area */}
      {optimization && (
        <>
          {/* Patch creation */}
          {!patch && (
            <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--rule)' }}>
              {canPropose(analysis, optimization) ? (
                <button
                  className={isPatchCurrent ? 'btn-primary' : 'btn-ghost'}
                  disabled={demo || !api || patchState.status === 'loading' || reviewState.status === 'loading'}
                  onClick={createAndReadPatch}
                >
                  {patchState.status === 'loading' || reviewState.status === 'loading' ? 'Creating…' : 'Create patch'}
                </button>
              ) : (
                <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: 0 }}>
                  Patch requires a persisted optimization with recorded evidence.
                  {optimization.result.provenance === 'test' && ' Synthetic test evidence cannot authorise a production patch.'}
                </p>
              )}
              {patchState.error && (
                <div className="inline-alert error" style={{ marginTop: 8 }} role="alert">
                  {patchState.error.kind}: {patchState.error.message}
                </div>
              )}
              {reviewState.error && (
                <div className="inline-alert error" style={{ marginTop: 8 }} role="alert">
                  {reviewState.error.kind}: {reviewState.error.message}
                </div>
              )}
            </div>
          )}

          {/* Tabs: Patch and Policy */}
          {patch && (
            <>
              <div className="tab-bar" role="tablist" aria-label="Patch review">
                {(['patch', 'policy'] as const).map(t => (
                  <button
                    key={t}
                    className="tab-btn"
                    role="tab"
                    aria-selected={tab === t}
                    onClick={() => setTab(t)}
                  >
                    {t === 'patch' ? 'Patch' : 'Policy'}
                  </button>
                ))}
              </div>

              {tab === 'patch' && (
                <PatchTab
                  proposal={patch}
                  validation={validationState.data ?? undefined}
                  api={api}
                  demo={demo}
                  step={step}
                  onApplySuccess={() => {}}
                />
              )}

              {tab === 'policy' && (
                <PolicyTab yaml={optimization.policy.yaml_content ?? '# No policy content available.'} />
              )}

              {/* Validate action */}
              {tab === 'patch' && !validationState.data && (
                <div style={{ padding: '0 20px 12px' }}>
                  <button
                    className="btn-ghost"
                    disabled={demo || !api || !/^patch_[0-9a-f]{32}$/.test(patchId) || validationState.status === 'loading'}
                    onClick={validatePatch}
                    style={{ fontSize: 'var(--fs-xs)' }}
                  >
                    {validationState.status === 'loading' ? 'Validating…' : 'Validate (static only)'}
                  </button>
                  <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginTop: 4 }}>
                    Static syntax and AST checks. No application tests ran and no patch was applied.
                  </p>
                  {validationState.error && (
                    <div className="inline-alert error" style={{ marginTop: 8 }} role="alert">
                      {validationState.error.kind}: {validationState.error.message}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Policy-only view when no patch but policy exists */}
          {!patch && optimization.policy.yaml_content && (
            <>
              <div className="tab-bar" role="tablist" aria-label="Policy">
                <button className="tab-btn" role="tab" aria-selected={true}>Policy</button>
              </div>
              <PolicyTab yaml={optimization.policy.yaml_content} />
            </>
          )}
        </>
      )}

      {/* Provenance note */}
      {optimization && (
        <div style={{ padding: '10px 20px', borderTop: '1px solid var(--rule)', marginTop: 'auto' }}>
          <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: 0 }}>
            {provenance(optimization.result.provenance)}
          </p>
        </div>
      )}
    </aside>
  );
}

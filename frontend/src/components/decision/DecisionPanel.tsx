/* oxlint-disable */
import { useEffect } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Backend_LLMNode as LLMNode, Scan, Job, Optimization, Patch, PatchAccepted, Validation } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { canPropose } from '../../services/patches.ts';
import { decisionHeadline, callName, type WorkflowStep } from '../../services/display.ts';

export interface DecisionPanelProps {
  api?: ApiClient;
  demo: boolean;
  analysis?: Scan;
  job?: Job;
  optimization?: Optimization;
  selectedNode?: LLMNode;
  step?: WorkflowStep;
  strictAllChecks?: boolean;
  onOptimization: (value?: Optimization) => void;
  onApplySuccess?: (result: { patch_id: string; applied_files: { file_path: string; backup_path: string; edits_count: number }[] }) => void;
}

// ---------------------------------------------------------------------------
// Diff viewer with line numbers, +/- gutter, soft tints, wrapped lines
// ---------------------------------------------------------------------------

function DiffViewer({ content }: { content: string }) {
  const lines = content.split('\n');
  let lineNum = 0;

  return (
    <div className="diff-viewer" role="region" aria-label="Diff preview" style={{ overflowX: 'auto' }}>
      {lines.map((line, i) => {
        let type: 'add' | 'del' | 'hdr' | 'ctx' = 'ctx';
        let gutter = ' ';

        if (line.startsWith('@@')) {
          type = 'hdr';
          gutter = ' ';
        } else if (line.startsWith('+') && !line.startsWith('+++')) {
          type = 'add';
          gutter = '+';
          lineNum++;
        } else if (line.startsWith('-') && !line.startsWith('---')) {
          type = 'del';
          gutter = '−';
        } else {
          lineNum++;
        }

        return (
          <div
            key={i}
            className={`diff-line ${type}`}
            style={{
              display: 'flex',
              padding: '2px 8px',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              lineHeight: 1.5,
              wordBreak: 'break-all',
              whiteSpace: 'pre-wrap',
            }}
          >
            <span
              className="diff-line-num"
              style={{
                width: 32,
                userSelect: 'none',
                color: 'var(--muted)',
                textAlign: 'right',
                marginRight: 10,
                flexShrink: 0,
              }}
            >
              {type === 'del' || type === 'hdr' ? '' : lineNum}
            </span>
            <span
              className="diff-line-gutter"
              aria-hidden="true"
              style={{
                width: 14,
                userSelect: 'none',
                fontWeight: 600,
                color: type === 'add' ? 'var(--gain)' : type === 'del' ? 'var(--loss)' : 'var(--muted)',
                flexShrink: 0,
              }}
            >
              {gutter}
            </span>
            <span
              className="diff-line-content"
              style={{
                flex: 1,
                color: type === 'add' ? 'var(--gain)' : type === 'del' ? 'var(--loss)' : 'var(--ink)',
              }}
            >
              {line || '\u00A0'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DecisionPanel
// ---------------------------------------------------------------------------

export function DecisionPanel({
  api,
  demo,
  analysis,
  job,
  optimization,
  selectedNode,
  step: _step,
  strictAllChecks: _strictAllChecks,
  onOptimization,
  onApplySuccess,
}: DecisionPanelProps) {
  const [optState, optOperation] = useOperation<Optimization>();
  const [patchState, patchOperation] = useOperation<PatchAccepted>();
  const [reviewState, reviewOperation] = useOperation<Patch>();
  const [_valState, validationOperation] = useOperation<{ report: Validation; historical: boolean }>();
  const [applyState, applyOperation] = useOperation<{ patch_id: string; status: string; applied_at: string; applied_files: { file_path: string; backup_path: string; edits_count: number }[] }>();

  const readyToOptimize = Boolean(job && job.status === 'complete' && job.plan.analysis_id === analysis?.analysis_id);
  const busy = optState.status === 'loading';
  const patch = reviewState.data;

  // Selected node decision
  const nodeDecision = optimization?.result.decisions.find(d =>
    selectedNode ? d.node_id === selectedNode.node_id : true
  ) ?? optimization?.result.decisions[0];

  const headline = decisionHeadline(
    nodeDecision,
    selectedNode ? callName(selectedNode) : undefined
  );

  const startOptimize = () => {
    if (!analysis || !job) return;
    onOptimization(undefined);
    void optOperation.run(s => api!.optimize({
      analysis_id: analysis.analysis_id,
      run_id: job.run_id,
      case_set: job.plan.case_set,
      evaluation_profile: job.plan.evaluation_profile,
    }, s)).then(result => {
      if (result) onOptimization(result);
    });
  };

  const createAndReadPatch = () => {
    if (!canPropose(analysis, optimization)) return;
    reviewOperation.reset();
    validationOperation.reset();
    applyOperation.reset();
    void patchOperation.run(s => api!.createPatch({
      analysis_id: analysis!.analysis_id,
      optimization_id: optimization!.optimization_id!,
      transformation: 'literal_model_id.v1',
    }, s)).then(result => {
      if (result) {
        void reviewOperation.run(s => api!.patch(result.patch_id, s));
        void validationOperation.run(async s => ({
          report: await api!.validate(result.patch_id, s),
          historical: false,
        }));
      }
    });
  };

  // Automatically create patch when optimization is recommended
  useEffect(() => {
    if (optimization && canPropose(analysis, optimization) && !patch && patchState.status === 'idle') {
      createAndReadPatch();
    }
  }, [optimization?.optimization_id]);

  const targetFile = patch?.manifest.files[0];
  const targetFileName = targetFile ? (targetFile.file_path.split('/').pop() ?? targetFile.file_path) : 'file';

  return (
    <aside className="decision-panel-container" aria-label="Optimization decision and patch">
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)' }}>
        <h3 className="decision-panel-title">
          Decision &amp; patch
        </h3>
      </div>

      <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14, flex: 1, overflowY: 'auto' }}>
        {/* If no benchmark run completed */}
        {!optimization && !readyToOptimize && (
          <div style={{ color: 'var(--muted)', fontSize: 'var(--fs-sm)' }}>
            Run a benchmark to see which model each call can move to.
          </div>
        )}

        {/* Ready to optimize button */}
        {!optimization && readyToOptimize && (
          <div>
            <p style={{ margin: '0 0 10px', fontSize: 'var(--fs-sm)', color: 'var(--ink)' }}>
              Benchmark complete. Ready to evaluate lowest-cost passing models.
            </p>
            <button
              type="button"
              className="btn-primary"
              disabled={demo || !api || busy}
              onClick={startOptimize}
              style={{ width: '100%' }}
            >
              {busy ? 'Evaluating…' : 'Get recommendation'}
            </button>
          </div>
        )}

        {/* Optimization Decision Headline */}
        {optimization && (
          <div>
            <div
              className="decision-headline"
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '18px',
                fontWeight: 600,
                color: headline.kind === 'recommended' ? 'var(--ink)' : 'var(--muted)',
                lineHeight: 1.35,
                margin: '0 0 4px',
              }}
            >
              {headline.headline}
            </div>
            {headline.subline && (
              <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: 0 }}>
                {headline.subline}
              </p>
            )}
          </div>
        )}

        {/* Patch Diff Section */}
        {optimization && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {patch?.review_diff ? (
              <div style={{ border: '1px solid var(--rule)', borderRadius: 'var(--r-ctrl)', overflow: 'hidden' }}>
                <div style={{ padding: '6px 12px', background: 'var(--paper)', borderBottom: '1px solid var(--rule)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)' }}>
                    {targetFile?.file_path ?? 'app.py'}
                  </span>
                </div>
                <DiffViewer content={patch.review_diff} />
              </div>
            ) : patchState.status === 'loading' || reviewState.status === 'loading' ? (
              <div className="skeleton" style={{ height: 100, borderRadius: 'var(--r-ctrl)' }} />
            ) : null}

            {/* Reassurance line */}
            <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
              Only the model name changes. Tests on the sample app: not run.
            </div>

            {/* Operation alerts */}
            {applyState.data && (
              <div className="inline-alert success" role="status">
                Patch applied. Backup saved at <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)' }}>{applyState.data.applied_files[0]?.backup_path ?? '—'}</code>
              </div>
            )}

            {applyState.error && (
              <div className="inline-alert error" role="alert">
                {applyState.error.kind}: {applyState.error.message}
                {applyState.error.code === 'source_conflict' && (
                  <div style={{ marginTop: 4 }}>
                    Source conflict (409): the file has changed since the patch was created. Rescan before applying.
                  </div>
                )}
              </div>
            )}

            {/* Primary Filled Apply Button */}
            {patch && !applyState.data && (
              <div style={{ marginTop: 8 }}>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={demo || !api || applyState.status === 'loading'}
                  onClick={() => {
                    const count = patch.manifest.files.length;
                    if (window.confirm(`Apply model changes to ${count} file(s)?`)) {
                      void applyOperation.run(s => api!.applyPatch(patch.manifest.patch_id, s)).then(result => {
                        if (result) onApplySuccess?.(result);
                      });
                    }
                  }}
                  style={{ width: '100%', height: 38 }}
                >
                  {applyState.status === 'loading' ? 'Applying patch…' : 'Apply patch'}
                </button>
                <div style={{ textAlign: 'center', fontSize: '11px', color: 'var(--muted)', marginTop: 6 }}>
                  Saves {targetFileName}.bak first
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

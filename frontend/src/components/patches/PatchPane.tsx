import { useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Optimization, Scan, Patch, PatchAccepted, Validation } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { provenance } from '../../services/presentation.ts';
import { canPropose, validationView } from '../../services/patches.ts';
import { OperationStatus } from '../OperationStatus.tsx';

export function PatchEvidence({ proposal }: { proposal: Patch }) {
  const m = proposal.manifest;
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', margin: '8px 0' }}>
        <p className="evidence-warning" style={{ margin: 0 }}>{provenance(m.provenance)}</p>
        <span style={{ fontSize: '12px', color: 'var(--cr-subtle)' }}>
          Status: <strong style={{ color: 'var(--cr-pass)' }}>{m.status}</strong>
        </span>
      </div>

      <p>Proposal <code>{m.patch_id}</code>: {m.status}. Created {new Date(m.created_at).toLocaleString()}. This is a review artifact; target source is unchanged.</p>
      <p>Analysis <code>{m.analysis_id}</code>; optimization <code>{m.optimization_id}</code>. Coverage: {m.complete_for_requested_nodes ? 'complete for requested nodes' : 'partial or unavailable'}.</p>

      <details style={{ margin: '8px 0' }}>
        <summary style={{ cursor: 'pointer', color: 'var(--cr-muted)', fontSize: 'var(--cr-fs-xs)' }}>Artifact identities</summary>
        <dl>
          <dt>Proposal digest</dt><dd><code>{proposal.digest}</code></dd>
          <dt>Artifact digest</dt><dd><code>{proposal.artifact_digest}</code></dd>
          <dt>Source manifest</dt><dd><code>{m.source_manifest_digest}</code></dd>
        </dl>
      </details>

      {m.files.map(f => (
        <details key={f.file_path} style={{ margin: '8px 0', background: 'var(--cr-surface-2)', padding: '10px 14px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600, color: 'var(--cr-text)', fontSize: '13px' }}>
            {f.file_path}: {f.edits.length} model-literal edits
          </summary>
          <ul style={{ paddingLeft: '20px', margin: '8px 0', fontSize: '12px' }}>
            {f.edits.map(e => (
              <li key={e.node_id} style={{ margin: '4px 0' }}>
                <code>{e.node_id}</code>: original UTF-8 bytes {e.start_byte}–{e.end_byte}; <code>{e.old_model_id}</code> → <code>{e.proposed_model_id}</code>
              </li>
            ))}
          </ul>
        </details>
      ))}

      {m.omissions.length > 0 && (
        <>
          <h3>Explicit omissions</h3>
          <ul>
            {m.omissions.map(o => (
              <li key={o.node_id}>{o.node_id}: {o.reason}</li>
            ))}
          </ul>
        </>
      )}

      <details style={{ margin: '12px 0' }} open>
        <summary style={{ cursor: 'pointer', color: 'var(--cr-accent)', fontSize: 'var(--cr-fs-xs)', fontWeight: 600 }}>
          Review literal-spans.v1 artifact (not an apply command)
        </summary>
        <p style={{ margin: '6px 0', fontSize: '12px' }}>
          This review format preserves literal byte spans. It is not a standard unified diff or an applied change.
        </p>
        <pre>{proposal.review_diff || 'No editable spans available.'}</pre>
      </details>
    </>
  );
}
export function ValidationEvidence({ report, historical }: { report: Validation; historical: boolean }) {
  const view = validationView(report, historical); const r = report.result;
  return (
    <article aria-labelledby="report-title" style={{ marginTop: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', margin: '8px 0' }}>
        <h3 id="report-title" style={{ margin: 0 }}>Static validation: {r.status}</h3>
        <span
          style={{
            fontSize: '11px',
            fontWeight: 600,
            padding: '3px 8px',
            borderRadius: '4px',
            background: r.status === 'validated' ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 191, 36, 0.12)',
            color: r.status === 'validated' ? 'var(--cr-pass)' : 'var(--cr-warn)',
          }}
        >
          {r.status}
        </span>
      </div>

      <p className="evidence-warning">{provenance(r.provenance)}</p>
      <p>{view.outcome}</p>
      <p className="evidence-warning">{view.freshness}</p>
      <p>{view.limitation}</p>

      <dl>
        <dt>Report ID</dt><dd><code>{report.validation_id}</code></dd>
        <dt>Proposal ID</dt><dd><code>{r.patch_id}</code></dd>
        <dt>Analysis ID</dt><dd><code>{r.analysis_id}</code></dd>
        <dt>Observed at</dt><dd><time dateTime={report.checked_at}>{new Date(report.checked_at).toLocaleString()}</time></dd>
        <dt>Validator / grammar</dt><dd>{report.validator_version ?? 'literal-static.v1'} / Python {report.grammar_target ?? '3.11'}</dd>
        <dt>Actual parser runtime</dt><dd>{report.python_version} (grammar target is not runtime validation)</dd>
        <dt>Reason</dt><dd>{r.reason}</dd>
        <dt>Proposal structure</dt><dd>{r.structure}</dd>
        <dt>Source evidence</dt><dd>{r.source_evidence}</dd>
        <dt>Source identity at observation</dt><dd>{r.source_identity}</dd>
        <dt>Requested-node coverage</dt><dd>{r.complete ? 'complete' : 'incomplete'}; {r.omitted_nodes} omitted nodes</dd>
      </dl>

      <p>not_checked: no completed determination. not_applicable: the source encoding is unsupported for this transformation.</p>

      {(r.files ?? []).length === 0 ? (
        <p>No per-file checks established in this observation.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <caption>Checks established at the observation time</caption>
            <thead>
              <tr>
                <th>File</th>
                <th>Spans</th>
                <th>Candidate</th>
                <th>Syntax</th>
                <th>AST preservation</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {r.files!.map(f => (
                <tr key={f.file_path}>
                  <td><code>{f.file_path}</code></td>
                  <td className="num">{f.spans}</td>
                  <td><code>{f.candidate}</code></td>
                  <td>
                    <span style={{ color: f.syntax === 'passed' ? 'var(--cr-pass)' : 'var(--cr-warn)' }}>
                      {f.syntax}
                    </span>
                  </td>
                  <td>{f.ast_preservation}</td>
                  <td>
                    {f.reason}
                    {f.diagnostic && (
                      <p style={{ margin: '4px 0 0', color: 'var(--cr-fail)' }}>
                        {f.diagnostic.code ?? 'candidate_syntax_error'} at line {f.diagnostic.line_number ?? 'unavailable'}, column {f.diagnostic.column_number ?? 'unavailable'}
                      </p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(r.omissions ?? []).length > 0 && (
        <details style={{ margin: '8px 0' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--cr-muted)' }}>Omitted nodes and reasons</summary>
          <ul>
            {r.omissions!.map(o => (
              <li key={o.node_id}>{o.node_id}: {o.reason}</li>
            ))}
          </ul>
        </details>
      )}

      <details style={{ margin: '8px 0' }}>
        <summary style={{ cursor: 'pointer', color: 'var(--cr-muted)' }}>Bound report identities</summary>
        <dl>
          <dt>Report digest</dt><dd><code>{report.digest}</code></dd>
          <dt>Proposal digest</dt><dd><code>{r.proposal_digest}</code></dd>
          <dt>Source manifest digest</dt><dd><code>{r.source_manifest_digest}</code></dd>
        </dl>
      </details>
    </article>
  );
}
export function PatchPane({ api, demo, analysis, optimization }: { api?: ApiClient; demo: boolean; analysis?: Scan; optimization?: Optimization }) {
  const [patchId, setPatchId] = useState('');
  const [validationId, setValidationId] = useState('');
  const [created, creation] = useOperation<PatchAccepted>();
  const [review, reviewOperation] = useOperation<Patch>();
  const [validation, validationOperation] = useOperation<{ report: Validation; historical: boolean }>();
  const [applied, applyOperation] = useOperation<{ patch_id: string; status: string; applied_at: string; applied_files: { file_path: string; backup_path: string; edits_count: number }[] }>();
  const busy = [created, review, validation, applied].some(s => s.status === 'loading');
  const disabled = demo || !api || busy;

  const readPatch = (id: string) => {
    validationOperation.reset();
    applyOperation.reset();
    void reviewOperation.run(s => api!.patch(id, s));
  };

  return (
    <section aria-labelledby="patch-title">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <h2 id="patch-title">4. Proposal review, validation & apply</h2>
        {canPropose(analysis, optimization) && (
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cr-pass)', background: 'rgba(52, 211, 153, 0.1)', padding: '3px 8px', borderRadius: '4px' }}>
            ✓ Ready to propose
          </span>
        )}
      </div>
      <p>Review and safely apply compiler-optimized model literals. An automatic backup (.bak) is created before any file is touched.</p>

      <button
        disabled={disabled || !canPropose(analysis, optimization)}
        onClick={() => {
          reviewOperation.reset();
          validationOperation.reset();
          applyOperation.reset();
          void creation.run(s => api!.createPatch({
            analysis_id: analysis!.analysis_id,
            optimization_id: optimization!.optimization_id!,
            transformation: 'literal_model_id.v1'
          }, s)).then(result => {
            if (result) {
              setPatchId(result.patch_id);
              readPatch(result.patch_id);
            }
          });
        }}
        style={{ margin: '8px 0' }}
      >
        Create review proposal from approved optimization
      </button>

      {!canPropose(analysis, optimization) && (
        <p>Creation requires a persisted optimization bound to this analysis. Run a benchmark and request optimization to generate a proposal.</p>
      )}

      <OperationStatus state={created} cancel={creation.cancel} />
      {created.data && (
        <p>Stored proposal <code>{created.data.patch_id}</code>: {created.data.status}; changed nodes {created.data.changed_nodes}, omitted {created.data.omitted_nodes}.</p>
      )}

      <form onSubmit={e => { e.preventDefault(); readPatch(patchId.trim()); }}>
        <label>
          Existing proposal ID
          <input
            required
            pattern="patch_[0-9a-f]{32}"
            value={patchId}
            disabled={disabled}
            onChange={e => {
              setPatchId(e.target.value);
              reviewOperation.reset();
              validationOperation.reset();
              applyOperation.reset();
            }}
            placeholder="patch_0123456789abcdef0123456789abcdef"
          />
        </label>
        <button disabled={disabled}>Review proposal</button>
      </form>

      <OperationStatus state={review} cancel={reviewOperation.cancel} />

      {review.data && (
        <>
          <PatchEvidence proposal={review.data} />
          {review.data.manifest.files.length > 0 && (
            <div style={{ marginTop: '1rem', padding: '16px', border: '1px solid var(--cr-pass)', borderRadius: 'var(--cr-r-control)', background: 'rgba(52, 211, 153, 0.05)' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--cr-pass)' }}>Apply Verified Patch</h4>
              <p style={{ margin: '0 0 0.75rem 0' }}>Atomically update model literals in your source code with automatic <code>.bak</code> backups.</p>
              <button
                disabled={disabled || applied.status === 'loading'}
                style={{ backgroundColor: '#34D399', color: '#0B0D12', fontWeight: 600, padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', border: 'none' }}
                onClick={() => {
                  if (window.confirm(`Apply verified model changes to ${review.data!.manifest.files.length} file(s)?`)) {
                    void applyOperation.run(s => api!.applyPatch(review.data!.manifest.patch_id, s));
                  }
                }}
              >
                {applied.status === 'loading' ? 'Applying to files...' : 'Apply Verified Patch to Codebase'}
              </button>
              <OperationStatus state={applied} cancel={applyOperation.cancel} />
              {applied.data && (
                <div role="status" style={{ marginTop: '0.75rem', color: '#34D399' }}>
                  <strong>✓ Patch successfully applied!</strong>
                  <ul style={{ margin: '0.5rem 0 0 1.25rem' }}>
                    {applied.data.applied_files.map(f => (
                      <li key={f.file_path}>
                        Updated <code>{f.file_path}</code> ({f.edits_count} edit). Backup created at <code>{f.backup_path}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}

      <button
        disabled={disabled || !/^patch_[0-9a-f]{32}$/.test(patchId.trim())}
        onClick={() => {
          void validationOperation.run(async s => ({
            report: await api!.validate(patchId.trim(), s),
            historical: false
          })).then(value => {
            if (value) setValidationId(value.report.validation_id);
          });
        }}
        style={{ margin: '10px 0' }}
      >
        Validate proposal now (static only)
      </button>
      <p>Validation verifies that the proposed changes strictly preserve AST semantics.</p>

      <form onSubmit={e => {
        e.preventDefault();
        reviewOperation.reset();
        void validationOperation.run(async s => ({
          report: await api!.validation(validationId.trim(), s),
          historical: true
        })).then(value => {
          if (value) setPatchId(value.report.result.patch_id);
        });
      }}>
        <label>
          Historical validation report ID
          <input
            required
            pattern="validation_[0-9a-f]{64}"
            value={validationId}
            disabled={disabled}
            onChange={e => {
              setValidationId(e.target.value);
              validationOperation.reset();
            }}
            placeholder="validation_0123456789abcdef..."
          />
        </label>
        <button disabled={disabled}>Retrieve historical report</button>
      </form>

      <OperationStatus state={validation} cancel={validationOperation.cancel} />

      {validation.data && (
        <>
          <ValidationEvidence report={validation.data.report} historical={validation.data.historical} />
          <button disabled={disabled} onClick={() => readPatch(validation.data!.report.result.patch_id)} style={{ marginTop: '10px' }}>
            Review associated proposal
          </button>
        </>
      )}
    </section>
  );
}

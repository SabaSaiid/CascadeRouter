import { useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan, Optimization } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { demoScan } from '../../services/demo.ts';
import { provenance, scanSummary } from '../../services/presentation.ts';
import { callName, callResult, type WorkflowStep } from '../../services/display.ts';
import { AgentGraph } from './AgentGraph.tsx';

// ---------------------------------------------------------------------------
// Call list (the connected call view, default)
// ---------------------------------------------------------------------------

function CallList({
  scan,
  selected,
  onSelect,
  optimization,
  graphEdges,
}: {
  scan: Scan;
  selected?: string;
  onSelect: (id: string) => void;
  optimization?: Optimization;
  graphEdges: readonly (readonly [string, string])[];
}) {
  const hasEdges = graphEdges.length > 0;

  return (
    <div style={{ position: 'relative' }}>
      {/* Thin vertical graph line */}
      {hasEdges && (
        <div style={{
          position: 'absolute',
          left: 24,
          top: 0,
          bottom: 0,
          width: 1,
          background: 'var(--rule)',
          pointerEvents: 'none',
          zIndex: 0,
        }} aria-hidden="true" />
      )}

      {scan.nodes.length === 0 ? (
        <p style={{ padding: '20px 16px', fontSize: 'var(--fs-sm)', color: 'var(--muted)', margin: 0 }}>
          No LLM calls found. {scanSummary(scan).empty}
        </p>
      ) : (
        <>
          {scan.nodes.map(node => {
            const isSelected = selected === node.node_id;
            const cr = callResult(node.node_id, optimization);
            const hasResult = cr.change !== null;

            return (
              <button
                key={node.node_id}
                onClick={() => onSelect(node.node_id)}
                aria-pressed={isSelected}
                className={`call-row${isSelected ? ' selected' : ''}`}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                  borderRadius: 0,
                  padding: 0,
                  cursor: 'pointer',
                  paddingLeft: hasEdges ? 44 : 16,
                }}
              >
                {/* Graph dot */}
                {hasEdges && (
                  <span
                    className={`graph-dot${isSelected ? ' selected' : ''}${hasResult && cr.kind === 'recommended' ? ' has-result' : ''}`}
                    aria-hidden="true"
                  />
                )}

                <span style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 10, paddingBottom: 10 }}>
                  <span className="call-row-name">{callName(node)}</span>
                  <span className="call-row-loc">
                    {node.file_path}:{node.line_number}
                  </span>
                  {cr.change && (
                    <span className="call-row-result">
                      {cr.kind === 'recommended' && cr.baselineName && cr.selectedName ? (
                        <>
                          <span style={{ color: 'var(--muted)' }}>{cr.baselineName} to </span>
                          <span style={{ color: 'var(--gain)', fontWeight: 600 }}>{cr.selectedName}</span>
                        </>
                      ) : (
                        <span style={{ color: cr.kind === 'retained' ? 'var(--muted)' : 'inherit' }}>{cr.change}</span>
                      )}
                    </span>
                  )}
                </span>
              </button>
            );
          })}

          {hasEdges && (
            <p style={{ padding: '8px 16px', fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: 0, borderTop: '1px solid var(--rule)' }}>
              Lines show which call feeds the next.
            </p>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RepositoryPane
// ---------------------------------------------------------------------------

export function ScanFindings({ scan, selected, onSelect }: { scan: Scan; selected?: string; onSelect: (id: string) => void }) {
  const summary = scanSummary(scan);
  const [page, setPage] = useState(0);
  const nodes = scan.nodes.slice(page * 50, page * 50 + 50);

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', margin: '8px 0' }}>
        <p className="evidence-warning" style={{ margin: 0 }}>{provenance(scan.data_source)}</p>
        <span style={{ fontSize: '12px', color: 'var(--cr-subtle)' }}>
          Analysis: <code>{scan.analysis_id}</code> — observed {new Date(scan.timestamp).toLocaleString()}
        </span>
      </div>

      <p>{summary.coverage}. Read {scan.scanned_files_count} of {scan.discovered_files_count} discovered files; {scan.total_source_bytes_read} source bytes. {summary.graph}.</p>
      {summary.empty && <p>{summary.empty}</p>}

      {!summary.empty && nodes.length > 0 && (
        <div style={{ marginTop: '12px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', margin: '12px 0' }}>
            <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
              Showing {page * 50 + 1}–{page * 50 + nodes.length} of {scan.nodes.length} findings. Select one for benchmarking.
            </span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table aria-label="Statically discovered LLM calls" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--fs-xs)' }}>
              <caption>Statically discovered LLM calls</caption>
              <thead>
                <tr>
                  <th style={{ width: 120, textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Finding</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Location</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)', fontWeight: 600 }}>Model evidence</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map(n => {
                  const isSelected = selected === n.node_id;
                  return (
                    <tr
                      key={n.node_id}
                      style={{
                        background: isSelected ? 'color-mix(in srgb, var(--navy) 6%, var(--sheet))' : undefined,
                        borderLeft: isSelected ? '3px solid var(--navy)' : '3px solid transparent',
                      }}
                    >
                      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--rule)' }}>
                        <button
                          aria-pressed={isSelected}
                          onClick={() => onSelect(n.node_id)}
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '3px 8px',
                            borderRadius: 'var(--r-chip)',
                            background: isSelected ? 'var(--navy)' : 'var(--chip-bg)',
                            border: '1px solid',
                            borderColor: isSelected ? 'var(--navy)' : 'var(--rule)',
                            color: isSelected ? '#ffffff' : 'var(--ink)',
                            cursor: 'pointer',
                          }}
                        >
                          {n.node_id}
                        </button>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', padding: '6px 8px', borderBottom: '1px solid var(--rule)', color: 'var(--muted)' }}>
                        {n.file_path}:{n.line_number}
                        <br />
                        <span style={{ color: 'var(--muted)' }}>{n.function_name ?? 'Module scope'}</span>
                      </td>
                      <td style={{ fontSize: '11px', padding: '6px 8px', borderBottom: '1px solid var(--rule)' }}>
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            padding: '1px 6px',
                            borderRadius: 'var(--r-chip)',
                            background: n.current_model ? 'var(--gain-tint)' : 'var(--caution-tint)',
                            color: n.current_model ? 'var(--gain)' : 'var(--caution)',
                          }}
                        >
                          {n.current_model ?? 'Model unavailable'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {scan.nodes.length > 50 && (
            <div style={{ display: 'flex', gap: 8, padding: '8px 0', justifyContent: 'flex-end' }}>
              <button className="btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
              <button className="btn-ghost" disabled={(page + 1) * 50 >= scan.nodes.length} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          )}
        </div>
      )}

      {[...scan.scan_diagnostics, ...scan.graph_diagnostics].length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--caution)', fontSize: 'var(--fs-xs)' }}>
            Coverage diagnostics ({scan.scan_diagnostics.length + scan.graph_diagnostics.length})
          </summary>
          <ul style={{ paddingLeft: 20, margin: '8px 0', fontSize: 12 }}>
            {[...scan.scan_diagnostics, ...scan.graph_diagnostics].map((d, i) => (
              <li key={i} style={{ margin: '4px 0', color: 'var(--muted)' }}>
                <strong style={{ color: d.level === 'warning' ? 'var(--caution)' : 'var(--loss)' }}>{d.level}</strong>: {d.code}
                {d.location && ` — ${d.location.file_path}`}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

export function RepositoryPane({
  api,
  demo,
  onAnalysis,
  selected,
  onSelect,
  step,
  optimization,
}: {
  api?: ApiClient;
  demo: boolean;
  onAnalysis: (scan?: Scan) => void;
  selected?: string;
  onSelect: (id: string) => void;
  step: WorkflowStep;
  optimization?: Optimization;
}) {
  const [path, setPath] = useState('');
  const [showGraph, setShowGraph] = useState(false);
  const [state, operation] = useOperation<Scan>();
  const scan = demo ? demoScan : state.data;
  const summary = scan ? scanSummary(scan) : null;

  const isCurrent = step === 'scan';
  const busy = state.status === 'loading';

  const submit = () => {
    onAnalysis(undefined);
    void operation.run(s => api!.scan(path.trim(), s)).then(result => { if (result) onAnalysis(result); });
  };

  return (
    <aside className="left-pane" aria-label="Repository">
      {/* Path field + actions */}
      <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid var(--rule)' }}>
        <p className="pane-title" style={{ marginBottom: 8 }}>Repository</p>

        <form onSubmit={e => { e.preventDefault(); submit(); }} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label className="field-label" htmlFor="repo-path">
            Repository path
            <input
              id="repo-path"
              className="field-input"
              value={path}
              onChange={e => setPath(e.target.value)}
              autoComplete="off"
              disabled={demo}
              placeholder="e.g. . or /path/to/repo"
            />
          </label>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            {/* Only one filled primary button when this is the current step */}
            {isCurrent && !scan ? (
              <button
                type="submit"
                className="btn-primary"
                disabled={demo || !api || busy || !path.trim()}
                style={{ minWidth: 0, flex: 1 }}
              >
                {busy ? 'Scanning…' : 'Scan repository'}
              </button>
            ) : (
              <button
                type="submit"
                className="btn-ghost"
                disabled={demo || !api || busy || !path.trim()}
              >
                {busy ? 'Scanning…' : scan ? 'Scan again' : 'Scan repository'}
              </button>
            )}
            <button type="button" className="btn-ghost" disabled={demo || busy} onClick={() => setPath('examples/customer_support_agent')}>
              Load Sample Agent
            </button>
            <button type="button" className="btn-ghost" disabled={demo || busy} onClick={() => setPath('.')}>
              Use Current Repo (.)
            </button>
          </div>
        </form>

        {/* Error */}
        {state.error && !busy && (
          <div className="inline-alert error" style={{ marginTop: 8 }}>
            {state.error.kind}: {state.error.message}
            {state.error.code && <code style={{ marginLeft: 4 }}>{state.error.code}</code>}
          </div>
        )}

        {/* Cancelled */}
        {state.status === 'cancelled' && (
          <div className="inline-alert warn" style={{ marginTop: 8 }}>
            This is taking longer than expected. The backend may still finish. Check for the result before submitting again.
            <button className="btn-link" style={{ marginLeft: 8 }} onClick={submit}>Check result</button>
          </div>
        )}

        {/* Scan summary */}
        {scan && summary && (
          <div style={{ marginTop: 8, fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
            {scan.scanned_files_count} file{scan.scanned_files_count !== 1 ? 's' : ''} scanned
            {scan.detected_framework && `, ${scan.detected_framework}`}
          </div>
        )}
      </div>

      {/* Loading skeletons */}
      {busy && (
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[80, 60, 70].map((w, i) => (
            <div key={i} className="skeleton" style={{ height: 40, width: `${w}%`, borderRadius: 'var(--r-ctrl)' }} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!scan && !busy && (
        <div style={{ padding: '20px 16px', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', textAlign: 'center', margin: 0 }}>
            No analysis result loaded. Scan a repository to find LLM calls.
          </p>
        </div>
      )}

      {/* Call list header */}
      {scan && !busy && (
        <>
          <div style={{ padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--ink)' }}>
              LLM calls <span style={{ color: 'var(--muted)', fontWeight: 400 }}>{scan.nodes.length} found</span>
            </span>
            {scan.graph_edges.length > 0 && (
              <button
                className="btn-link"
                onClick={() => setShowGraph(!showGraph)}
                style={{ fontSize: 'var(--fs-xs)' }}
              >
                {showGraph ? 'View list' : 'View graph'}
              </button>
            )}
          </div>

          {showGraph ? (
            <div style={{ padding: '0 0 16px' }}>
              <AgentGraph scan={scan} onSelect={onSelect} selected={selected} />
            </div>
          ) : (
            <CallList
              scan={scan}
              selected={selected}
              onSelect={onSelect}
              optimization={optimization}
              graphEdges={scan.graph_edges}
            />
          )}
        </>
      )}
    </aside>
  );
}

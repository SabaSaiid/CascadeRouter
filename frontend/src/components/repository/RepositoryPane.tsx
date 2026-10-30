import { useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { demoScan } from '../../services/demo.ts';
import { provenance, scanSummary } from '../../services/presentation.ts';
import { OperationStatus } from '../OperationStatus.tsx';
import { AgentGraph } from './AgentGraph.tsx';

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

      {/* Metric Cards Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', margin: '14px 0' }}>
        <div style={{ background: 'var(--cr-surface-2)', padding: '12px 16px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <div style={{ fontSize: '11px', color: 'var(--cr-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Coverage</div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--cr-text)', marginTop: '4px' }}>{summary.coverage}</div>
        </div>
        <div style={{ background: 'var(--cr-surface-2)', padding: '12px 16px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <div style={{ fontSize: '11px', color: 'var(--cr-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Files Inspected</div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--cr-text)', marginTop: '4px' }}>
            <span className="num" style={{ color: 'var(--cr-accent)' }}>{scan.scanned_files_count}</span>
            <span style={{ color: 'var(--cr-subtle)', fontWeight: 400 }}> / {scan.discovered_files_count} files</span>
          </div>
        </div>
        <div style={{ background: 'var(--cr-surface-2)', padding: '12px 16px', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)' }}>
          <div style={{ fontSize: '11px', color: 'var(--cr-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Source Data</div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--cr-text)', marginTop: '4px' }}>
            <span className="num" style={{ color: 'var(--cr-pass)' }}>{scan.total_source_bytes_read.toLocaleString()}</span>
            <span style={{ color: 'var(--cr-subtle)', fontWeight: 400 }}> bytes</span>
          </div>
        </div>
      </div>

      <p>{summary.coverage}. Read {scan.scanned_files_count} of {scan.discovered_files_count} discovered files; {scan.total_source_bytes_read} source bytes. {summary.graph}.</p>
      {summary.empty && <p>{summary.empty}</p>}

      {scan.nodes.length > 0 && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginTop: '16px' }}>
            <p style={{ margin: 0, fontWeight: 500, color: 'var(--cr-text)' }}>
              Showing {page * 50 + 1}–{page * 50 + nodes.length} of {scan.nodes.length} findings. Select a finding for the local benchmark plan.
            </p>
            <span style={{ fontSize: '11px', color: 'var(--cr-subtle)' }}>
              Click any finding ID to select it for benchmarking
            </span>
          </div>

          <div className="table-scroll">
            <table>
              <caption>Statically discovered LLM calls</caption>
              <thead>
                <tr>
                  <th style={{ width: '220px' }}>Finding</th>
                  <th style={{ width: '240px' }}>Location</th>
                  <th>Model evidence</th>
                  <th>Prompt / schema evidence</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map(n => {
                  const isSelected = selected === n.node_id;
                  return (
                    <tr
                      key={n.node_id}
                      style={{
                        background: isSelected ? 'rgba(77, 133, 255, 0.08)' : undefined,
                        borderLeft: isSelected ? '3px solid var(--cr-accent)' : '3px solid transparent',
                        transition: 'background 140ms ease',
                      }}
                    >
                      <td>
                        <button
                          aria-pressed={isSelected}
                          onClick={() => onSelect(n.node_id)}
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '12px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '6px',
                            background: isSelected ? 'var(--cr-accent)' : 'rgba(77, 133, 255, 0.12)',
                            borderColor: isSelected ? 'var(--cr-accent)' : 'rgba(77, 133, 255, 0.3)',
                            color: isSelected ? '#ffffff' : '#A5C0FF',
                            boxShadow: isSelected ? '0 0 10px rgba(77, 133, 255, 0.4)' : 'none',
                          }}
                        >
                          {n.node_id}
                        </button>
                        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--cr-subtle)', margin: '4px 0 0' }}>
                          {n.call_signature}
                        </p>
                      </td>
                      <td>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--cr-text)' }}>
                          {n.file_path}:{n.line_number}:{n.column_number} (AST UTF-8 byte column)
                        </div>
                        <p style={{ margin: '4px 0 0', fontSize: '11px', color: 'var(--cr-subtle)' }}>
                          {n.function_name ?? 'Module scope'}
                        </p>
                      </td>
                      <td>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                          <span
                            style={{
                              fontSize: '11px',
                              fontWeight: 600,
                              fontFamily: 'var(--font-mono)',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              background: n.current_model ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 191, 36, 0.12)',
                              border: n.current_model ? '1px solid rgba(52, 211, 153, 0.3)' : '1px solid rgba(251, 191, 36, 0.3)',
                              color: n.current_model ? 'var(--cr-pass)' : 'var(--cr-warn)',
                            }}
                          >
                            {n.current_model ?? 'Model unavailable'}
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: '11px', color: 'var(--cr-muted)' }}>
                          {n.model_resolution}{n.model_reference && `: ${n.model_reference}`}
                        </p>
                      </td>
                      <td style={{ fontSize: '12px' }}>
                        Prompt: {n.prompt_resolution}; schema: {n.schema_resolution}. Source contents are not returned.
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="control-row" style={{ justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', color: 'var(--cr-subtle)' }}>
              Page {page + 1} of {Math.max(1, Math.ceil(scan.nodes.length / 50))}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous findings</button>
              <button disabled={(page + 1) * 50 >= scan.nodes.length} onClick={() => setPage(page + 1)}>Next findings</button>
            </div>
          </div>
        </>
      )}

      {[...scan.scan_diagnostics, ...scan.graph_diagnostics].length > 0 && (
        <details style={{ marginTop: '12px' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--cr-warn)', fontSize: 'var(--cr-fs-xs)' }}>
            Coverage and analysis diagnostics ({scan.scan_diagnostics.length + scan.graph_diagnostics.length})
          </summary>
          <ul style={{ paddingLeft: '20px', margin: '8px 0', fontSize: '12px' }}>
            {[...scan.scan_diagnostics, ...scan.graph_diagnostics].map((d, i) => (
              <li key={i} style={{ margin: '4px 0', color: 'var(--cr-muted)' }}>
                <strong style={{ color: d.level === 'warning' ? 'var(--cr-warn)' : 'var(--cr-fail)' }}>{d.level}</strong>: {d.code}
                {d.location && ` — ${d.location.file_path}`}
              </li>
            ))}
          </ul>
        </details>
      )}

      <AgentGraph scan={scan} onSelect={onSelect} selected={selected} />
    </>
  );
}

export function RepositoryPane({ api, demo, onAnalysis, selected, onSelect }: { api?: ApiClient; demo: boolean; onAnalysis: (scan?: Scan) => void; selected?: string; onSelect: (id: string) => void }) {
  const [path, setPath] = useState('');
  const [analysisId, setAnalysisId] = useState('');
  const [state, operation] = useOperation<Scan>();
  const scan = demo ? demoScan : state.data;

  const submit = (stored: boolean) => {
    onAnalysis(undefined);
    void operation.run(s => stored ? api!.analysis(analysisId.trim(), s) : api!.scan(path.trim(), s)).then(result => { if (result) onAnalysis(result); });
  };

  return (
    <section aria-labelledby="scan-title">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <h2 id="scan-title">1. Repository analysis</h2>
        {scan && (
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cr-pass)', background: 'rgba(52, 211, 153, 0.1)', padding: '3px 8px', borderRadius: '4px' }}>
            ✓ {scan.nodes.length} call sites discovered
          </span>
        )}
      </div>
      <p>Supply a path allowed by the backend. Scanning parses Python without importing or executing it. No scan starts automatically.</p>

      <form onSubmit={e => { e.preventDefault(); submit(false); }}>
        <label>
          Authorized repository path
          <input
            value={path}
            onChange={e => setPath(e.target.value)}
            required
            autoComplete="off"
            disabled={demo}
            placeholder="e.g. . or /absolute/path/to/repo"
          />
        </label>
        <div className="control-row">
          <button disabled={demo || !api || state.status === 'loading' || !path.trim()}>Scan repository</button>
          <button type="button" disabled={demo || !api || state.status === 'loading'} onClick={() => setPath('.')}>Use Current Repo (.)</button>
        </div>
      </form>

      <form onSubmit={e => { e.preventDefault(); submit(true); }}>
        <label>
          Stored analysis ID
          <input
            value={analysisId}
            onChange={e => setAnalysisId(e.target.value)}
            required
            pattern="analysis_[0-9a-f]{32}"
            disabled={demo}
            placeholder="analysis_0123456789abcdef0123456789abcdef"
          />
        </label>
        <button disabled={demo || !api || state.status === 'loading'}>Retrieve analysis</button>
      </form>

      <OperationStatus state={state} cancel={operation.cancel} />

      {!scan && state.status !== 'loading' && (
        <div style={{ padding: '16px', background: 'var(--cr-surface-2)', borderRadius: 'var(--cr-r-control)', border: '1px solid var(--cr-line)', margin: '14px 0' }}>
          <p style={{ margin: 0 }}>
            No analysis result loaded. Supply a repository or retrieve a stored analysis; retry the form after correcting any reported error.
          </p>
        </div>
      )}

      {scan && <ScanFindings key={scan.analysis_id} scan={scan} selected={selected} onSelect={onSelect} />}
    </section>
  );
}

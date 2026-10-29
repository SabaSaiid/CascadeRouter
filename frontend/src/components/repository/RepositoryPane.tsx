import { useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { demoScan } from '../../services/demo.ts';
import { provenance, scanSummary } from '../../services/presentation.ts';
import { OperationStatus } from '../OperationStatus.tsx';
import { AgentGraph } from './AgentGraph.tsx';

export function ScanFindings({ scan, selected, onSelect }: { scan: Scan; selected?: string; onSelect: (id: string) => void }) {
  const summary = scanSummary(scan); const [page, setPage] = useState(0);
  const nodes = scan.nodes.slice(page * 50, page * 50 + 50);
  return <><p className="evidence-warning">{provenance(scan.data_source)}</p>
    <p><code>{scan.analysis_id}</code> — observed {new Date(scan.timestamp).toLocaleString()}</p>
    <p>{summary.coverage}. Read {scan.scanned_files_count} of {scan.discovered_files_count} discovered files; {scan.total_source_bytes_read} source bytes. {summary.graph}.</p>
    {summary.empty && <p>{summary.empty}</p>}
    {scan.nodes.length > 0 && <><p>Showing {page * 50 + 1}–{page * 50 + nodes.length} of {scan.nodes.length} findings. Select a finding for the local benchmark plan.</p>
      <div className="table-scroll"><table><caption>Statically discovered LLM calls</caption><thead><tr><th>Finding</th><th>Location</th><th>Model evidence</th><th>Prompt / schema evidence</th></tr></thead><tbody>
        {nodes.map(n => <tr key={n.node_id}><td><button aria-pressed={selected === n.node_id} onClick={() => onSelect(n.node_id)}>{n.node_id}</button><p>{n.call_signature}</p></td>
          <td>{n.file_path}:{n.line_number}:{n.column_number} (AST UTF-8 byte column)<p>{n.function_name ?? 'Module scope'}</p></td>
          <td>{n.current_model ?? 'Model unavailable'}<p>{n.model_resolution}{n.model_reference && `: ${n.model_reference}`}</p></td>
          <td>Prompt: {n.prompt_resolution}; schema: {n.schema_resolution}. Source contents are not returned.</td></tr>)}
      </tbody></table></div>
      <div className="control-row"><button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous findings</button><button disabled={(page + 1) * 50 >= scan.nodes.length} onClick={() => setPage(page + 1)}>Next findings</button></div></>}
    {[...scan.scan_diagnostics, ...scan.graph_diagnostics].length > 0 && <details><summary>Coverage and analysis diagnostics</summary><ul>{[...scan.scan_diagnostics, ...scan.graph_diagnostics].map((d, i) => <li key={i}>{d.level}: {d.code}{d.location && ` — ${d.location.file_path}`}</li>)}</ul></details>}
    <AgentGraph scan={scan} onSelect={onSelect} />
  </>;
}
export function RepositoryPane({ api, demo, onAnalysis, selected, onSelect }: { api?: ApiClient; demo: boolean; onAnalysis: (scan?: Scan) => void; selected?: string; onSelect: (id: string) => void }) {
  const [path, setPath] = useState(''); const [analysisId, setAnalysisId] = useState('');
  const [state, operation] = useOperation<Scan>(); const scan = demo ? demoScan : state.data;
  const submit = (stored: boolean) => {
    onAnalysis(undefined);
    void operation.run(s => stored ? api!.analysis(analysisId.trim(), s) : api!.scan(path.trim(), s)).then(result => { if (result) onAnalysis(result); });
  };
  return <section aria-labelledby="scan-title"><h2 id="scan-title">1. Repository analysis</h2>
    <p>Supply a path allowed by the backend. Scanning parses Python without importing or executing it. No scan starts automatically.</p>
    <form onSubmit={e => { e.preventDefault(); submit(false); }}><label>Authorized repository path<input value={path} onChange={e => setPath(e.target.value)} required autoComplete="off" disabled={demo} /></label><button disabled={demo || !api || state.status === 'loading' || !path.trim()}>Scan repository</button></form>
    <form onSubmit={e => { e.preventDefault(); submit(true); }}><label>Stored analysis ID<input value={analysisId} onChange={e => setAnalysisId(e.target.value)} required pattern="analysis_[0-9a-f]{32}" disabled={demo} /></label><button disabled={demo || !api || state.status === 'loading'}>Retrieve analysis</button></form>
    <OperationStatus state={state} cancel={operation.cancel} />
    {!scan && state.status !== 'loading' && <p>No analysis result loaded. Supply a repository or retrieve a stored analysis; retry the form after correcting any reported error.</p>}
    {scan && <ScanFindings key={scan.analysis_id} scan={scan} selected={selected} onSelect={onSelect} />}
  </section>;
}

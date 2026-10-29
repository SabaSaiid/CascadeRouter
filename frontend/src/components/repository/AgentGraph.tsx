import { useState } from 'react';
import type { Scan } from '../../services/contracts.ts';
import { graphView } from '../../services/graph.ts';
export function AgentGraph({ scan, onSelect }: { scan: Scan; onSelect: (id: string) => void }) {
  const [page, setPage] = useState(0); const view = graphView(scan); const edges = view.edges.slice(page * 50, page * 50 + 50);
  return <div aria-labelledby="graph-title"><h3 id="graph-title">Evidence-based agent graph</h3>
    <p>{view.coverage}. Only backend-reported data dependency edges are shown. An absent edge does not prove independence or execution order. Edge evidence details are private and are not returned by this API.</p>
    {edges.length === 0 ? <p>No dependency edges observed in this result.</p> : <><p>Edges {page * 50 + 1}–{page * 50 + edges.length} of {view.edges.length}. Fan-in and fan-out are retained as separate edges.</p>
      <div className="table-scroll"><table><caption>Observed data dependencies</caption><thead><tr><th>Producer finding</th><th>Relationship</th><th>Consumer finding</th></tr></thead><tbody>
        {edges.map(e => <tr key={`${e.from}:${e.to}`}><td><button onClick={() => onSelect(e.from)} aria-label={`Select producer ${e.from}`}>{e.from}</button></td><td>data dependency →</td><td><button onClick={() => onSelect(e.to)} aria-label={`Select consumer ${e.to}`}>{e.to}</button></td></tr>)}
      </tbody></table></div><div className="control-row"><button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous edges</button><button disabled={(page + 1) * 50 >= view.edges.length} onClick={() => setPage(page + 1)}>Next edges</button></div></>}
    <p>{view.unconnected.length} findings have no observed connecting edge.</p>
    {view.unconnected.length > 0 && <details><summary>Findings without observed connections (first 50)</summary><ul>{view.unconnected.slice(0, 50).map(n => <li key={n.node_id}><button onClick={() => onSelect(n.node_id)}>{n.node_id}</button></li>)}</ul></details>}
  </div>;
}

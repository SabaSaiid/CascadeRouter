import { useMemo, useState } from 'react';
import type { Scan } from '../../services/contracts.ts';
import { graphView } from '../../services/graph.ts';

export function AgentGraph({ scan, onSelect, selected }: { scan: Scan; onSelect: (id: string) => void; selected?: string }) {
  const [page, setPage] = useState(0);
  const [activeTab, setActiveTab] = useState<'canvas' | 'table'>('canvas');
  const view = useMemo(() => graphView(scan), [scan]);
  const edges = view.edges.slice(page * 50, page * 50 + 50);

  // Compute 2D coordinates for visual SVG graph
  const layout = useMemo(() => {
    if (view.edges.length === 0) return null;
    const nodeIds = Array.from(new Set(view.edges.flatMap(e => [e.from, e.to])));
    // Assign layers (simple topological / dependency depth)
    const inDegree = new Map<string, number>(nodeIds.map(id => [id, 0]));
    for (const e of view.edges) inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1);

    const layer0 = nodeIds.filter(id => (inDegree.get(id) ?? 0) === 0);
    const layer1 = nodeIds.filter(id => (inDegree.get(id) ?? 0) > 0);

    const nodePositions = new Map<string, { x: number; y: number }>();
    const col0X = 140;
    const col1X = 540;
    const rowHeight = 76;

    layer0.forEach((id, idx) => {
      nodePositions.set(id, { x: col0X, y: 50 + idx * rowHeight });
    });
    layer1.forEach((id, idx) => {
      nodePositions.set(id, { x: col1X, y: 50 + idx * rowHeight });
    });

    const totalHeight = Math.max(220, Math.max(layer0.length, layer1.length) * rowHeight + 80);
    return { nodePositions, totalHeight, width: 700 };
  }, [view]);

  return (
    <div aria-labelledby="graph-title" style={{ marginTop: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <h3 id="graph-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ color: 'var(--cr-accent)' }}>⬡</span>
          Evidence-based agent graph
        </h3>
        {view.edges.length > 0 && (
          <div style={{ display: 'inline-flex', background: 'var(--cr-surface-2)', padding: '2px', borderRadius: '6px', border: '1px solid var(--cr-line)' }}>
            <button
              type="button"
              onClick={() => setActiveTab('canvas')}
              style={{
                padding: '4px 10px',
                fontSize: '11px',
                background: activeTab === 'canvas' ? 'var(--cr-surface-3)' : 'transparent',
                border: 'none',
                color: activeTab === 'canvas' ? 'var(--cr-text)' : 'var(--cr-muted)',
              }}
            >
              Visual Canvas
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('table')}
              style={{
                padding: '4px 10px',
                fontSize: '11px',
                background: activeTab === 'table' ? 'var(--cr-surface-3)' : 'transparent',
                border: 'none',
                color: activeTab === 'table' ? 'var(--cr-text)' : 'var(--cr-muted)',
              }}
            >
              Edge Table ({view.edges.length})
            </button>
          </div>
        )}
      </div>

      <p>
        <span
          style={{
            fontSize: '11px',
            padding: '2px 8px',
            borderRadius: '4px',
            background: scan.graph_complete ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 191, 36, 0.12)',
            color: scan.graph_complete ? 'var(--cr-pass)' : 'var(--cr-warn)',
            fontWeight: 600,
            marginRight: '8px',
            display: 'inline-block',
          }}
        >
          {view.coverage}
        </span>
        Only backend-reported data dependency edges are shown. An absent edge does not prove independence or execution order. Edge evidence details are private and are not returned by this API.
      </p>

      {edges.length === 0 ? (
        <div style={{ padding: '24px', textAlign: 'center', background: 'var(--cr-surface-2)', borderRadius: 'var(--cr-r-control)', border: '1px dashed var(--cr-line)', margin: '14px 0' }}>
          <p style={{ margin: 0, color: 'var(--cr-subtle)' }}>No dependency edges observed in this result.</p>
        </div>
      ) : (
        <>
          {activeTab === 'canvas' && layout && (
            <div
              style={{
                background: '#0B0D12',
                border: '1px solid var(--cr-line)',
                borderRadius: 'var(--cr-r-panel)',
                padding: '16px',
                margin: '14px 0',
                overflowX: 'auto',
                position: 'relative',
                boxShadow: 'inset 0 0 40px rgba(0, 0, 0, 0.6)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '11px', color: 'var(--cr-subtle)' }}>
                <span>PRODUCER NODES</span>
                <span>CONSUMER NODES</span>
              </div>
              <svg width={layout.width} height={layout.totalHeight} style={{ display: 'block', margin: 'auto' }}>
                <defs>
                  <linearGradient id="edgeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#4D85FF" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#34D399" stopOpacity="0.8" />
                  </linearGradient>
                  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#34D399" />
                  </marker>
                </defs>

                {/* Render Edges */}
                {view.edges.map(e => {
                  const p1 = layout.nodePositions.get(e.from);
                  const p2 = layout.nodePositions.get(e.to);
                  if (!p1 || !p2) return null;
                  const isHighlighted = selected === e.from || selected === e.to;
                  const dx = (p2.x - p1.x) / 2;
                  const path = `M ${p1.x + 100} ${p1.y + 20} C ${p1.x + 100 + dx} ${p1.y + 20}, ${p2.x - dx} ${p2.y + 20}, ${p2.x} ${p2.y + 20}`;
                  return (
                    <g key={`${e.from}->${e.to}`}>
                      <path
                        d={path}
                        fill="none"
                        stroke={isHighlighted ? '#4D85FF' : 'rgba(77, 133, 255, 0.35)'}
                        strokeWidth={isHighlighted ? 2.5 : 1.5}
                        strokeDasharray={isHighlighted ? 'none' : '4 3'}
                        markerEnd="url(#arrow)"
                      />
                    </g>
                  );
                })}

                {/* Render Nodes */}
                {Array.from(layout.nodePositions.entries()).map(([id, pos]) => {
                  const isSel = selected === id;
                  const nodeObj = scan.nodes.find(n => n.node_id === id);
                  return (
                    <g
                      key={id}
                      transform={`translate(${pos.x}, ${pos.y})`}
                      onClick={() => onSelect(id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <rect
                        width="120"
                        height="44"
                        rx="8"
                        fill={isSel ? 'rgba(77, 133, 255, 0.22)' : 'var(--cr-surface-2)'}
                        stroke={isSel ? '#4D85FF' : 'var(--cr-line)'}
                        strokeWidth={isSel ? 2 : 1}
                        style={{ filter: isSel ? 'drop-shadow(0 0 10px rgba(77, 133, 255, 0.5))' : 'none', transition: 'all 160ms ease' }}
                      />
                      <circle cx="10" cy="22" r="3.5" fill={isSel ? '#4D85FF' : '#34D399'} />
                      <text x="20" y="19" fill="#E9ECF2" fontSize="10" fontFamily="var(--font-mono)" fontWeight="bold">
                        {id.length > 14 ? id.slice(0, 13) + '…' : id}
                      </text>
                      <text x="20" y="33" fill="#A6AEBD" fontSize="9" fontFamily="var(--font-sans)">
                        {nodeObj?.current_model ? nodeObj.current_model.split('/').pop()?.slice(0, 15) : 'LLM Call'}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
          )}

          {/* Edge Table View */}
          <div style={{ display: activeTab === 'table' ? 'block' : 'none' }}>
            <p>Edges {page * 50 + 1}–{page * 50 + edges.length} of {view.edges.length}. Fan-in and fan-out are retained as separate edges.</p>
            <div className="table-scroll">
              <table>
                <caption>Observed data dependencies</caption>
                <thead>
                  <tr>
                    <th>Producer finding</th>
                    <th>Relationship</th>
                    <th>Consumer finding</th>
                  </tr>
                </thead>
                <tbody>
                  {edges.map(e => (
                    <tr key={`${e.from}:${e.to}`}>
                      <td>
                        <button
                          onClick={() => onSelect(e.from)}
                          aria-label={`Select producer ${e.from}`}
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '11px',
                            background: selected === e.from ? 'var(--cr-accent)' : 'var(--cr-surface-2)',
                            color: selected === e.from ? '#fff' : 'var(--cr-text)',
                          }}
                        >
                          {e.from}
                        </button>
                      </td>
                      <td>
                        <span style={{ color: 'var(--cr-subtle)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          data dependency <span style={{ color: 'var(--cr-accent)' }}>→</span>
                        </span>
                      </td>
                      <td>
                        <button
                          onClick={() => onSelect(e.to)}
                          aria-label={`Select consumer ${e.to}`}
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '11px',
                            background: selected === e.to ? 'var(--cr-accent)' : 'var(--cr-surface-2)',
                            color: selected === e.to ? '#fff' : 'var(--cr-text)',
                          }}
                        >
                          {e.to}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="control-row">
              <button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous edges</button>
              <button disabled={(page + 1) * 50 >= view.edges.length} onClick={() => setPage(page + 1)}>Next edges</button>
            </div>
          </div>
        </>
      )}

      <p style={{ marginTop: '12px' }}>{view.unconnected.length} findings have no observed connecting edge.</p>
      {view.unconnected.length > 0 && (
        <details style={{ marginTop: '8px' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--cr-muted)', fontSize: 'var(--cr-fs-xs)' }}>
            Findings without observed connections (first 50)
          </summary>
          <ul style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', listStyle: 'none', padding: '8px 0', margin: 0 }}>
            {view.unconnected.slice(0, 50).map(n => (
              <li key={n.node_id}>
                <button
                  onClick={() => onSelect(n.node_id)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    padding: '3px 8px',
                    background: selected === n.node_id ? 'var(--cr-accent)' : 'var(--cr-surface-2)',
                    color: selected === n.node_id ? '#fff' : 'var(--cr-text)',
                  }}
                >
                  {n.node_id}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

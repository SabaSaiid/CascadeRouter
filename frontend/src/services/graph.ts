import type { Scan } from './contracts.ts';
export function graphView(scan: Scan) {
  const incident = new Set(scan.graph_edges.flatMap(([from, to]) => [from, to]));
  return { edges: scan.graph_edges.map(([from, to]) => ({ from, to, kind: 'data_dependency' as const })),
    unconnected: scan.nodes.filter(node => !incident.has(node.node_id)),
    coverage: scan.graph_complete ? 'Complete within supported static rules' : 'Partial graph: additional dependencies may be absent' };
}
export function acyclic(ids: readonly string[], edges: readonly (readonly [string, string])[]): boolean {
  const incoming = new Map(ids.map(id => [id, 0])); const outgoing = new Map(ids.map(id => [id, [] as string[]]));
  for (const [from, to] of edges) {
    if (!incoming.has(from) || !incoming.has(to)) return false;
    incoming.set(to, incoming.get(to)! + 1); outgoing.get(from)!.push(to);
  }
  const ready = ids.filter(id => incoming.get(id) === 0); let processed = 0;
  for (let i = 0; i < ready.length; i++) { processed++; for (const to of outgoing.get(ready[i])!) { incoming.set(to, incoming.get(to)! - 1); if (incoming.get(to) === 0) ready.push(to); } }
  return processed === ids.length;
}

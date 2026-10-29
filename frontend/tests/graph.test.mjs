import test from 'node:test';
import assert from 'node:assert/strict';
import { graphView, acyclic } from '../src/services/graph.ts';
import { parseContract } from '../src/services/contractCheck.ts';
import { fixture } from './fixtures.mjs';
test('fan-in, fan-out and disconnected findings retain exactly the reported edges', () => {
  const scan = fixture('scan'); scan.nodes = [1, 2, 3, 4, 5].map(n => ({ ...scan.nodes[0], node_id: 'llm_' + String(n).repeat(24) }));
  const [a,b,c,d] = scan.nodes.map(n => n.node_id); scan.graph_edges = [[a,b],[a,c],[b,d],[c,d]];
  const result = graphView(parseContract('Scan', scan));
  assert.deepEqual(result.edges.map(e => [e.from,e.to]), scan.graph_edges); assert.equal(result.unconnected.length, 1);
  scan.graph_complete = scan.complete = false; assert.match(graphView(scan).coverage, /Partial/);
  scan.graph_edges.push([d,a]); assert.throws(() => parseContract('Scan', scan));
});
test('empty graph is not an invented sequence', () => {
  const scan = fixture('scan'); assert.deepEqual(graphView(scan).edges, []); assert.equal(graphView(scan).unconnected.length, 1);
  assert.equal(acyclic(['a','b'], [['a','missing']]), false);
});

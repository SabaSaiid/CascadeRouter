import assert from 'node:assert/strict';
import { acceptance } from './client.mjs';
import { graphView } from '../../src/services/graph.ts';
import { scanSummary } from '../../src/services/presentation.ts';
await acceptance(async ({ api, input, status, mark }) => {
  mark('scan response');
  const scan = await api.scan(input.repository); status(200);
  assert.equal(scan.data_source, 'live'); assert.equal(scan.nodes.length, 2);
  mark('coverage'); assert.equal(scan.complete, !input.partial); assert.equal(scan.scan_complete, !input.partial); assert.equal(scan.graph_complete, !input.partial);
  mark('observed graph');
  const producer = scan.nodes.find(n => n.line_number === 4), consumer = scan.nodes.find(n => n.line_number === 5);
  assert.ok(producer && consumer); assert.deepEqual(scan.graph_edges, [[producer.node_id, consumer.node_id]]);
  assert.equal(graphView(scan).edges.length, 1);
  if (input.partial) { assert.match(scanSummary(scan).coverage, /incomplete/); assert.ok(scan.scan_diagnostics.some(d => d.code === 'syntax_error')); }
  mark('stored retrieval'); assert.deepEqual(await api.analysis(scan.analysis_id), scan); status(200);
  return scan;
});

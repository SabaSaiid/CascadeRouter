import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiClient } from '../src/services/api.ts';
import { LocalTransport } from '../src/services/transport.ts';
import { scanSummary, provenance } from '../src/services/presentation.ts';
import { fixture } from './fixtures.mjs';
test('scan uses actual request contract and preserves backend provenance', async () => {
  const api = new ApiClient(new LocalTransport(undefined, async (url, init) => {
    assert.ok(url.endsWith('/api/scan')); assert.deepEqual(JSON.parse(init.body), { repository_path: 'operator/path' });
    return Response.json(fixture('scan'));
  }));
  const result = await api.scan('operator/path'); assert.equal(result.data_source, 'mock'); assert.match(provenance(result.data_source), /DEMO/);
});
test('partial empty scan cannot claim absence or full coverage', () => {
  const scan = fixture('scan'); scan.nodes = []; scan.detected_framework = null; scan.complete = scan.scan_complete = scan.graph_complete = false;
  const view = scanSummary(scan); assert.match(view.empty, /undiscovered/); assert.match(view.coverage, /incomplete/); assert.match(view.graph, /Partial/);
});
test('stored analysis retrieval uses protected analysis route and binds identity', async () => {
  const scan = fixture('scan'); const api = new ApiClient(new LocalTransport(undefined, async (url, init) => {
    assert.ok(url.endsWith('/api/analyses/' + scan.analysis_id)); assert.equal(init.method, 'GET'); return Response.json(scan);
  })); assert.deepEqual(await api.analysis(scan.analysis_id), scan);
});

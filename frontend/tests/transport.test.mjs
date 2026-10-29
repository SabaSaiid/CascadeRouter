import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixtures.mjs';
import { LocalTransport, localBase } from '../src/services/transport.ts';
import { parseContract } from '../src/services/contractCheck.ts';

const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

test('actual backend fixture contracts parse; synthetic provenance is retained', () => {
  for (const [model, file] of Object.entries({ Health: 'health', Scan: 'scan', Job: 'job', JobAccepted: 'jobAccepted', Optimization: 'optimization', Patch: 'patch', PatchAccepted: 'patchAccepted', Validation: 'validation' })) {
    const value = fixture(file); assert.deepEqual(parseContract(model, value), value);
  }
  assert.equal(fixture('job').plan.provenance, 'test'); assert.equal(fixture('scan').data_source, 'mock');
});
test('success uses explicit local URL and disallows redirect/credentials', async () => {
  const client = new LocalTransport(undefined, async (url, init) => {
    assert.equal(url, 'http://127.0.0.1:8000/api/health'); assert.equal(init.redirect, 'error'); assert.equal(init.credentials, 'omit');
    return json(fixture('health'));
  });
  assert.equal((await client.request('/api/health', 'Health')).benchmark_provenance, 'test');
});
for (const url of ['https://localhost:8000', 'http://example.invalid', 'http://127.0.0.1.evil.invalid', 'http://user:PRIVATE@localhost:8000', 'file:///tmp/api', 'http://localhost/path', 'http://localhost?key=PRIVATE']) {
  test('reject non-local or credential-bearing configuration ' + url.split(':')[0], () => assert.throws(() => localBase(url), e => e.kind === 'configuration' && !e.message.includes('PRIVATE')));
}
for (const [status, kind] of [[403, 'authorization'], [404, 'not_found'], [409, 'conflict'], [413, 'validation'], [422, 'validation'], [429, 'rate_limit'], [500, 'server'], [503, 'unavailable']]) {
  test(`HTTP ${status} stays an honest sanitized ${kind} failure`, async () => {
    const client = new LocalTransport(undefined, async () => json({ code: 'invalid_request', message: 'PRIVATE /internal/path', request_id: 'req_' + 'a'.repeat(32) }, status));
    await assert.rejects(client.request('/api/health', 'Health'), e => e.kind === kind && e.status === status && !e.message.includes('PRIVATE') && e.requestId.startsWith('req_'));
  });
}
test('network failure does not return mock success', async () => {
  const client = new LocalTransport(undefined, async () => { throw new Error('PRIVATE transport detail'); });
  await assert.rejects(client.request('/api/health', 'Health'), e => e.kind === 'unavailable' && !e.message.includes('PRIVATE'));
});
test('timeout and cancellation are distinct and never success', async () => {
  const blocked = async (_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new Error('PRIVATE'))));
  await assert.rejects(new LocalTransport(undefined, blocked, 5).request('/api/health', 'Health'), e => e.kind === 'timeout');
  const controller = new AbortController(); const request = new LocalTransport(undefined, blocked).request('/api/health', 'Health', { signal: controller.signal });
  controller.abort(); await assert.rejects(request, e => e.kind === 'cancelled');
});
test('already aborted requests and invalid paths make no fetch', async () => {
  const client = new LocalTransport(undefined, async () => assert.fail('Unexpected request'));
  const c = new AbortController(); c.abort();
  await assert.rejects(client.request('/api/health', 'Health', { signal: c.signal }), e => e.kind === 'cancelled');
  await assert.rejects(client.request('//outside.invalid', 'Health'), e => e.kind === 'validation');
});
for (const response of [() => new Response('PRIVATE invalid json', { headers: { 'Content-Type': 'application/json' } }), () => json({ status: 'ok' }), () => new Response('{}', { headers: { 'Content-Type': 'text/html' } })]) {
  test('malformed success bodies fail closed', async () => await assert.rejects(new LocalTransport(undefined, async () => response()).request('/api/health', 'Health'), e => e.kind === 'malformed'));
}
test('response byte limit is enforced', async () => await assert.rejects(new LocalTransport(undefined, async () => json(fixture('health')), 1000, 8).request('/api/health', 'Health'), e => e.kind === 'malformed'));
test('contradictory measured zero, partial and validation success are rejected', () => {
  const job = fixture('job'); job.measurements[0].latency_ms = { availability: 'unavailable', value: 0 };
  assert.throws(() => parseContract('Job', job));
  const scan = fixture('scan'); scan.scan_complete = false; scan.complete = true; assert.throws(() => parseContract('Scan', scan));
  const report = fixture('validation'); report.result.source_identity = 'not_verified'; assert.throws(() => parseContract('Validation', report));
});

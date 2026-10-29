import test from 'node:test';
import assert from 'node:assert/strict';
import { Operation } from '../src/services/operation.ts';
import { ApiClient } from '../src/services/api.ts';
import { LocalTransport } from '../src/services/transport.ts';
import { demoScan } from '../src/services/demo.ts';
import { fixture } from './fixtures.mjs';
test('duplicate in-flight actions do not submit twice', async () => {
  let resolve; let calls = 0; const op = new Operation();
  const pending = op.run(() => { calls++; return new Promise(r => { resolve = r; }); });
  await op.run(async () => { calls++; }); assert.equal(calls, 1);
  resolve('one'); await pending; assert.equal(op.snapshot().data, 'one');
});
test('superseded response cannot overwrite newer state even when fetch ignores abort', async () => {
  let resolve; const op = new Operation(); const first = op.run(() => new Promise(r => { resolve = r; }));
  await op.run(async () => 'new', true); resolve('old'); await first;
  assert.deepEqual(op.snapshot(), { status: 'ready', data: 'new' });
});
test('cancellation and lifecycle cleanup prevent late publication', async () => {
  let resolve; const op = new Operation(); const pending = op.run(() => new Promise(r => { resolve = r; }));
  op.cancel(); resolve('late'); await pending; assert.equal(op.snapshot().status, 'cancelled'); assert.equal(op.snapshot().data, undefined);
  op.reset(); assert.equal(op.snapshot().status, 'idle');
});
test('failed operation exposes sanitized error and never demo data', async () => {
  const op = new Operation(); await op.run(async () => { throw new Error('PRIVATE'); });
  assert.equal(op.snapshot().status, 'error'); assert.equal(op.snapshot().data, undefined); assert.ok(!op.snapshot().error.message.includes('PRIVATE'));
  assert.equal(demoScan.data_source, 'mock');
});
test('domain client validates requests and response identities', async () => {
  let calls = 0; const api = new ApiClient(new LocalTransport(undefined, async () => { calls++; return Response.json(fixture('scan')); }));
  await assert.rejects(api.analysis('analysis_' + 'f'.repeat(32)), e => e.kind === 'malformed');
  await assert.rejects(api.benchmark({ node_ids: [] }), e => e.kind === 'validation'); assert.equal(calls, 1);
});

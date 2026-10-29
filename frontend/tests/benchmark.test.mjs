import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiClient } from '../src/services/api.ts';
import { LocalTransport } from '../src/services/transport.ts';
import { population, measured, terminal, SubmissionKeys } from '../src/services/benchmark.ts';
import { parseContract } from '../src/services/contractCheck.ts';
import { fixture } from './fixtures.mjs';
test('missing measurement remains unavailable while a measured zero stays zero', () => {
  assert.equal(measured({ availability: 'available', value: 0 }), '0'); assert.equal(measured({ availability: 'unavailable', value: null }), 'Unavailable');
  assert.equal(population(), 'Unavailable'); assert.match(population(fixture('job').result.metrics.cost_usd), /USD/);
  const bad = fixture('job'); bad.measurements[0].latency_ms.value = -1; assert.throws(() => parseContract('Job', bad));
  const absent = fixture('job'); absent.measurements[0].input_tokens = { availability: 'available' }; assert.throws(() => parseContract('Job', absent));
  const inconsistent = fixture('job'); inconsistent.result.metrics.evaluation_complete = false; assert.throws(() => parseContract('Job', inconsistent));
});
test('same plan retries use one key; changed plan uses a new key', () => {
  const keys = new SubmissionKeys(); let n=0; const create=()=>String(++n);
  assert.equal(keys.forRequest({ node_ids: ['a'] },create), '1'); assert.equal(keys.forRequest({ node_ids: ['a'] },create), '1'); assert.equal(keys.forRequest({ node_ids: ['b'] },create), '2');
});
test('job state labels retain completion, interruption and cooperative cancellation semantics', () => {
  for (const status of ['complete','cancelled','error','interrupted']) assert.equal(terminal(status), true);
  for (const status of ['queued','running','cancelling']) assert.equal(terminal(status), false);
});
test('local benchmark, recovery, cancellation and optimization use exact API contracts', async () => {
  const job=fixture('job'); const plan=job.plan; const seen=[];
  const request={ analysis_id:plan.analysis_id,node_ids:plan.node_ids,baseline_model_id:plan.models[0].identifier,candidate_model_ids:plan.models.slice(1).map(m=>m.identifier),benchmark_case_set_id:plan.case_set.identifier,evaluation_profile_id:plan.evaluation_profile.identifier };
  const api=new ApiClient(new LocalTransport(undefined,async (url,init)=>{ seen.push([url,init]); return Response.json(fixture(url.endsWith('/api/benchmark')?'jobAccepted':url.endsWith('/api/optimize')?'optimization':'job')); }));
  assert.equal((await api.benchmark(request)).provenance,'test'); await api.run(job.run_id); await api.run(job.run_id,undefined,true);
  const optimized=await api.optimize({analysis_id:plan.analysis_id,run_id:job.run_id,case_set:plan.case_set,evaluation_profile:plan.evaluation_profile});
  assert.equal(optimized.result.provenance,'test'); assert.equal(seen[2][1].method,'POST'); assert.ok(seen[2][0].endsWith('/cancel'));
  assert.deepEqual(JSON.parse(seen[3][1].body),{analysis_id:plan.analysis_id,run_id:job.run_id,case_set:plan.case_set,evaluation_profile:plan.evaluation_profile});
});

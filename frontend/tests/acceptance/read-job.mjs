import assert from 'node:assert/strict';
import { setTimeout } from 'node:timers/promises';
import { acceptance } from './client.mjs';
await acceptance(async ({ api, input, status, mark }) => {
  mark('retained job identity');
  if (input.corrupt) { await assert.rejects(api.run(input.run_id), e => e.kind === 'conflict' && e.status === 409); status(409); return { rejected: true }; }
  let job; const deadline = Date.now() + 5000;
  do { job = await api.run(input.run_id); status(200); if (job.status === input.expected) break; await setTimeout(50); } while (Date.now() < deadline);
  assert.equal(job.status, input.expected); assert.equal(job.plan.provenance, 'test');
  if (input.expected === 'interrupted') { assert.equal(job.error.code, 'process_interrupted'); assert.equal(job.result, null); assert.equal(job.progress.completed_units, 0); }
  else { assert.equal(job.result.evaluation_status, 'inconclusive'); assert.equal(job.result.metrics, null); }
  assert.deepEqual(await api.run(job.run_id, undefined, true), job); status(200);
  return job;
});

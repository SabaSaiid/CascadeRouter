import assert from 'node:assert/strict';
import { setTimeout } from 'node:timers/promises';
import { acceptance } from './client.mjs';
await acceptance(async ({ api, input, status, mark }) => {
  const wait = async (id, expected) => { const deadline = Date.now()+5000; let job;
    do { job=await api.run(id); status(200); if(job.status===expected) return job; await setTimeout(50); } while(Date.now()<deadline);
    assert.fail('Expected lifecycle state was not reached');
  };
  mark('running job'); const first=await api.benchmark({...input.request,idempotency_key:'acceptance-first'}); status(202); await wait(first.run_id,'running');
  mark('queued job'); const second=await api.benchmark({...input.request,idempotency_key:'acceptance-second'}); status(202);
  assert.equal((await api.run(second.run_id)).status,'queued'); status(200);
  mark('concurrent queued cancellation'); const attempts=await Promise.allSettled([api.run(second.run_id,undefined,true),api.run(second.run_id,undefined,true)]);
  assert.ok(attempts.some(a=>a.status==='fulfilled'));
  for(const attempt of attempts) {
    if(attempt.status==='rejected') assert.ok(attempt.reason.kind==='rate_limit' && attempt.reason.status===429);
    else assert.ok(attempt.value.status==='cancelled' && attempt.value.result===null && attempt.value.progress.completed_units===0);
  }
  mark('idempotent retry after bounded admission'); assert.equal((await api.run(second.run_id,undefined,true)).status,'cancelled'); status(200);
  mark('running cancellation'); const requested=await api.run(first.run_id,undefined,true); status(200); assert.ok(['cancelling','cancelled'].includes(requested.status));
  const ended=await wait(first.run_id,'cancelled'); assert.equal(ended.result,null); assert.equal(ended.progress.completed_units,0);
  return [ended,await api.run(second.run_id)];
});

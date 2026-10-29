import test from 'node:test';
import assert from 'node:assert/strict';
import { invalidJobs } from './job-vectors.mjs';
import { parseContract } from '../src/services/contractCheck.ts';
import { ApiClient } from '../src/services/api.ts';
import { LocalTransport } from '../src/services/transport.ts';
import { Operation } from '../src/services/operation.ts';
for(const {name,value} of invalidJobs) test(`reject malformed job: ${name}`,async()=>{
  assert.throws(()=>parseContract('Job',value));
  const api=new ApiClient(new LocalTransport(undefined,async()=>Response.json(value)));
  const operation=new Operation(); await operation.run(signal=>api.run(value.run_id,signal));
  assert.equal(operation.snapshot().status,'error'); assert.equal(operation.snapshot().error.kind,'malformed'); assert.equal(operation.snapshot().data,undefined);
});

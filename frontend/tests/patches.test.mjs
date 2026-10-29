import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiClient } from '../src/services/api.ts';
import { LocalTransport } from '../src/services/transport.ts';
import { parseContract } from '../src/services/contractCheck.ts';
import { validationView, canPropose } from '../src/services/patches.ts';
import { fixture } from './fixtures.mjs';
import { reportFor } from './validation-fixtures.mjs';
for (const status of ['validated','partial','invalid','stale','unavailable']) {
  test(`real validation contract retains ${status} outcome independently of HTTP 201`,async()=>{
    const report=reportFor(status); parseContract('Validation',report);
    const api=new ApiClient(new LocalTransport(undefined,async(url,init)=>{
      assert.ok(url.endsWith('/api/patches/'+report.result.patch_id+'/validate')); assert.equal(init.method,'POST'); assert.equal(init.body,undefined);
      return Response.json(report,{status:201});
    })); assert.equal((await api.validate(report.result.patch_id)).result.status,status);
  });
}
test('history uses GET and never claims a current freshness check',async()=>{
  const report=fixture('validation'); const api=new ApiClient(new LocalTransport(undefined,async(url,init)=>{assert.ok(url.endsWith('/api/patch-validations/'+report.validation_id));assert.equal(init.method,'GET');return Response.json(report);}));
  const value=await api.validation(report.validation_id); assert.match(validationView(value,true).freshness,/does not check current/); assert.match(validationView(value,false).freshness,/Point-in-time/);
});
test('test optimization evidence cannot enable production proposal creation',()=>{
  assert.equal(canPropose(fixture('scan'),fixture('optimization')),false);
  assert.equal(canPropose(),false);
});
test('wrong proposal or report identity fails closed',async()=>{
  const api=new ApiClient(new LocalTransport(undefined,async()=>Response.json(fixture('validation'))));
  await assert.rejects(api.validate('patch_'+'f'.repeat(32)),e=>e.kind==='malformed');
  await assert.rejects(api.validation('validation_'+'f'.repeat(64)),e=>e.kind==='malformed');
});

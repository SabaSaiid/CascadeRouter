import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { inventory } from '../scripts/check_cache.mjs';
const bytes = Buffer.from('synthetic test artifact, not package or benchmark evidence');
const entry = { version:'1.0.0', resolved:'https://registry.npmjs.org/example/-/example-1.0.0.tgz', integrity:'sha512-'+createHash('sha512').update(bytes).digest('base64') };
test('verified cached bytes never imply installation or build success',async()=>{
  const result=await inventory({'':{},'node_modules/example':entry},async()=>bytes);
  assert.equal(result.verified,1); assert.equal(result.all_artifacts_verified,true); assert.equal(result.production_build_verified,false); assert.equal(result.installation_verified,false);
});
for(const [code,state] of [['ENOENT','missing'],['EINTEGRITY','integrity_mismatch'],['PRIVATE_ERROR','unavailable']]) test(`cache ${state} fails closed without private details`,async()=>{
  const result=await inventory({'node_modules/example':entry},async()=>{throw Object.assign(new Error('PRIVATE_PATH'),{code});});
  assert.equal(result[state],1); assert.equal(result.all_artifacts_verified,false); assert.ok(!JSON.stringify(result).includes('PRIVATE_'));
});
test('corrupt cached bytes cannot satisfy locked integrity',async()=>{
  const result=await inventory({'node_modules/example':entry},async()=>Buffer.from('changed'));
  assert.equal(result.integrity_mismatch,1); assert.equal(result.all_artifacts_verified,false);
});
test('invalid lock records never trigger a cache read',async()=>{
  const result=await inventory({'node_modules/example':{version:'1.0.0'}},async()=>assert.fail('Unexpected read'));
  assert.equal(result.invalid_lock,1);
});
test('optional platform artifacts remain visible, not silently assumed installed',async()=>{
  const result=await inventory({'node_modules/example':{...entry,optional:true,os:['linux']}},async()=>{throw Object.assign(new Error(),{code:'ENOENT'});});
  assert.equal(result.artifacts[0].platform_optional,true); assert.deepEqual(result.artifacts[0].os,['linux']); assert.equal(result.all_artifacts_verified,false);
});

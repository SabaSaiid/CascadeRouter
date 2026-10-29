import test from 'node:test';
import assert from 'node:assert/strict';
import { parseContract } from '../src/services/contractCheck.ts';
import { fixture } from './fixtures.mjs';
for(const key of ['constructor','__proto__','toString']) test(`unknown own property ${key} cannot match an inherited schema member`,()=>{
  const value=JSON.parse(JSON.stringify({...fixture('health'),[key]:{}}));
  assert.ok(Object.hasOwn(value,key)); assert.throws(()=>parseContract('Health',value));
  assert.equal(Object.getPrototypeOf(value),Object.prototype);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { ApiFailure } from '../src/services/transport.ts';
const { default: App } = await component('App');
const { OperationStatus } = await component('components/OperationStatus');
test('initial workbench is idle, has named sections and native keyboard form controls', () => {
  let calls=0; const original=globalThis.fetch; globalThis.fetch=()=>{calls++;throw new Error('unexpected');};
  let html; try { html=renderToStaticMarkup(React.createElement(App)); } finally { globalThis.fetch=original; }
  assert.equal(calls,0); assert.match(html,/href="#workbench"/); assert.match(html,/<main id="workbench"/);
  const ids=[...html.matchAll(/\sid="([^"]+)"/g)].map(m=>m[1]); assert.equal(ids.length,new Set(ids).size);
  for(const section of html.matchAll(/<section aria-labelledby="([^"]+)"/g)) assert.ok(ids.includes(section[1]));
  for(const form of html.matchAll(/<form>([\s\S]*?)<\/form>/g)) { assert.match(form[1],/<label>/); assert.match(form[1],/<button/); }
  assert.ok(!/tabindex="[1-9]/i.test(html)); assert.match(html,/No analysis result loaded/); assert.ok(!html.includes('Patch tested'));
});
test('loading, cancellation and errors have distinct screen-reader announcements', () => {
  const loading=renderToStaticMarkup(React.createElement(OperationStatus,{state:{status:'loading'},cancel(){}}));
  assert.match(loading,/role="status"/); assert.match(loading,/<button>Stop waiting/);
  const error=renderToStaticMarkup(React.createElement(OperationStatus,{state:{status:'error',error:new ApiFailure('authorization')}}));
  assert.match(error,/role="alert"/); assert.match(error,/denied access/);
  const cancelled=renderToStaticMarkup(React.createElement(OperationStatus,{state:{status:'cancelled'}})); assert.match(cancelled,/Backend work may still finish/);
  const ready=renderToStaticMarkup(React.createElement(OperationStatus,{state:{status:'ready',data:{}}})); assert.match(ready,/role="status"/); assert.match(ready,/Review the evidence and outcome/); assert.ok(!ready.includes('passed'));
});

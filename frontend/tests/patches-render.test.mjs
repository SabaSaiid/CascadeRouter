import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { fixture } from './fixtures.mjs';
import { reportFor } from './validation-fixtures.mjs';
const { ValidationEvidence, PatchEvidence, PatchPane }=await component('components/patches/PatchPane');
for(const status of ['validated','partial','invalid','stale','unavailable']) test(`render ${status} without claiming behavioral correctness or application`,()=>{
  const report=reportFor(status); const html=renderToStaticMarkup(React.createElement(ValidationEvidence,{report,historical:true}));
  assert.match(html,new RegExp('Static validation: '+status)); assert.ok(html.includes(report.result.patch_id)); assert.match(html,/Historical observation/); assert.match(html,/No application tests ran and no patch was applied/); assert.match(html,/TEST — synthetic/); assert.match(html,/<time dateTime=/);
});
test('proposal review preserves literal-spans contract and offers no apply action',()=>{
  const html=renderToStaticMarkup(React.createElement(PatchEvidence,{proposal:fixture('patch')}));
  assert.match(html,/literal-spans.v1/); assert.match(html,/not a standard unified diff/); assert.ok(!/<button[^>]*>.*(?:Apply|Commit|Rollback)/.test(html));
});
test('critical proposal actions are explicit native controls, disabled in demo',()=>{
  const html=renderToStaticMarkup(React.createElement(PatchPane,{demo:true,onJob(){}}));
  assert.match(html,/<label>Existing proposal ID<input/); assert.match(html,/<label>Historical validation report ID<input/); assert.match(html,/Validate proposal now \(static only\)/);
  for(const button of html.matchAll(/<button([^>]*)>/g)) assert.match(button[1],/disabled=""/);
});

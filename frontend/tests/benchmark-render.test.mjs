import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { fixture } from './fixtures.mjs';
const { JobEvidence, BenchmarkPane }=await component('components/benchmark/BenchmarkPane');
const { OptimizationEvidence }=await component('components/optimization/OptimizationPane');
test('job UI labels test provenance and missing metrics without synthetic comparisons',()=>{
  const job=fixture('job'); job.result.metrics=null;
  const html=renderToStaticMarkup(React.createElement(JobEvidence,{job}));
  assert.match(html,/TEST — synthetic/); assert.match(html,/Aggregate measurements unavailable/); assert.match(html,/completion does not mean quality passed/); assert.ok(!html.includes('0%'));
});
test('benchmark form has labeled controls and never submits during render or demo',()=>{
  const html=renderToStaticMarkup(React.createElement(BenchmarkPane,{demo:true,onJob(){}}));
  assert.match(html,/<fieldset disabled=""/); assert.match(html,/<label>Baseline model ID<input/); assert.match(html,/No automatic retry or polling/);
});
test('optimizer displays backend eligibility and does not authorize test fixtures',()=>{
  const value=fixture('optimization'); value.optimization_id=null;
  const html=renderToStaticMarkup(React.createElement(OptimizationEvidence,{value}));
  assert.match(html,/TEST — synthetic evidence; not production approval/); assert.match(html,/cannot create a production proposal/); assert.match(html,/all-checks-then-cost.v1/); assert.match(html,/not activated/);
});

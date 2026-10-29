import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { fixture } from './fixtures.mjs';
const { AgentGraph } = await component('components/repository/AgentGraph');
test('graph rendering explains absent evidence and supports native keyboard controls', () => {
  const scan = fixture('scan'); scan.graph_complete = scan.complete = false;
  const html = renderToStaticMarkup(React.createElement(AgentGraph, { scan, onSelect() {} }));
  assert.match(html, /Partial graph/); assert.match(html, /absent edge does not prove independence/); assert.match(html, /<button/); assert.match(html, /No dependency edges observed/);
});

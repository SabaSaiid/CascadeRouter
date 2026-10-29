import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { fixture } from './fixtures.mjs';
const { ScanFindings } = await component('components/repository/RepositoryPane');
test('findings render nullable evidence, native selection buttons, and partial coverage honestly', () => {
  const scan = fixture('scan'); scan.scan_complete = scan.complete = false; scan.nodes[0].current_model = null; scan.nodes[0].model_resolution = 'unresolved';
  const html = renderToStaticMarkup(React.createElement(ScanFindings, { scan, selected: scan.nodes[0].node_id, onSelect() {} }));
  assert.match(html, /DEMO/); assert.match(html, /coverage is incomplete/); assert.match(html, /Model unavailable/);
  assert.match(html, /<button[^>]+aria-pressed="true"/); assert.match(html, /<caption>/);
  assert.ok(!html.includes(scan.repository_path)); assert.ok(!html.includes('View source'));
});

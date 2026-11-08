import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { Operation } from '../src/services/operation.ts';
import { ApiFailure } from '../src/services/transport.ts';

const { default: App } = await component('App');
const { OperationStatus } = await component('components/OperationStatus');

test('initial render of App has zero alert/status warnings', () => {
  const html = renderToStaticMarkup(React.createElement(App));
  assert.ok(!html.includes('inline-alert warn'), 'Must have zero inline warn alerts on fresh load');
  assert.ok(!html.includes('This is taking longer than expected'), 'Must not show timeout warning on fresh load');
  assert.ok(!html.includes('Stopped waiting'), 'Must not show cancelled warning on fresh load');
  const alerts = [...html.matchAll(/role="alert"/g)];
  assert.equal(alerts.length, 0, 'Must have zero role="alert" banners on fresh load');
});

test('StrictMode double-mount leaves all operations idle', () => {
  const op = new Operation();
  assert.equal(op.snapshot().status, 'idle');
  // Simulate React 19 StrictMode mount -> layoutEffect cleanup cancel() -> remount
  op.cancel();
  assert.equal(op.snapshot().status, 'idle', 'Operation must remain idle when cancelled from idle');

  // StrictMode render of App
  const html = renderToStaticMarkup(
    React.createElement(React.StrictMode, null, React.createElement(App))
  );
  assert.ok(!html.includes('inline-alert warn'));
  assert.ok(!html.includes('This is taking longer than expected'));
  assert.ok(!html.includes('Stopped waiting'));
});

test('simulated timeout renders exactly one warning in the triggering control with stacked check button', () => {
  const timeoutFailure = new ApiFailure('timeout');
  const html = renderToStaticMarkup(React.createElement(OperationStatus, {
    state: { status: 'error', error: timeoutFailure },
    onCheckResult: () => {},
  }));

  const matches = [...html.matchAll(/This is taking longer than expected/g)];
  assert.equal(matches.length, 1, 'Timeout warning must appear exactly once');
  assert.match(html, /The backend may still finish\. Check for the result before submitting again\./);
  assert.match(html, /Check result/);
  assert.match(html, /role="status"/);
});

test('explicit Cancel shows the cooperative cancellation message', () => {
  const html = renderToStaticMarkup(React.createElement(OperationStatus, {
    state: { status: 'cancelled' },
  }));
  assert.match(html, /Stopped waiting\. The backend may still finish; check for the result before submitting again\./);
  assert.match(html, /Backend work may still finish/);
});

test('acceptance: fresh load at 1366x layout elements and empty states', () => {
  const html = renderToStaticMarkup(React.createElement(App));

  // Header status
  assert.match(html, /Backend not checked/);
  assert.match(html, /<button[^>]*>Check<\/button>/);

  // Progress trail: Scan is current (aria-current="step"), others pending
  assert.match(html, /aria-current="step"[^>]*>[\s\S]*?Scan/);
  assert.match(html, /Benchmark/);
  assert.match(html, /Recommend/);
  assert.match(html, /Patch/);

  // Left pane: empty path, disabled scan repository button, two secondary buttons, muted line
  assert.match(html, /Scan repository/);
  assert.match(html, /Use sample agent/);
  assert.match(html, /Use current repo/);
  assert.match(html, /Calls will appear here after a scan\./);

  // Centre pane: empty state
  assert.match(html, /Compare models on your own LLM calls/);
  assert.match(html, /Scan a repository, pick a call, then run a benchmark\./);
  assert.ok(!html.includes('Scan a repository first.'), 'Must not show Scan a repository first.');

  // Right pane: empty state
  assert.match(html, /Recommendation/);
  assert.match(html, /Run a benchmark to see which model each call can move to\./);
  assert.ok(!html.includes('Get recommendation'), 'Must not render Get recommendation button when idle');
});

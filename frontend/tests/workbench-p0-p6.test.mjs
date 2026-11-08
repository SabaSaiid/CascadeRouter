import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { Operation } from '../src/services/operation.ts';
import { ApiFailure } from '../src/services/transport.ts';
import { homeIllustrationFixture } from '../src/services/homeIllustration.ts';

const { default: App } = await component('App');
const { OperationStatus } = await component('components/OperationStatus');
const { HomeScreen } = await component('components/home/HomeScreen');
const { RepositoryPane } = await component('components/repository/RepositoryPane');
const { BenchmarkPane } = await component('components/benchmark/BenchmarkPane');
const { RightPane } = await component('components/optimization/RightPane');

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

test('fresh load at 1366x shows Home screen with headline, both buttons and example card', () => {
  const html = renderToStaticMarkup(React.createElement(App));

  // Header status
  assert.match(html, /Backend not checked/);
  assert.match(html, /<button[^>]*>Check<\/button>/);

  // Progress trail: Scan is current (aria-current="step"), others pending
  assert.match(html, /aria-current="step"[^>]*>[\s\S]*?Scan/);
  assert.match(html, /Benchmark/);
  assert.match(html, /Recommend/);
  assert.match(html, /Patch/);

  // Home Left column headline and copy
  assert.match(html, /Pay frontier-model prices only where you need them\./);
  assert.match(html, /CascadeRouter reads your Python AI app, tests cheaper NVIDIA Nemotron models on each LLM call/);

  // Buttons: filled "Try the sample agent" and outlined "Scan my own repository"
  assert.match(html, /Try the sample agent/);
  assert.match(html, /Scan my own repository/);

  // Reassurance line
  assert.match(html, /Your code is never run\./);
  assert.match(html, /Nothing changes until you apply\./);
  assert.match(html, /Every change is backed up\./);

  // How it works steps
  assert.match(html, /Finds every LLM call in your code without running it\./);
  assert.match(html, /Runs your test cases on each candidate model and records cost, speed and pass or fail\./);
  assert.match(html, /Picks the cheapest model that passes every check\./);
  assert.match(html, /Shows the one-line change\. A \.bak backup is saved before anything is written\./);

  // Example card on right column
  assert.match(html, /What a result looks like/);
  assert.match(html, /Example, not your data/);
  assert.match(html, /Triage intent/);
  assert.match(html, /Ultra to Nano/);
  assert.match(html, /Extract context/);
  assert.match(html, /Ultra to Lightning/);
  assert.match(html, /Draft reply/);
  assert.match(html, /Stays on Ultra/);
  assert.match(html, /Two of three calls can move to a cheaper model\. The third stays where it is\./);
  assert.match(html, /Models: NVIDIA Nemotron, served by Nebius Token Factory\./);
});

test('mandatory "Example, not your data" label renders whenever illustration fixture is shown', () => {
  assert.equal(homeIllustrationFixture.isIllustration, true);
  const html = renderToStaticMarkup(React.createElement(HomeScreen, {
    onTrySampleAgent: () => {},
    onScanOwnRepo: () => {},
  }));
  assert.match(html, /Example, not your data/);
  assert.match(html, /data-testid="example-mandatory-label"/);
});

test('recorded run updates example card label to Recorded run, <date time>', () => {
  const html = renderToStaticMarkup(React.createElement(HomeScreen, {
    onTrySampleAgent: () => {},
    onScanOwnRepo: () => {},
    recordedRunDate: '31 Oct 12:01',
  }));
  assert.match(html, /Recorded run, 31 Oct 12:01/);
});

test('backend unavailable on Home renders inline notice with Retry button', () => {
  const unavailableFailure = new ApiFailure('unavailable');
  const html = renderToStaticMarkup(React.createElement(HomeScreen, {
    onTrySampleAgent: () => {},
    onScanOwnRepo: () => {},
    healthError: unavailableFailure,
    onRetryHealth: () => {},
  }));
  assert.match(html, /The local backend isn(&#x27;|')t responding/);
  assert.match(html, /Start it with bash start\.sh, then press Retry/);
  assert.match(html, /<button[^>]*>Retry<\/button>/);
});

test('workbench three-pane view displays repository, benchmark and recommendation panes', () => {
  const repoHtml = renderToStaticMarkup(React.createElement(RepositoryPane, {
    demo: false,
    onAnalysis: () => {},
    onSelect: () => {},
    step: 'scan',
  }));
  assert.match(repoHtml, /Scan repository/);
  assert.match(repoHtml, /Use sample agent/);
  assert.match(repoHtml, /Use current repo/);
  assert.match(repoHtml, /Calls will appear here after a scan\./);

  const benchHtml = renderToStaticMarkup(React.createElement(BenchmarkPane, {
    demo: false,
    onJob: () => {},
    step: 'scan',
  }));
  assert.match(benchHtml, /Compare models on your own LLM calls/);
  assert.match(benchHtml, /Scan a repository, pick a call, then run a benchmark\./);

  const rightHtml = renderToStaticMarkup(React.createElement(RightPane, {
    demo: false,
    step: 'scan',
    onOptimization: () => {},
  }));
  assert.match(rightHtml, /Recommendation/);
  assert.match(rightHtml, /Run a benchmark to see which model each call can move to\./);
});

test('enhanced UI/UX: benchmark pane provides interactive sortable headers and presets', () => {
  const html = renderToStaticMarkup(React.createElement(BenchmarkPane, {
    demo: true,
    onJob: () => {},
    step: 'benchmark',
  }));
  assert.match(html, /Use Nebius \/ NVIDIA defaults/);
  assert.match(html, /Nemotron Suite \(70B, 8B\)/);
  assert.match(html, /Fast Eval \(8B only\)/);
});

test('enhanced UI/UX: repository pane provides instant call search and filter bar', () => {
  const html = renderToStaticMarkup(React.createElement(RepositoryPane, {
    demo: false,
    onAnalysis: () => {},
    onSelect: () => {},
    step: 'scan',
    autoFocusPath: false,
  }));
  assert.match(html, /Scan repository/);
});

test('enhanced UI/UX: policy tab provides Download YAML and Copy actions', () => {
  const html = renderToStaticMarkup(React.createElement(RightPane, {
    demo: false,
    step: 'recommend',
    onOptimization: () => {},
  }));
  assert.match(html, /Recommendation/);
});

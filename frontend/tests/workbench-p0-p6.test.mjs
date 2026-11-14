import test from 'node:test';
import assert from 'node:assert/strict';
import { React, renderToStaticMarkup, component } from './render.mjs';
import { Operation } from '../src/services/operation.ts';
import { ApiFailure } from '../src/services/transport.ts';
import { homeIllustrationFixture } from '../src/services/homeIllustration.ts';

const { default: App } = await component('App');
const { OperationStatus } = await component('components/OperationStatus');
const { HomeScreen } = await component('components/home/HomeScreen');
const { TierBoard } = await component('components/board/TierBoard');
const { DetailTable } = await component('components/detail/DetailTable');
const { DecisionPanel } = await component('components/decision/DecisionPanel');
const { RepoBar } = await component('components/repository/RepoBar');
const { SettingsDrawer, HowItWorksDrawer, SecurityTermsDrawer } = await component('components/modals/Drawers');

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

  // Route board example on right column
  assert.match(html, /Where each call runs/);
  assert.match(html, /Example, not your data/);
  assert.match(html, /Triage intent/);
  assert.match(html, /Extract context/);
  assert.match(html, /Draft reply/);
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

test('workbench displays repository bar, tier board, detail table and decision panel', () => {
  const repoHtml = renderToStaticMarkup(React.createElement(RepoBar, {
    demo: false,
    onAnalysis: () => {},
    callSearch: '',
    onCallSearchChange: () => {},
  }));
  assert.match(repoHtml, /Scan repository/);
  assert.match(repoHtml, /Sample agent/);
  assert.match(repoHtml, /Current dir/);

  const boardHtml = renderToStaticMarkup(React.createElement(TierBoard, {
    calls: [],
  }));
  assert.match(boardHtml, /Where each call runs/);
  assert.match(boardHtml, /Cheaper tiers on the left/);

  const detailHtml = renderToStaticMarkup(React.createElement(DetailTable, {
    selectedNode: undefined,
  }));
  assert.match(detailHtml, /Select a call on the board/);

  const decisionHtml = renderToStaticMarkup(React.createElement(DecisionPanel, {
    demo: false,
    step: 'scan',
    onOptimization: () => {},
  }));
  assert.match(decisionHtml, /Decision &amp; patch|Decision & patch/);
  assert.match(decisionHtml, /Run a benchmark to see which model each call can move to\./);
});

test('acceptance: no sidebar, no ALL-CAPS labels, no mono badges rendered in App', () => {
  const html = renderToStaticMarkup(React.createElement(App));
  assert.ok(!html.includes('app-sidebar'), 'Must have no app-sidebar');
  assert.ok(!html.includes('Step 1: Scan & DAG'), 'Must have no Step 1 badge');
  assert.ok(!html.includes('Step 2: Empirical Benchmark'), 'Must have no Step 2 badge');
  assert.ok(!html.includes('Step 3 & 4: FinOps & Patch'), 'Must have no Step 3 & 4 badge');
  assert.ok(!html.includes('NVIDIA H100'), 'Must have no unverified H100 hardware claims');
  assert.ok(!html.includes('Mock data</span>'), 'Must not render Mock data chip');
});

test('acceptance: TierBoard renders columns, tracks, stations, and accessibility', () => {
  const html = renderToStaticMarkup(React.createElement(TierBoard, {
    calls: [
      {
        node_id: 'llm_1',
        function_name: 'triage_intent',
        file_path: 'app.py',
        line_number: 14,
        current_model: 'meta-llama/Meta-Llama-3.1-70B-Instruct',
        call_signature: '',
        model_resolution: 'literal',
        model_reference: null,
        model_references: [],
        prompt_resolution: 'literal',
        prompt_reference: null,
        prompt_references: [],
        schema_resolution: 'missing',
        schema_reference: null,
        schema_references: [],
        limited_schema_summary: null,
      }
    ],
  }));
  assert.match(html, /Where each call runs/);
  assert.match(html, /Cheaper tiers on the left/);
  assert.match(html, /triage_intent/);
  assert.match(html, /app\.py:14/);
  assert.match(html, /Meta-Llama-3\.1-8B-Instruct/);
});

test('acceptance: DetailTable displays model comparison without first-token in table', () => {
  const html = renderToStaticMarkup(React.createElement(DetailTable, {
    selectedNode: {
      node_id: 'llm_1',
      function_name: 'triage_intent',
      file_path: 'app.py',
      line_number: 14,
      current_model: 'meta-llama/Meta-Llama-3.1-70B-Instruct',
      call_signature: '',
      model_resolution: 'literal',
      model_reference: null,
      model_references: [],
      prompt_resolution: 'literal',
      prompt_reference: null,
      prompt_references: [],
      schema_resolution: 'missing',
      schema_reference: null,
      schema_references: [],
      limited_schema_summary: null,
    },
  }));
  assert.match(html, /triage_intent, in detail/);
  assert.ok(!html.includes('First token'), 'First token / TTFT must not appear in table columns');
});

test('acceptance: SettingsDrawer has single control for strict checks', () => {
  const html = renderToStaticMarkup(React.createElement(SettingsDrawer, {
    onClose: () => {},
    strictAllChecks: true,
    onStrictAllChecksChange: () => {},
  }));
  assert.match(html, /Only recommend a model if it passes every check/);
  assert.ok(!html.includes('Dark Theme'), 'Theme options must be removed');
  assert.ok(!html.includes('Nebius & Hardware'), 'Hardware options must be removed');
});

test('acceptance: HowItWorksDrawer and SecurityTermsDrawer render without hardware claims', () => {
  const howHtml = renderToStaticMarkup(React.createElement(HowItWorksDrawer, { onClose: () => {} }));
  assert.match(howHtml, /How it works/);
  assert.ok(!howHtml.includes('H100'));

  const secHtml = renderToStaticMarkup(React.createElement(SecurityTermsDrawer, { onClose: () => {} }));
  assert.match(secHtml, /Security and terms/);
  assert.match(secHtml, /Zero code execution guarantee/i);
  assert.ok(!secHtml.includes('H100'));
});

test('acceptance: RepoBar hides search field when calls <= 8 and shows Scan again', () => {
  const html = renderToStaticMarkup(React.createElement(RepoBar, {
    demo: false,
    analysis: {
      analysis_id: 'analysis_' + '0'.repeat(32),
      repository_path: 'examples/customer_support_agent',
      nodes: [
        { node_id: 'llm_1', function_name: 'call_1', file_path: 'app.py', line_number: 1, current_model: 'm', call_signature: '', model_resolution: 'literal', model_reference: null, model_references: [], prompt_resolution: 'literal', prompt_reference: null, prompt_references: [], schema_resolution: 'missing', schema_reference: null, schema_references: [], limited_schema_summary: null },
      ],
      graph_edges: [],
      scanned_files_count: 1,
      discovered_files_count: 1,
      total_source_bytes_read: 100,
      detected_framework: 'OpenAI SDK',
      data_source: 'live',
      scan_complete: true,
      graph_complete: true,
      complete: true,
      scan_diagnostics: [],
      graph_diagnostics: [],
      schema_version: 'cascaderouter.scan.v1',
      timestamp: '2026-10-31T12:00:00Z',
    },
    onAnalysis: () => {},
    callSearch: '',
    onCallSearchChange: () => {},
  }));
  assert.match(html, /examples\/customer_support_agent/);
  assert.match(html, /1 file scanned, 1 LLM call found, OpenAI SDK/);
  assert.match(html, /Scan again/);
  assert.ok(!html.includes('Search calls…'), 'Search field must be hidden when calls <= 8');
});

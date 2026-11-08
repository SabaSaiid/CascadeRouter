import test from 'node:test';
import assert from 'node:assert/strict';

// Import the compiled module via the render harness path trick used in other test files
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, mkdirSync, writeFileSync, lstatSync, realpathSync, rmSync, readdirSync } from 'node:fs';
import { resolve, dirname, join, basename } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { tmpdir } from 'node:os';

const root = fileURLToPath(new URL('..', import.meta.url));
const tools = process.env.CASCADE_TEST_TOOLS || root;
const require = createRequire(join(tools, 'package.json'));
const ts = require('typescript');
const build = mkdtempSync(join(tmpdir(), 'cascade-display-'));

const ownedIdentity = lstatSync(build);
process.once('exit', () => {
  try {
    const resolved = realpathSync(build), current = lstatSync(build);
    if (dirname(resolved) !== realpathSync(tmpdir()) || !basename(resolved).startsWith('cascade-display-')
      || current.isSymbolicLink() || !current.isDirectory() || current.dev !== ownedIdentity.dev || current.ino !== ownedIdentity.ino) throw new Error();
    rmSync(resolved, { recursive: true, force: true });
  } catch { process.stderr.write('Display-test workspace cleanup unavailable.\n'); process.exitCode ||= 1; }
});

writeFileSync(join(build, 'package.json'), '{"type":"module"}');

function compile(folder) {
  for (const file of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, file.name);
    if (file.isDirectory()) compile(path);
    else if (/\.tsx?$/.test(path)) {
      const destination = join(build, path.slice(resolve(root, 'src').length + 1).replace(/\.tsx?$/, '.js'));
      mkdirSync(dirname(destination), { recursive: true });
      const result = ts.transpileModule(readFileSync(path, 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX }
      });
      const output = result.outputText
        .replace(/(from\s+['"][^'"]+)\.tsx?(['"])/g, '$1.js$2')
        .replace(/(from\s+['"])(react(?:-dom)?(?:\/[^'"]+)?)(['"])/g, (_match, before, name, after) =>
          before + pathToFileURL(require.resolve(name)).href + after);
      writeFileSync(destination, output);
    }
  }
}
compile(resolve(root, 'src'));

const displayPath = pathToFileURL(join(build, 'services/display.js')).href;
const { shortModelName, costBarScale, savingsSentence, dataSourceLabel } = await import(displayPath);

// ---------------------------------------------------------------------------
// shortModelName
// ---------------------------------------------------------------------------
test('shortModelName strips vendor prefix', () => {
  assert.equal(shortModelName('nvidia/NVIDIA-Nemotron-3-Nano-3B-A3B'), 'NVIDIA-Nemotron-3-Nano-3B-A3B');
  assert.equal(shortModelName('meta-llama/Meta-Llama-3.1-70B-Instruct'), 'Meta-Llama-3.1-70B-Instruct');
});

test('shortModelName falls back to full ID when no slash', () => {
  assert.equal(shortModelName('nemotron-nano'), 'nemotron-nano');
  assert.equal(shortModelName(''), '');
});

// ---------------------------------------------------------------------------
// costBarScale
// ---------------------------------------------------------------------------
test('costBarScale returns 100 for the max row', () => {
  assert.equal(costBarScale('0.000459', '0.000459'), 100);
});

test('costBarScale scales proportionally', () => {
  const result = costBarScale('0.000030', '0.000459');
  assert.ok(result > 0 && result < 100, `expected 0–100, got ${result}`);
});

test('costBarScale returns 0 for null/undefined cost', () => {
  assert.equal(costBarScale(null, '0.000459'), 0);
  assert.equal(costBarScale(undefined, '0.000459'), 0);
  assert.equal(costBarScale('0.000030', null), 0);
});

test('costBarScale returns 0 when max is zero', () => {
  assert.equal(costBarScale('0', '0'), 0);
});

// ---------------------------------------------------------------------------
// savingsSentence
// ---------------------------------------------------------------------------
function makeDecision(overrides = {}) {
  return {
    analysis_id: 'analysis_' + '0'.repeat(32),
    node_id: 'llm_' + '0'.repeat(24),
    provenance: 'recorded',
    status: 'recommended',
    reason: 'lowest_recorded_cost',
    baseline_model_id: 'nvidia/Ultra',
    selected_model_id: 'nvidia/Nano',
    differs_from_baseline: true,
    quality_threshold: null,
    recorded_savings_usd: '0.000429',
    candidates: [
      { model: { identifier: 'nvidia/Nano', version: '1' }, eligibility: 'eligible', reasons: [], planned_cases: 6, passed_cases: 6, failed_cases: 0, unresolved_cases: 0, latency_ms: { availability: 'available', unit: 'ms', sample_count: 6, mean: 138 }, cost_total_usd: '0.000030', quality_pass_rate: '1.0', provenance: 'recorded' },
      { model: { identifier: 'nvidia/Ultra', version: '1' }, eligibility: 'eligible', reasons: [], planned_cases: 6, passed_cases: 6, failed_cases: 0, unresolved_cases: 0, latency_ms: { availability: 'available', unit: 'ms', sample_count: 6, mean: 1145 }, cost_total_usd: '0.000459', quality_pass_rate: '1.0', provenance: 'recorded' },
    ],
    ...overrides,
  };
}

test('savingsSentence includes cheapest model name without hard-coding', () => {
  const decision = makeDecision();
  const sentence = savingsSentence({ decision, candidates: decision.candidates, selectedModelId: decision.selected_model_id, baselineModelId: decision.baseline_model_id });
  assert.ok(sentence.includes('Nano'), 'should mention short model name');
  assert.ok(sentence.includes('%'), 'should include saving percentage');
  assert.ok(!sentence.includes('nvidia/'), 'should not include vendor prefix');
});

test('savingsSentence returns em dash when selectedModelId is null', () => {
  const decision = makeDecision({ selected_model_id: null });
  const result = savingsSentence({ decision, candidates: decision.candidates, selectedModelId: null, baselineModelId: 'nvidia/Ultra' });
  assert.equal(result, '—');
});

test('savingsSentence handles unknown costs with em dash', () => {
  const decision = makeDecision();
  const candidates = decision.candidates.map(c => ({ ...c, cost_total_usd: null }));
  const sentence = savingsSentence({ decision, candidates, selectedModelId: decision.selected_model_id, baselineModelId: decision.baseline_model_id });
  assert.ok(!sentence.includes('NaN'), 'should not contain NaN');
  assert.ok(!sentence.includes('undefined'), 'should not contain undefined');
});

// ---------------------------------------------------------------------------
// dataSourceLabel
// ---------------------------------------------------------------------------
test('dataSourceLabel returns mock kind for mock data_source', () => {
  const result = dataSourceLabel('mock', null, null);
  assert.equal(result.kind, 'mock');
  assert.equal(result.text, 'Mock data');
});

test('dataSourceLabel returns recorded kind with date', () => {
  const result = dataSourceLabel('recorded', null, '2024-10-31T12:01:00Z');
  assert.equal(result.kind, 'recorded');
  assert.ok(result.text.startsWith('Recorded run'), `got: ${result.text}`);
});

test('dataSourceLabel returns live kind for live data_source', () => {
  const result = dataSourceLabel('live', 'recorded', null);
  assert.equal(result.kind, 'live');
  assert.ok(result.text.includes('Live'), `got: ${result.text}`);
});

test('dataSourceLabel handles undefined scan source gracefully', () => {
  const result = dataSourceLabel(undefined, undefined, undefined);
  assert.equal(result.kind, 'live');
});


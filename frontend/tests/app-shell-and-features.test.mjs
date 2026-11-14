import test from 'node:test';
import assert from 'node:assert/strict';
import { derivePipelineSteps } from '../src/services/pipeline.ts';
import {
  sanitizeRepoFolderName,
  getRecentResults,
  saveRecentResult,
  removeRecentResult,
  clearRecentResults,
  RECENT_RESULTS_CAP,
} from '../src/services/recentResults.ts';
import {
  deriveQualityThreshold,
  parseCandidateModelIds,
  isValidIdentifier,
} from '../src/services/settings.ts';
import { parseRoute, ROUTE_TITLES } from '../src/services/router.ts';
import { NoticeQueue, MAX_NOTICES } from '../src/services/notices.ts';

// ============================================================================
// 1. Pipeline Summary Derivation Tests
// ============================================================================
test('pipeline summary derivation: initial un-scanned state', () => {
  const steps = derivePipelineSteps({});
  assert.equal(steps.length, 4);

  const [scan, bench, rec, patch] = steps;
  assert.equal(scan.name, 'Scan');
  assert.equal(scan.dot, 'current');
  assert.equal(scan.summary, 'Pick a repository');

  assert.equal(bench.name, 'Benchmark');
  assert.equal(bench.dot, 'pending');
  assert.equal(bench.summary, 'Not started');

  assert.equal(rec.name, 'Recommend');
  assert.equal(rec.dot, 'pending');
  assert.equal(rec.summary, 'Waiting for results');

  assert.equal(patch.name, 'Patch');
  assert.equal(patch.dot, 'pending');
  assert.equal(patch.summary, 'Not started');
});

test('pipeline summary derivation: scanned state with N calls found', () => {
  const mockScan = {
    analysis_id: 'analysis_123',
    repository_path: '/abs/path/to/my_app',
    nodes: [
      { node_id: 'n1', current_model: 'model-a', file_path: 'a.py', line_number: 1 },
      { node_id: 'n2', current_model: 'model-b', file_path: 'b.py', line_number: 2 },
      { node_id: 'n3', current_model: 'model-c', file_path: 'c.py', line_number: 3 },
    ],
  };

  const steps = derivePipelineSteps({ analysis: mockScan });
  const [scan, bench] = steps;
  assert.equal(scan.dot, 'done');
  assert.equal(scan.summary, '3 calls found');
  assert.equal(bench.dot, 'current');
  assert.equal(bench.summary, 'Not started');

  // Single call grammar check
  const singleStep = derivePipelineSteps({
    analysis: { ...mockScan, nodes: [mockScan.nodes[0]] },
  });
  assert.equal(singleStep[0].summary, '1 call found');
});

test('pipeline summary derivation: benchmark in flight with progress bar', () => {
  const mockScan = {
    analysis_id: 'analysis_123',
    nodes: [{ node_id: 'n1' }, { node_id: 'n2' }, { node_id: 'n3' }],
  };

  const steps = derivePipelineSteps({
    analysis: mockScan,
    isBenchmarking: true,
    benchmarkingUnits: { completed: 2, total: 6 },
  });

  const bench = steps[1];
  assert.equal(bench.dot, 'current');
  assert.equal(bench.summary, '2 of 6 tested');
  assert.equal(bench.progressPercent, 33);
});

test('pipeline summary derivation: benchmark completed', () => {
  const mockScan = {
    analysis_id: 'analysis_123',
    nodes: [{ node_id: 'n1' }, { node_id: 'n2' }],
  };
  const mockJob = {
    run_id: 'run_123',
    status: 'complete',
    plan: { node_ids: ['n1', 'n2'] },
  };

  const steps = derivePipelineSteps({ analysis: mockScan, job: mockJob });
  const [_, bench, rec] = steps;
  assert.equal(bench.dot, 'done');
  assert.equal(bench.summary, '2 of 2 tested');
  assert.equal(rec.dot, 'current');
  assert.equal(rec.summary, 'Waiting for results');
});

test('pipeline summary derivation: recommendations and patch states', () => {
  const mockScan = { analysis_id: 'analysis_1', nodes: [{ node_id: 'n1' }, { node_id: 'n2' }] };
  const mockJob = { run_id: 'r1', status: 'complete', plan: { node_ids: ['n1', 'n2'] } };

  // Case A: 2 calls can move
  const mockOptMovers = {
    result: {
      decisions: [
        { node_id: 'n1', status: 'recommended', baseline_model_id: 'base', selected_model_id: 'cand1' },
        { node_id: 'n2', status: 'recommended', baseline_model_id: 'base', selected_model_id: 'cand2' },
      ],
    },
  };

  const stepsA = derivePipelineSteps({ analysis: mockScan, job: mockJob, optimization: mockOptMovers });
  assert.equal(stepsA[2].dot, 'done');
  assert.equal(stepsA[2].summary, '2 calls can move');
  assert.equal(stepsA[3].dot, 'current');
  assert.equal(stepsA[3].summary, 'Ready to apply');

  // Case B: No call can move
  const mockOptNoMovers = {
    result: {
      decisions: [
        { node_id: 'n1', status: 'baseline_retained', baseline_model_id: 'base', selected_model_id: 'base' },
      ],
    },
  };
  const stepsB = derivePipelineSteps({ analysis: mockScan, job: mockJob, optimization: mockOptNoMovers });
  assert.equal(stepsB[2].summary, 'No call can move');
  assert.equal(stepsB[3].dot, 'pending');
  assert.equal(stepsB[3].summary, 'Not started');

  // Case C: Patch applied
  const stepsC = derivePipelineSteps({
    analysis: mockScan,
    job: mockJob,
    optimization: mockOptMovers,
    patchApplied: true,
  });
  assert.equal(stepsC[3].dot, 'done');
  assert.equal(stepsC[3].summary, 'Applied, backup saved');
});

// ============================================================================
// 2. Recent Results Storage Tests (Cap, No Absolute Paths, Fail-closed)
// ============================================================================
test('recent-results storage: sanitizes folder name and NEVER stores absolute paths', () => {
  assert.equal(sanitizeRepoFolderName('/Users/sabasaeed/work/customer_support'), 'customer_support');
  assert.equal(sanitizeRepoFolderName('C:\\Users\\admin\\repos\\ai_agent\\'), 'ai_agent');
  assert.equal(sanitizeRepoFolderName('/home/user/code/chatbot/'), 'chatbot');
  assert.equal(sanitizeRepoFolderName('my-project'), 'my-project');
  assert.equal(sanitizeRepoFolderName('///'), 'repository');
  assert.equal(sanitizeRepoFolderName(''), 'repository');
});

test('recent-results storage: enforces cap of 20 entries', () => {
  // Use a simulated in-memory storage for test isolation
  const memoryStore = new Map();
  const mockStorage = {
    getItem: (k) => memoryStore.get(k) || null,
    setItem: (k, v) => memoryStore.set(k, String(v)),
    removeItem: (k) => memoryStore.delete(k),
  };
  globalThis.window = { localStorage: mockStorage };

  clearRecentResults();

  // Add 25 entries
  for (let i = 1; i <= 25; i++) {
    saveRecentResult({
      analysis_id: `analysis_${i}`,
      repo_folder: `/var/data/project_${i}`,
      date: '14 Nov 2026',
      calls_found: i,
      calls_can_move: 1,
      saving_percentage: '50%',
      statuses: ['Scanned'],
      summary: `${i} calls found`,
    });
  }

  const stored = getRecentResults();
  assert.equal(stored.length, RECENT_RESULTS_CAP);
  // Entry 25 should be at the top
  assert.equal(stored[0].repo_folder, 'project_25');
  assert.ok(!stored[0].repo_folder.includes('/'), 'Must never contain slashes');

  // Test remove
  const idToRemove = stored[0].id;
  removeRecentResult(idToRemove);
  const afterRemove = getRecentResults();
  assert.equal(afterRemove.length, RECENT_RESULTS_CAP - 1);
  assert.ok(!afterRemove.some(e => e.id === idToRemove));
});

test('recent-results storage: safely handles storage unavailable or quota exceeded', () => {
  const throwingStorage = {
    getItem: () => { throw new Error('SecurityError: storage disabled'); },
    setItem: () => { throw new Error('QuotaExceededError'); },
    removeItem: () => { throw new Error('SecurityError'); },
  };
  globalThis.window = { localStorage: throwingStorage };

  // Should return empty array without throwing
  const res = getRecentResults();
  assert.deepEqual(res, []);

  // Save should return null without throwing
  const saved = saveRecentResult({
    repo_folder: 'safe_repo',
    date: 'now',
    calls_found: 2,
    calls_can_move: 1,
    saving_percentage: '20%',
    statuses: ['Scanned'],
    summary: 'safe summary',
  });
  assert.equal(saved, null);
});

// ============================================================================
// 3. Settings to Threshold & Benchmark-Plan Mapping Tests
// ============================================================================
test('settings to threshold: strict all checks maps to 1.000000', () => {
  assert.equal(deriveQualityThreshold(true, 100), '1.000000');
  assert.equal(deriveQualityThreshold(true, 80), '1.000000');
});

test('settings to threshold: non-strict maps to 6-decimal rate clamped [50, 100]', () => {
  assert.equal(deriveQualityThreshold(false, 100), '1.000000');
  assert.equal(deriveQualityThreshold(false, 80), '0.800000');
  assert.equal(deriveQualityThreshold(false, 75), '0.750000');
  assert.equal(deriveQualityThreshold(false, 99.5), '0.995000');
  // Clamp < 50 to 50%
  assert.equal(deriveQualityThreshold(false, 30), '0.500000');
  // Clamp > 100 to 100%
  assert.equal(deriveQualityThreshold(false, 120), '1.000000');
});

test('candidate model ID validation and parsing', () => {
  // Valid list
  const validList = 'nvidia/nemotron-mini-4b-instruct, meta-llama/llama-3.1-8b-instruct';
  const resValid = parseCandidateModelIds(validList);
  assert.equal(resValid.error, undefined);
  assert.deepEqual(resValid.valid, [
    'nvidia/nemotron-mini-4b-instruct',
    'meta-llama/llama-3.1-8b-instruct',
  ]);

  // Cap at 8
  const tenModels = Array.from({ length: 10 }, (_, i) => `model-${i}`).join(', ');
  const resTen = parseCandidateModelIds(tenModels);
  assert.ok(resTen.error?.includes('limited to at most 8'));
  assert.equal(resTen.valid.length, 8);

  // Invalid characters
  const invalidList = 'good-model, bad model with spaces!';
  const resInvalid = parseCandidateModelIds(invalidList);
  assert.ok(resInvalid.error?.includes('Invalid model identifier'));

  // Empty string
  const resEmpty = parseCandidateModelIds('  ,  ');
  assert.ok(resEmpty.error?.includes('At least one candidate model is required'));

  // Identifier regex test
  assert.equal(isValidIdentifier('valid-id_1.0/v2'), true);
  assert.equal(isValidIdentifier('invalid id with spaces'), false);
  assert.equal(isValidIdentifier(''), false);
});

// ============================================================================
// 4. Hash Routing Tests
// ============================================================================
test('hash routing: parses routes and titles accurately', () => {
  assert.equal(parseRoute('#/'), 'home');
  assert.equal(parseRoute(''), 'home');
  assert.equal(parseRoute('#/workbench'), 'workbench');
  assert.equal(parseRoute('#workbench'), 'workbench');
  assert.equal(parseRoute('#/history'), 'history');
  assert.equal(parseRoute('#/settings'), 'settings');
  assert.equal(parseRoute('#/guide'), 'guide');
  assert.equal(parseRoute('#/security'), 'security');
  assert.equal(parseRoute('#/unknown-hash'), 'home');

  // Verify document titles
  assert.equal(ROUTE_TITLES.home, 'CascadeRouter - Home');
  assert.equal(ROUTE_TITLES.workbench, 'CascadeRouter - Workbench');
  assert.equal(ROUTE_TITLES.history, 'CascadeRouter - Recent results');
  assert.equal(ROUTE_TITLES.settings, 'CascadeRouter - Settings');
  assert.equal(ROUTE_TITLES.guide, 'CascadeRouter - How it works');
  assert.equal(ROUTE_TITLES.security, 'CascadeRouter - Security and terms');
});

// ============================================================================
// 5. Completion Notice Queue Tests
// ============================================================================
test('notice queue: enforces maximum of 2 visible notices with FIFO dismissal', () => {
  const queue = new NoticeQueue();
  assert.equal(queue.getNotices().length, 0);

  const id1 = queue.addNotice('Call 1 finished. It can move to Nano and save 93%.');
  assert.equal(queue.getNotices().length, 1);
  assert.equal(queue.getNotices()[0].id, id1);

  const id2 = queue.addNotice('Call 2 finished. It can move to Lightning and save 85%.');
  assert.equal(queue.getNotices().length, 2);

  // Adding 3rd notice drops the 1st
  const id3 = queue.addNotice('Call 3 finished. It remains on Ultra.');
  assert.equal(queue.getNotices().length, MAX_NOTICES);
  assert.equal(queue.getNotices()[0].id, id2);
  assert.equal(queue.getNotices()[1].id, id3);

  // Manual dismiss
  queue.dismiss(id2);
  assert.equal(queue.getNotices().length, 1);
  assert.equal(queue.getNotices()[0].id, id3);

  queue.clear();
  assert.equal(queue.getNotices().length, 0);
});

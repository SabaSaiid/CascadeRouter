// ==============================================================================
// CascadeRouter IDE - Realistic Mock Data Fixtures
// Strictly used for offline development & fallback demo playback
// ==============================================================================

import type { BenchmarkRun, OptimizeResult, ScanResult } from '../types';

export const MOCK_SCAN_RESULT: ScanResult = {
  repository_path: 'tests/fixtures/sample_repo',
  scanned_files_count: 8,
  detected_framework: 'OpenAI SDK / Python Agent',
  timestamp: new Date().toISOString(),
  data_source: 'mock',
  nodes: [
    {
      node_id: 'node_classify_intent',
      file_path: 'agent/workflow.py',
      line_number: 38,
      function_name: 'classify_customer_intent',
      current_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      call_signature: 'client.chat.completions.create(model=..., messages=[...])',
      prompt_reference: 'SYSTEM_INTENT_CLASSIFICATION_PROMPT',
      docstring: 'Classifies customer inquiry into categories: billing, tech_support, or general.',
      expected_schema: {
        type: 'object',
        properties: {
          category: { type: 'string', enum: ['billing', 'tech_support', 'general'] },
          confidence: { type: 'number' },
          urgency: { type: 'string', enum: ['low', 'medium', 'high'] },
        },
        required: ['category', 'confidence'],
      },
      snippet: `response = client.chat.completions.create(
    model="nvidia/Nemotron-3-Ultra-550b-a55b",
    messages=[{"role": "system", "content": SYSTEM_INTENT_CLASSIFICATION_PROMPT},
              {"role": "user", "content": query}]
)`,
    },
    {
      node_id: 'node_extract_entities',
      file_path: 'agent/workflow.py',
      line_number: 94,
      function_name: 'extract_ticket_metadata',
      current_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      call_signature: 'client.chat.completions.create(model=..., response_format=...)',
      prompt_reference: 'ENTITY_EXTRACTION_PROMPT',
      docstring: 'Extracts account number, software version, and operating system from ticket.',
      expected_schema: {
        type: 'object',
        properties: {
          account_id: { type: 'string' },
          os_version: { type: 'string' },
          error_code: { type: 'string' },
        },
        required: ['account_id'],
      },
      snippet: `res = client.chat.completions.create(
    model="nvidia/Nemotron-3-Ultra-550b-a55b",
    response_format={"type": "json_object"},
    messages=[{"role": "user", "content": prompt}]
)`,
    },
    {
      node_id: 'node_synthesize_solution',
      file_path: 'agent/workflow.py',
      line_number: 162,
      function_name: 'generate_support_resolution',
      current_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      call_signature: 'client.chat.completions.create(model=..., max_tokens=1024)',
      prompt_reference: 'RESOLUTION_SYNTHESIS_TEMPLATE',
      docstring: 'Synthesizes step-by-step resolution based on diagnostics.',
      snippet: `resolution = client.chat.completions.create(
    model="nvidia/Nemotron-3-Ultra-550b-a55b",
    messages=history + [{"role": "user", "content": "Generate fix"}]
)`,
    },
  ],
  graph_edges: [
    ['node_classify_intent', 'node_extract_entities'],
    ['node_extract_entities', 'node_synthesize_solution'],
  ],
};

export const MOCK_BENCHMARK_RUN: BenchmarkRun = {
  run_id: 'run_nebius_bench_7894',
  status: 'complete',
  progress_pct: 100,
  current_step: 'Completed all 12 model evaluations across 3 nodes',
  data_source: 'mock',
  created_at: new Date(Date.now() - 1000 * 60 * 3).toISOString(),
  nodes: [
    {
      node_id: 'node_classify_intent',
      recommended_model_id: 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
      metrics_by_model: {
        'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': {
          model_id: 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
          model_name: 'Nemotron-3 Nano (30B)',
          tier: 'efficient',
          input_tokens: 312,
          output_tokens: 48,
          total_latency_ms: 138,
          time_to_first_token_ms: 42,
          estimated_cost_usd: 0.00003024,
          quality_score: 0.98,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3_5-Lightning': {
          model_id: 'nvidia/Nemotron-3_5-Lightning',
          model_name: 'Nemotron-3.5 Lightning',
          tier: 'efficient',
          input_tokens: 312,
          output_tokens: 52,
          total_latency_ms: 108,
          time_to_first_token_ms: 31,
          estimated_cost_usd: 0.00003120,
          quality_score: 0.94,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3.5-Super-VL': {
          model_id: 'nvidia/Nemotron-3.5-Super-VL',
          model_name: 'Nemotron-3.5 Super-VL',
          tier: 'balanced',
          input_tokens: 312,
          output_tokens: 49,
          total_latency_ms: 412,
          time_to_first_token_ms: 98,
          estimated_cost_usd: 0.00013770,
          quality_score: 0.99,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3-Ultra-550b-a55b': {
          model_id: 'nvidia/Nemotron-3-Ultra-550b-a55b',
          model_name: 'Nemotron-3 Ultra (550B)',
          tier: 'powerful',
          input_tokens: 312,
          output_tokens: 48,
          total_latency_ms: 1145,
          time_to_first_token_ms: 290,
          estimated_cost_usd: 0.00045600,
          quality_score: 0.99,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
      },
    },
    {
      node_id: 'node_extract_entities',
      recommended_model_id: 'nvidia/Nemotron-3_5-Lightning',
      metrics_by_model: {
        'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': {
          model_id: 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
          model_name: 'Nemotron-3 Nano (30B)',
          tier: 'efficient',
          input_tokens: 480,
          output_tokens: 92,
          total_latency_ms: 182,
          time_to_first_token_ms: 45,
          estimated_cost_usd: 0.00005088,
          quality_score: 0.93,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3_5-Lightning': {
          model_id: 'nvidia/Nemotron-3_5-Lightning',
          model_name: 'Nemotron-3.5 Lightning',
          tier: 'efficient',
          input_tokens: 480,
          output_tokens: 88,
          total_latency_ms: 125,
          time_to_first_token_ms: 34,
          estimated_cost_usd: 0.00004992,
          quality_score: 0.96,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3.5-Super-VL': {
          model_id: 'nvidia/Nemotron-3.5-Super-VL',
          model_name: 'Nemotron-3.5 Super-VL',
          tier: 'balanced',
          input_tokens: 480,
          output_tokens: 89,
          total_latency_ms: 480,
          time_to_first_token_ms: 112,
          estimated_cost_usd: 0.00022410,
          quality_score: 0.99,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3-Ultra-550b-a55b': {
          model_id: 'nvidia/Nemotron-3-Ultra-550b-a55b',
          model_name: 'Nemotron-3 Ultra (550B)',
          tier: 'powerful',
          input_tokens: 480,
          output_tokens: 90,
          total_latency_ms: 1310,
          time_to_first_token_ms: 325,
          estimated_cost_usd: 0.00075000,
          quality_score: 1.00,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
      },
    },
    {
      node_id: 'node_synthesize_solution',
      recommended_model_id: 'nvidia/Nemotron-3.5-Super-VL',
      metrics_by_model: {
        'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': {
          model_id: 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
          model_name: 'Nemotron-3 Nano (30B)',
          tier: 'efficient',
          input_tokens: 840,
          output_tokens: 320,
          total_latency_ms: 610,
          time_to_first_token_ms: 55,
          estimated_cost_usd: 0.00012720,
          quality_score: 0.78, // Fails 0.92 threshold for complex synthesis!
          passes_validation: false,
          validation_errors: ['Quality score 0.78 below 0.92 threshold', 'Omitted diagnostic step 3'],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3_5-Lightning': {
          model_id: 'nvidia/Nemotron-3_5-Lightning',
          model_name: 'Nemotron-3.5 Lightning',
          tier: 'efficient',
          input_tokens: 840,
          output_tokens: 310,
          total_latency_ms: 450,
          time_to_first_token_ms: 38,
          estimated_cost_usd: 0.00012480,
          quality_score: 0.81, // Fails 0.92 threshold!
          passes_validation: false,
          validation_errors: ['Quality score 0.81 below 0.92 threshold'],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3.5-Super-VL': {
          model_id: 'nvidia/Nemotron-3.5-Super-VL',
          model_name: 'Nemotron-3.5 Super-VL',
          tier: 'balanced',
          input_tokens: 840,
          output_tokens: 340,
          total_latency_ms: 820,
          time_to_first_token_ms: 128,
          estimated_cost_usd: 0.00055800,
          quality_score: 0.97, // PASSES!
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
        'nvidia/Nemotron-3-Ultra-550b-a55b': {
          model_id: 'nvidia/Nemotron-3-Ultra-550b-a55b',
          model_name: 'Nemotron-3 Ultra (550B)',
          tier: 'powerful',
          input_tokens: 840,
          output_tokens: 345,
          total_latency_ms: 2280,
          time_to_first_token_ms: 410,
          estimated_cost_usd: 0.00187500,
          quality_score: 0.99,
          passes_validation: true,
          validation_errors: [],
          is_estimated: false,
          status: 'completed',
        },
      },
    },
  ],
};

export const MOCK_OPTIMIZE_RESULT: OptimizeResult = {
  total_baseline_cost_usd: 0.003081,
  total_optimized_cost_usd: 0.00063816,
  total_cost_reduction_pct: 79.3,
  avg_latency_reduction_pct: 68.4,
  all_regressions_passed: true,
  data_source: 'mock',
  decisions: [
    {
      node_id: 'node_classify_intent',
      baseline_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      recommended_model: 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
      fallback_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      baseline_cost_usd: 0.000456,
      optimized_cost_usd: 0.00003024,
      cost_reduction_pct: 93.4,
      baseline_latency_ms: 1145,
      optimized_latency_ms: 138,
      latency_reduction_pct: 88.0,
      quality_score: 0.98,
      status: 'optimized',
      regression_passed: true,
      regression_log: 'tests/test_agent.py::test_classify_intent PASSED [0.08s]',
      policy_yaml: `node_id: node_classify_intent
primary_model: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
fallback_model: nvidia/Nemotron-3-Ultra-550b-a55b
routing_conditions:
  min_quality_score: 0.92
  enforce_schema: true
  max_retries: 1
telemetry:
  verified_cost_savings_pct: 93.4%
  measured_ttft_ms: 42ms`,
      patch_diff: `--- a/agent/workflow.py
+++ b/agent/workflow.py
@@ -38,3 +38,5 @@
-    response = client.chat.completions.create(
-        model="nvidia/Nemotron-3-Ultra-550b-a55b",
-        messages=[{"role": "system", "content": SYSTEM_INTENT_CLASSIFICATION_PROMPT},
+    response = cascade_router.dispatch(
+        node_id="node_classify_intent",
+        client=client,
+        fallback_tier="nvidia/Nemotron-3-Ultra-550b-a55b",
+        messages=[{"role": "system", "content": SYSTEM_INTENT_CLASSIFICATION_PROMPT},`,
    },
    {
      node_id: 'node_extract_entities',
      baseline_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      recommended_model: 'nvidia/Nemotron-3_5-Lightning',
      fallback_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      baseline_cost_usd: 0.000750,
      optimized_cost_usd: 0.00004992,
      cost_reduction_pct: 93.3,
      baseline_latency_ms: 1310,
      optimized_latency_ms: 125,
      latency_reduction_pct: 90.5,
      quality_score: 0.96,
      status: 'optimized',
      regression_passed: true,
      regression_log: 'tests/test_agent.py::test_entity_extraction PASSED [0.11s]',
      policy_yaml: `node_id: node_extract_entities
primary_model: nvidia/Nemotron-3_5-Lightning
fallback_model: nvidia/Nemotron-3-Ultra-550b-a55b
routing_conditions:
  min_quality_score: 0.92
  enforce_json_schema: true
telemetry:
  verified_cost_savings_pct: 93.3%
  measured_ttft_ms: 34ms`,
      patch_diff: `--- a/agent/workflow.py
+++ b/agent/workflow.py
@@ -94,3 +94,5 @@
-    res = client.chat.completions.create(
-        model="nvidia/Nemotron-3-Ultra-550b-a55b",
+    res = cascade_router.dispatch(
+        node_id="node_extract_entities",
+        client=client,
+        fallback_tier="nvidia/Nemotron-3-Ultra-550b-a55b",
         response_format={"type": "json_object"},`,
    },
    {
      node_id: 'node_synthesize_solution',
      baseline_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      recommended_model: 'nvidia/Nemotron-3.5-Super-VL',
      fallback_model: 'nvidia/Nemotron-3-Ultra-550b-a55b',
      baseline_cost_usd: 0.001875,
      optimized_cost_usd: 0.000558,
      cost_reduction_pct: 70.2,
      baseline_latency_ms: 2280,
      optimized_latency_ms: 820,
      latency_reduction_pct: 64.0,
      quality_score: 0.97,
      status: 'optimized',
      regression_passed: true,
      regression_log: 'tests/test_agent.py::test_synthesize_resolution PASSED [0.34s]',
      policy_yaml: `node_id: node_synthesize_solution
primary_model: nvidia/Nemotron-3.5-Super-VL
fallback_model: nvidia/Nemotron-3-Ultra-550b-a55b
routing_conditions:
  min_quality_score: 0.92
telemetry:
  verified_cost_savings_pct: 70.2%
  measured_ttft_ms: 128ms`,
      patch_diff: `--- a/agent/workflow.py
+++ b/agent/workflow.py
@@ -162,3 +162,5 @@
-    resolution = client.chat.completions.create(
-        model="nvidia/Nemotron-3-Ultra-550b-a55b",
+    resolution = cascade_router.dispatch(
+        node_id="node_synthesize_solution",
+        client=client,
+        fallback_tier="nvidia/Nemotron-3-Ultra-550b-a55b",
         messages=history + [{"role": "user", "content": "Generate fix"}]`,
    },
  ],
  combined_policy_yaml: `# Generated by CascadeRouter FinOps Compiler (Oct 26, 2026)
# Target Repo: tests/fixtures/sample_repo
# Nebius Token Factory Optimization Plan

version: "1.0"
quality_threshold: 0.92
total_projected_savings: 79.3%

nodes:
  - id: node_classify_intent
    selected_tier: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
    fallback_tier: nvidia/Nemotron-3-Ultra-550b-a55b
    cost_savings: 93.4%
    latency_reduction: 88.0%

  - id: node_extract_entities
    selected_tier: nvidia/Nemotron-3_5-Lightning
    fallback_tier: nvidia/Nemotron-3-Ultra-550b-a55b
    cost_savings: 93.3%
    latency_reduction: 90.5%

  - id: node_synthesize_solution
    selected_tier: nvidia/Nemotron-3.5-Super-VL
    fallback_tier: nvidia/Nemotron-3-Ultra-550b-a55b
    cost_savings: 70.2%
    latency_reduction: 64.0%
`,
  combined_patch_diff: `--- a/agent/workflow.py
+++ b/agent/workflow.py
@@ -8,6 +8,7 @@
 import os
 from openai import OpenAI
+from cascaderouter import CascadeRouter
 
 client = OpenAI(base_url="https://api.studio.nebius.ai/v1")
+cascade_router = CascadeRouter.load(".cascaderouter.yaml")
@@ -38,3 +39,5 @@
-    response = client.chat.completions.create(
-        model="nvidia/Nemotron-3-Ultra-550b-a55b",
+    response = cascade_router.dispatch(
+        node_id="node_classify_intent",
+        client=client,
+        fallback_tier="nvidia/Nemotron-3-Ultra-550b-a55b",
@@ -94,3 +97,5 @@
-    res = client.chat.completions.create(
-        model="nvidia/Nemotron-3-Ultra-550b-a55b",
+    res = cascade_router.dispatch(
+        node_id="node_extract_entities",
+        client=client,
+        fallback_tier="nvidia/Nemotron-3-Ultra-550b-a55b",
@@ -162,3 +167,5 @@
-    resolution = client.chat.completions.create(
-        model="nvidia/Nemotron-3-Ultra-550b-a55b",
+    resolution = cascade_router.dispatch(
+        node_id="node_synthesize_solution",
+        client=client,
+        fallback_tier="nvidia/Nemotron-3-Ultra-550b-a55b",
`,
};

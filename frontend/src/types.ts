// ==============================================================================
// CascadeRouter IDE - Shared Frontend TypeScript Contracts
// Mirrors backend/schemas.py (Single Source of Truth)
// ==============================================================================

export type DataSourceMode = 'live' | 'recorded' | 'mock';

export type ModelTier = 'efficient' | 'balanced' | 'powerful';

export interface LLMNode {
  node_id: string;
  file_path: string;
  line_number: number;
  current_model: string;
  call_signature: string;
  prompt_reference?: string;
  expected_schema?: Record<string, unknown>;
  function_name?: string;
  docstring?: string;
  snippet?: string;
}

export type GraphEdge = [string, string]; // [from_node_id, to_node_id]

export interface ScanResult {
  repository_path: string;
  nodes: LLMNode[];
  graph_edges: GraphEdge[];
  timestamp: string;
  data_source: DataSourceMode;
  scanned_files_count: number;
  detected_framework: string;
}

export interface BenchmarkMetric {
  model_id: string;
  model_name: string;
  tier: ModelTier;
  input_tokens: number;
  output_tokens: number;
  total_latency_ms: number;
  time_to_first_token_ms?: number;
  estimated_cost_usd: number;
  quality_score: number;
  passes_validation: boolean;
  validation_errors: string[];
  is_estimated: boolean;
  status: 'completed' | 'failed' | 'running' | 'pending';
}

export interface NodeBenchmarkResult {
  node_id: string;
  metrics_by_model: Record<string, BenchmarkMetric>;
  recommended_model_id?: string;
}

export interface BenchmarkRun {
  run_id: string;
  status: 'idle' | 'running' | 'complete' | 'error';
  progress_pct: number;
  current_step?: string;
  nodes: NodeBenchmarkResult[];
  data_source: DataSourceMode;
  created_at: string;
}

export interface OptimizationDecision {
  node_id: string;
  baseline_model: string;
  recommended_model: string;
  fallback_model: string;
  baseline_cost_usd: number;
  optimized_cost_usd: number;
  cost_reduction_pct: number;
  baseline_latency_ms: number;
  optimized_latency_ms: number;
  latency_reduction_pct: number;
  quality_score: number;
  status: 'optimized' | 'inconclusive' | 'baseline_retained';
  policy_yaml: string;
  patch_diff: string;
  regression_passed: boolean;
  regression_log?: string;
}

export interface OptimizeResult {
  decisions: OptimizationDecision[];
  total_baseline_cost_usd: number;
  total_optimized_cost_usd: number;
  total_cost_reduction_pct: number;
  avg_latency_reduction_pct: number;
  combined_policy_yaml: string;
  combined_patch_diff: string;
  all_regressions_passed: boolean;
  data_source: DataSourceMode;
}

// Model Tier Catalog Definition
export interface ModelTierConfig {
  id: string;
  name: string;
  tier: ModelTier;
  inputPricePerM: number;
  outputPricePerM: number;
  description: string;
  badgeColor: string;
}

export const NEMOTRON_CATALOG: ModelTierConfig[] = [
  {
    id: 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
    name: 'Nemotron-3 Nano (30B)',
    tier: 'efficient',
    inputPricePerM: 0.06,
    outputPricePerM: 0.24,
    description: 'Lightweight & ultra-low latency, ideal for extraction & categorization',
    badgeColor: 'emerald',
  },
  {
    id: 'nvidia/Nemotron-3_5-Lightning',
    name: 'Nemotron-3.5 Lightning',
    tier: 'efficient',
    inputPricePerM: 0.06,
    outputPricePerM: 0.24,
    description: 'Ultra-fast token generation for intermediate agent steps',
    badgeColor: 'cyan',
  },
  {
    id: 'nvidia/Nemotron-3.5-Super-VL',
    name: 'Nemotron-3.5 Super-VL',
    tier: 'balanced',
    inputPricePerM: 0.30,
    outputPricePerM: 0.90,
    description: 'Balanced multimodal reasoning & complex structured transformations',
    badgeColor: 'purple',
  },
  {
    id: 'nvidia/Nemotron-3-Ultra-550b-a55b',
    name: 'Nemotron-3 Ultra (550B)',
    tier: 'powerful',
    inputPricePerM: 1.00,
    outputPricePerM: 3.00,
    description: 'Frontier reasoning & code generation; acts as fallback safety tier',
    badgeColor: 'amber',
  },
];

import type { Scan, Job, Optimization } from './contracts.ts';

export type PipelineDotState = 'done' | 'current' | 'pending';

export interface PipelineStep {
  key: 'scan' | 'benchmark' | 'recommend' | 'patch';
  name: string;
  dot: PipelineDotState;
  summary: string;
  progressPercent?: number;
}

export interface PipelineDerivationInput {
  analysis?: Scan;
  job?: Job;
  optimization?: Optimization;
  isBenchmarking?: boolean;
  benchmarkingUnits?: { completed: number; total: number };
  patchApplied?: boolean;
}

export function derivePipelineSteps(input: PipelineDerivationInput): PipelineStep[] {
  const {
    analysis,
    job,
    optimization,
    isBenchmarking = false,
    benchmarkingUnits,
    patchApplied = false,
  } = input;

  // 1. Scan step
  const scanDone = Boolean(analysis && analysis.nodes.length > 0);
  const scanStep: PipelineStep = {
    key: 'scan',
    name: 'Scan',
    dot: scanDone ? 'done' : 'current',
    summary: scanDone
      ? `${analysis!.nodes.length} call${analysis!.nodes.length === 1 ? '' : 's'} found`
      : 'Pick a repository',
  };

  // 2. Benchmark step
  const totalCalls = analysis?.nodes.length ?? 0;
  const benchmarkDone = Boolean(job && job.status === 'complete');
  let benchmarkDot: PipelineDotState = 'pending';
  let benchmarkSummary = 'Not started';
  let benchmarkProgress: number | undefined;

  if (benchmarkDone) {
    benchmarkDot = 'done';
    const tested = job?.plan?.node_ids?.length ?? totalCalls;
    benchmarkSummary = `${tested} of ${totalCalls || tested} tested`;
  } else if (isBenchmarking) {
    benchmarkDot = 'current';
    const k = benchmarkingUnits?.completed ?? 0;
    const n = benchmarkingUnits?.total ?? (totalCalls || 1);
    benchmarkSummary = `${k} of ${n} tested`;
    benchmarkProgress = n > 0 ? Math.min(100, Math.round((k / n) * 100)) : 0;
  } else if (scanDone) {
    benchmarkDot = 'current';
    benchmarkSummary = 'Not started';
  }

  const benchmarkStep: PipelineStep = {
    key: 'benchmark',
    name: 'Benchmark',
    dot: benchmarkDot,
    summary: benchmarkSummary,
    progressPercent: benchmarkProgress,
  };

  // 3. Recommend step
  let recommendDot: PipelineDotState = 'pending';
  let recommendSummary = 'Waiting for results';

  if (optimization) {
    recommendDot = 'done';
    const movableCalls = optimization.result.decisions.filter(
      d => d.status === 'recommended' &&
           d.selected_model_id &&
           d.selected_model_id !== d.baseline_model_id
    ).length;

    if (movableCalls > 0) {
      recommendSummary = `${movableCalls} call${movableCalls === 1 ? '' : 's'} can move`;
    } else {
      recommendSummary = 'No call can move';
    }
  } else if (benchmarkDone) {
    recommendDot = 'current';
    recommendSummary = 'Waiting for results';
  }

  const recommendStep: PipelineStep = {
    key: 'recommend',
    name: 'Recommend',
    dot: recommendDot,
    summary: recommendSummary,
  };

  // 4. Patch step
  let patchDot: PipelineDotState = 'pending';
  let patchSummary = 'Not started';

  if (patchApplied) {
    patchDot = 'done';
    patchSummary = 'Applied, backup saved';
  } else if (optimization) {
    const movableCalls = optimization.result.decisions.filter(
      d => d.status === 'recommended' &&
           d.selected_model_id &&
           d.selected_model_id !== d.baseline_model_id
    ).length;

    if (movableCalls > 0) {
      patchDot = 'current';
      patchSummary = 'Ready to apply';
    } else {
      patchDot = 'pending';
      patchSummary = 'Not started';
    }
  }

  const patchStep: PipelineStep = {
    key: 'patch',
    name: 'Patch',
    dot: patchDot,
    summary: patchSummary,
  };

  return [scanStep, benchmarkStep, recommendStep, patchStep];
}

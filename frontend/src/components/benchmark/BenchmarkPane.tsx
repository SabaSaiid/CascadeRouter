import { useState, type FC } from 'react';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Coins,
  Sparkles,
  Zap,
  BarChart3,
  AlertCircle,
} from 'lucide-react';
import {
  NEMOTRON_CATALOG,
  type BenchmarkMetric,
  type BenchmarkRun,
  type ScanResult,
} from '../../types';

interface BenchmarkPaneProps {
  benchmarkRun: BenchmarkRun | null;
  scanResult: ScanResult | null;
  onRunBenchmark: () => void;
  isBenchmarking: boolean;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

export const BenchmarkPane: FC<BenchmarkPaneProps> = ({
  benchmarkRun,
  scanResult,
  onRunBenchmark,
  isBenchmarking,
  selectedNodeId,
  onSelectNode,
}) => {
  const [activeCellMetric, setActiveCellMetric] = useState<BenchmarkMetric | null>(null);

  const nodes = scanResult?.nodes || [];

  return (
    <div className="flex flex-col h-full bg-[#0b0f19] border-r border-slate-800/80 overflow-hidden">
      {/* Pane Header */}
      <div className="p-3 border-b border-slate-800 bg-[#0e1424]/70 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Nemotron Benchmark Matrix (Nebius Token Factory)
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
            <span className="text-slate-500">Quality Hurdle:</span>
            <span className="font-mono text-emerald-400 font-semibold px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
              &ge; 0.92
            </span>
          </div>
          <button
            onClick={onRunBenchmark}
            disabled={nodes.length === 0 || isBenchmarking}
            className="flex items-center gap-1 px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white rounded text-xs font-medium transition-colors"
          >
            <Zap className="w-3 h-3" />
            <span>{isBenchmarking ? 'Running Matrix...' : 'Run Benchmark'}</span>
          </button>
        </div>
      </div>

      {/* Progress & Concurrency Banner */}
      {isBenchmarking && (
        <div className="px-4 py-2 bg-indigo-950/50 border-b border-indigo-800/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
            <span className="text-xs text-indigo-200">
              Benchmarking {nodes.length} nodes across 4 Nemotron tiers with bounded concurrency (4 workers)...
            </span>
          </div>
          <span className="text-xs font-mono text-indigo-300 font-bold">
            {benchmarkRun?.progress_pct || 45}%
          </span>
        </div>
      )}

      {/* Benchmark Matrix Container */}
      <div className="flex-1 overflow-auto p-4">
        {nodes.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-slate-500 border border-dashed border-slate-800 rounded-xl">
            <BarChart3 className="w-10 h-10 text-slate-600 mb-2" />
            <h3 className="text-sm font-semibold text-slate-300">Matrix Idle</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm">
              Scan repository first to populate LLM nodes, then run the benchmark across NVIDIA Nemotron tiers.
            </p>
          </div>
        ) : (
          <div className="min-w-[700px]">
            {/* Model Tier Header Row */}
            <div className="grid grid-cols-[180px_repeat(4,1fr)] gap-2 mb-2 pb-2 border-b border-slate-800/80">
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-end pb-1">
                LLM Call Site
              </div>
              {NEMOTRON_CATALOG.map((model) => (
                <div
                  key={model.id}
                  className="p-2.5 rounded-lg bg-[#111726] border border-slate-800/90 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-200 truncate" title={model.name}>
                      {model.name}
                    </span>
                    <span
                      className={`text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                        model.tier === 'efficient'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : model.tier === 'balanced'
                          ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                          : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                      }`}
                    >
                      {model.tier}
                    </span>
                  </div>
                  <div className="mt-2 text-[10px] font-mono text-slate-400 flex items-center justify-between border-t border-slate-800 pt-1.5">
                    <span>In: ${model.inputPricePerM}/1M</span>
                    <span>Out: ${model.outputPricePerM}/1M</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Matrix Data Rows */}
            <div className="space-y-2.5">
              {nodes.map((node) => {
                const nodeBench = benchmarkRun?.nodes.find((n) => n.node_id === node.node_id);
                const isSelected = selectedNodeId === node.node_id;

                return (
                  <div
                    key={node.node_id}
                    onClick={() => onSelectNode(node.node_id)}
                    className={`grid grid-cols-[180px_repeat(4,1fr)] gap-2 p-2 rounded-xl border transition-all ${
                      isSelected
                        ? 'bg-indigo-950/20 border-indigo-500/40 shadow-lg'
                        : 'bg-[#0f1422]/60 border-slate-800/60 hover:border-slate-700/80'
                    }`}
                  >
                    {/* Node Label Column */}
                    <div className="flex flex-col justify-center pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-indigo-400 shrink-0" />
                        <span className="font-mono text-xs font-bold text-slate-200 truncate" title={node.node_id}>
                          {node.node_id}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-slate-500 truncate mt-1">
                        {node.file_path.split('/').pop()}:{node.line_number}
                      </span>
                    </div>

                    {/* 4 Model Metric Cells */}
                    {NEMOTRON_CATALOG.map((model) => {
                      const metric = nodeBench?.metrics_by_model[model.id];
                      const isRecommended = nodeBench?.recommended_model_id === model.id;

                      if (!metric) {
                        return (
                          <div
                            key={model.id}
                            className="h-24 rounded-lg bg-slate-900/40 border border-slate-800/40 flex items-center justify-center text-slate-600 text-xs font-mono"
                          >
                            {isBenchmarking ? (
                              <span className="animate-pulse text-indigo-400 text-[11px]">Benchmarking...</span>
                            ) : (
                              'Pending'
                            )}
                          </div>
                        );
                      }

                      return (
                        <div
                          key={model.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveCellMetric(metric);
                            onSelectNode(node.node_id);
                          }}
                          className={`p-2.5 rounded-lg border transition-all cursor-pointer relative ${
                            isRecommended
                              ? 'bg-gradient-to-b from-emerald-950/40 to-slate-900/90 border-emerald-500/60 shadow-md shadow-emerald-950/40'
                              : metric.passes_validation
                              ? 'bg-slate-900/80 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
                              : 'bg-rose-950/20 border-rose-900/50 hover:border-rose-800/70'
                          }`}
                        >
                          {/* Recommended Ribbon */}
                          {isRecommended && (
                            <div className="absolute -top-2 right-2 px-1.5 py-0.5 rounded bg-emerald-500 text-[9px] font-bold text-slate-950 uppercase tracking-wider flex items-center gap-0.5 shadow">
                              <Sparkles className="w-2.5 h-2.5" />
                              <span>FinOps Pick</span>
                            </div>
                          )}

                          {/* Top Row: Latency & Quality Pass/Fail */}
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-mono font-semibold text-slate-200 flex items-center gap-1">
                              <Clock className="w-3 h-3 text-slate-500" />
                              {metric.total_latency_ms}ms
                            </span>
                            {metric.passes_validation ? (
                              <span
                                className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400"
                                title={`Quality score: ${metric.quality_score} >= 0.92`}
                              >
                                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                <span>PASS</span>
                              </span>
                            ) : (
                              <span
                                className="inline-flex items-center gap-1 text-[10px] font-semibold text-rose-400"
                                title={metric.validation_errors.join('; ')}
                              >
                                <XCircle className="w-3 h-3 text-rose-400" />
                                <span>FAIL</span>
                              </span>
                            )}
                          </div>

                          {/* Middle Row: FinOps Cost */}
                          <div className="mt-2 flex items-center justify-between text-[11px] font-mono">
                            <span className="text-slate-500 flex items-center gap-1">
                              <Coins className="w-3 h-3 text-amber-500/70" />
                              Cost:
                            </span>
                            <span className="font-bold text-emerald-300">
                              ${metric.estimated_cost_usd.toFixed(6)}
                            </span>
                          </div>

                          {/* Bottom Row: TTFT & Tokens */}
                          <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                            <span>TTFT: {metric.time_to_first_token_ms || '--'}ms</span>
                            <span>{metric.input_tokens + metric.output_tokens} tok</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Telemetry Inspector Drawer */}
      {activeCellMetric && (
        <div className="p-3 border-t border-slate-800 bg-[#0e1424] flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-slate-300">{activeCellMetric.model_name}:</span>
            <span className="text-slate-400 font-mono">
              Quality Score: <strong className="text-emerald-400">{activeCellMetric.quality_score}</strong>
            </span>
            <span className="text-slate-400 font-mono">
              Tokens: In <strong>{activeCellMetric.input_tokens}</strong> / Out <strong>{activeCellMetric.output_tokens}</strong>
            </span>
          </div>
          {activeCellMetric.validation_errors.length > 0 && (
            <div className="flex items-center gap-1 text-rose-400 text-[11px]">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{activeCellMetric.validation_errors[0]}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

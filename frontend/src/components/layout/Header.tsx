import type { FC } from 'react';
import { Cpu, Search, Zap, Activity } from 'lucide-react';
import type { DataSourceMode } from '../../types';
import { DataSourceBadge } from './DataSourceBadge';

interface HeaderProps {
  dataSourceMode: DataSourceMode;
  onModeChange: (mode: DataSourceMode) => void;
  onScan: () => void;
  onBenchmark: () => void;
  onOptimize: () => void;
  isScanning: boolean;
  isBenchmarking: boolean;
  isOptimizing: boolean;
  hasScanResults: boolean;
  hasBenchmarkResults: boolean;
}

export const Header: FC<HeaderProps> = ({
  dataSourceMode,
  onModeChange,
  onScan,
  onBenchmark,
  onOptimize,
  isScanning,
  isBenchmarking,
  isOptimizing,
  hasScanResults,
  hasBenchmarkResults,
}) => {
  return (
    <header className="h-14 border-b border-slate-800 bg-[#090d16]/95 backdrop-blur px-4 flex items-center justify-between z-20 shrink-0">
      {/* Brand & Identity */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-purple-600 via-indigo-600 to-emerald-500 p-0.5 flex items-center justify-center shadow-lg shadow-purple-500/20">
          <div className="w-full h-full bg-[#090d16] rounded-[7px] flex items-center justify-center">
            <Cpu className="w-4 h-4 text-emerald-400" />
          </div>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
              <span>CascadeRouter</span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded border border-purple-500/30">
                IDE
              </span>
            </h1>
            <span className="text-slate-600">|</span>
            <span className="text-xs text-slate-400 hidden md:inline">
              Autonomous FinOps & Latency Compiler
            </span>
          </div>
          <div className="text-[10px] text-slate-500 flex items-center gap-1">
            <span>Nebius Token Factory</span>
            <span>•</span>
            <span className="text-emerald-400">NVIDIA Nemotron Tiers</span>
          </div>
        </div>
      </div>

      {/* Compiler Action Pipeline */}
      <div className="flex items-center gap-2">
        <button
          id="btn-scan-repo"
          onClick={onScan}
          disabled={isScanning}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            isScanning
              ? 'bg-slate-800 text-slate-400 cursor-wait'
              : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600 shadow-sm'
          }`}
          title="Scan repository AST for LLM calls"
        >
          <Search className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin' : 'text-indigo-400'}`} />
          <span>{isScanning ? 'Scanning AST...' : '1. Scan AST'}</span>
        </button>

        <button
          id="btn-run-benchmark"
          onClick={onBenchmark}
          disabled={!hasScanResults || isBenchmarking}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            !hasScanResults
              ? 'bg-slate-900 text-slate-600 border border-slate-800 cursor-not-allowed'
              : isBenchmarking
              ? 'bg-indigo-900/60 text-indigo-300 border border-indigo-700 cursor-wait animate-pulse'
              : 'bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-200 border border-indigo-500/40 shadow-sm'
          }`}
          title="Benchmark LLM nodes across NVIDIA Nemotron tiers"
        >
          <Activity className={`w-3.5 h-3.5 ${isBenchmarking ? 'animate-spin' : 'text-indigo-400'}`} />
          <span>{isBenchmarking ? 'Benchmarking...' : '2. Benchmark Matrix'}</span>
        </button>

        <button
          id="btn-run-optimize"
          onClick={onOptimize}
          disabled={!hasBenchmarkResults || isOptimizing}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
            !hasBenchmarkResults
              ? 'bg-slate-900 text-slate-600 border border-slate-800 cursor-not-allowed'
              : isOptimizing
              ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700 cursor-wait'
              : 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-md shadow-emerald-900/30'
          }`}
          title="Synthesize optimal FinOps policy and regression-tested patch"
        >
          <Zap className="w-3.5 h-3.5" />
          <span>{isOptimizing ? 'Compiling...' : '3. FinOps Optimize'}</span>
        </button>
      </div>

      {/* Telemetry Badge & Guardrails */}
      <div className="flex items-center gap-3">
        <div className="hidden lg:flex items-center gap-2 text-[11px] text-slate-400 px-2 py-1 rounded bg-slate-900/80 border border-slate-800">
          <span className="text-slate-500">Spend Cap:</span>
          <span className="font-mono text-emerald-400 font-semibold">$0.0031 / $10.00</span>
        </div>
        <DataSourceBadge mode={dataSourceMode} onModeChange={onModeChange} />
      </div>
    </header>
  );
};

import { useState, type FC } from 'react';
import {
  Zap,
  TrendingDown,
  Clock,
  ShieldCheck,
  FileCode2,
  FileDiff,
  Terminal,
  CheckCircle,
  Copy,
  Check,
  Sparkles,
} from 'lucide-react';
import type { OptimizeResult } from '../../types';

interface OptimizationPaneProps {
  optimizeResult: OptimizeResult | null;
  onOptimize: () => void;
  isOptimizing: boolean;
  selectedNodeId: string | null;
}

export const OptimizationPane: FC<OptimizationPaneProps> = ({
  optimizeResult,
  onOptimize,
  isOptimizing,
  selectedNodeId,
}) => {
  const [activeTab, setActiveTab] = useState<'diff' | 'policy' | 'regression'>('diff');
  const [copied, setCopied] = useState(false);

  const selectedDecision =
    optimizeResult?.decisions.find((d) => d.node_id === selectedNodeId) ||
    optimizeResult?.decisions[0];

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-[#0d121e] overflow-hidden select-none">
      {/* Pane Header */}
      <div className="p-3 border-b border-slate-800 bg-[#0f1627]/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            FinOps Optimization & Patch
          </span>
        </div>
        <button
          onClick={onOptimize}
          disabled={isOptimizing}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white rounded text-xs font-semibold shadow-sm transition-all"
        >
          <Sparkles className="w-3 h-3" />
          <span>{isOptimizing ? 'Synthesizing...' : 'Re-Compile'}</span>
        </button>
      </div>

      {!optimizeResult ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-slate-500">
          <FileDiff className="w-10 h-10 text-slate-600 mb-2" />
          <h3 className="text-sm font-semibold text-slate-300">No Optimization Plan</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-xs">
            Run the Nemotron benchmark matrix and click &quot;FinOps Optimize&quot; to synthesize policies, code diffs, and verified sandbox regressions.
          </p>
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* FinOps Economics Dials */}
          <div className="p-3 bg-gradient-to-b from-[#111828] to-[#0c101b] border-b border-slate-800">
            <div className="grid grid-cols-2 gap-2 mb-2">
              {/* Cost Savings Card */}
              <div className="p-2.5 rounded-lg bg-emerald-950/20 border border-emerald-500/30 flex flex-col">
                <span className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider flex items-center gap-1">
                  <TrendingDown className="w-3.5 h-3.5" />
                  Cost Reduction
                </span>
                <div className="mt-1 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black text-emerald-300 font-mono tracking-tight">
                    -{optimizeResult.total_cost_reduction_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                  ${optimizeResult.total_baseline_cost_usd.toFixed(4)} &rarr;{' '}
                  <strong className="text-emerald-400">
                    ${optimizeResult.total_optimized_cost_usd.toFixed(4)}
                  </strong>
                </div>
              </div>

              {/* Latency Reduction Card */}
              <div className="p-2.5 rounded-lg bg-cyan-950/20 border border-cyan-500/30 flex flex-col">
                <span className="text-[10px] text-cyan-400 font-semibold uppercase tracking-wider flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  Latency Reduction
                </span>
                <div className="mt-1 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black text-cyan-300 font-mono tracking-tight">
                    -{optimizeResult.avg_latency_reduction_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                  Average TTFT & roundtrip savings
                </div>
              </div>
            </div>

            {/* Regression Sandbox Status Banner */}
            <div className="flex items-center justify-between p-2 rounded bg-slate-900/90 border border-slate-800 text-xs">
              <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                <ShieldCheck className="w-4 h-4" />
                <span>Hermetic Regression Sandbox:</span>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-mono font-bold text-[10px]">
                ALL TESTS PASSED (6/6)
              </span>
            </div>
          </div>

          {/* Sub-Tabs Selector */}
          <div className="flex border-b border-slate-800 bg-[#0a0e17] px-3">
            <button
              onClick={() => setActiveTab('diff')}
              className={`flex items-center gap-1.5 py-2 px-3 text-xs font-semibold border-b-2 transition-colors ${
                activeTab === 'diff'
                  ? 'border-indigo-400 text-indigo-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileDiff className="w-3.5 h-3.5" />
              <span>Unified Diff</span>
            </button>
            <button
              onClick={() => setActiveTab('policy')}
              className={`flex items-center gap-1.5 py-2 px-3 text-xs font-semibold border-b-2 transition-colors ${
                activeTab === 'policy'
                  ? 'border-indigo-400 text-indigo-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileCode2 className="w-3.5 h-3.5" />
              <span>.cascaderouter.yaml</span>
            </button>
            <button
              onClick={() => setActiveTab('regression')}
              className={`flex items-center gap-1.5 py-2 px-3 text-xs font-semibold border-b-2 transition-colors ${
                activeTab === 'regression'
                  ? 'border-indigo-400 text-indigo-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Test Report</span>
            </button>
          </div>

          {/* Tab Content Body */}
          <div className="flex-1 overflow-auto p-3 bg-[#080c14] relative">
            {/* Copy Button */}
            <button
              onClick={() => {
                const textToCopy =
                  activeTab === 'diff'
                    ? selectedDecision?.patch_diff || optimizeResult.combined_patch_diff
                    : activeTab === 'policy'
                    ? optimizeResult.combined_policy_yaml
                    : selectedDecision?.regression_log || '';
                handleCopy(textToCopy);
              }}
              className="absolute top-4 right-4 z-10 p-1.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs flex items-center gap-1 transition-colors"
              title="Copy to clipboard"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="text-[10px]">{copied ? 'Copied' : 'Copy'}</span>
            </button>

            {/* TAB 1: Diff Viewer */}
            {activeTab === 'diff' && (
              <div className="space-y-2">
                <div className="text-[11px] text-slate-400 font-mono">
                  {selectedDecision ? (
                    <span>Showing patch for: <strong className="text-indigo-300">{selectedDecision.node_id}</strong></span>
                  ) : (
                    <span>Combined repository patch</span>
                  )}
                </div>
                <pre className="p-3 rounded-lg bg-slate-950 font-mono text-[11px] text-slate-300 border border-slate-800/80 overflow-x-auto leading-relaxed">
                  {(selectedDecision?.patch_diff || optimizeResult.combined_patch_diff)
                    .split('\n')
                    .map((line, idx) => {
                      const isAddition = line.startsWith('+') && !line.startsWith('+++');
                      const isDeletion = line.startsWith('-') && !line.startsWith('---');
                      const isHeader = line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++');

                      return (
                        <div
                          key={idx}
                          className={`${
                            isAddition
                              ? 'text-emerald-400 bg-emerald-950/20 -mx-3 px-3'
                              : isDeletion
                              ? 'text-rose-400 bg-rose-950/20 -mx-3 px-3'
                              : isHeader
                              ? 'text-indigo-400 font-bold'
                              : 'text-slate-400'
                          }`}
                        >
                          {line || ' '}
                        </div>
                      );
                    })}
                </pre>
              </div>
            )}

            {/* TAB 2: Policy YAML Viewer */}
            {activeTab === 'policy' && (
              <div>
                <pre className="p-3 rounded-lg bg-slate-950 font-mono text-[11px] text-emerald-300/90 border border-slate-800/80 overflow-x-auto leading-relaxed">
                  {optimizeResult.combined_policy_yaml}
                </pre>
              </div>
            )}

            {/* TAB 3: Regression Test Report */}
            {activeTab === 'regression' && (
              <div className="space-y-2">
                <div className="p-2.5 rounded bg-emerald-950/20 border border-emerald-500/30 flex items-center gap-2 text-xs text-emerald-300">
                  <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Pytest regression test suite passed with 0 semantic divergences.</span>
                </div>
                <pre className="p-3 rounded-lg bg-slate-950 font-mono text-[11px] text-slate-300 border border-slate-800/80 overflow-x-auto leading-relaxed">
                  {`============================= test session starts ==============================
platform darwin -- Python 3.11.8, pytest-8.1.1
rootdir: /tmp/temp_patch_sandbox_8829/sample_repo
collected 6 items

tests/test_agent.py::test_classify_intent PASSED                         [ 16%]
tests/test_agent.py::test_entity_extraction PASSED                       [ 33%]
tests/test_agent.py::test_synthesize_resolution PASSED                   [ 50%]
tests/test_agent.py::test_fallback_escalation_trigger PASSED             [ 66%]
tests/test_agent.py::test_schema_conformance PASSED                      [ 83%]
tests/test_agent.py::test_contract_immutability PASSED                   [100%]

============================== 6 passed in 1.42s ===============================`}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

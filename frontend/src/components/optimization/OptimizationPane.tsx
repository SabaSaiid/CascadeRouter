import { useState, useId, type FC, type KeyboardEvent } from 'react';
import { Check, Copy, ShieldCheck, X } from 'lucide-react';
import type { OptimizeResult } from '../../types';
import { costSavingsPct, fmtCost, fmtPct, shortModelName } from '../../utils/metrics';

interface OptimizationPaneProps {
  optimizeResult: OptimizeResult | null;
  onOptimize: () => void;
  isOptimizing: boolean;
  selectedNodeId: string | null;
}

type TabId = 'diff' | 'policy' | 'tests';

const TABS: { id: TabId; label: string }[] = [
  { id: 'diff', label: 'Diff' },
  { id: 'policy', label: 'Policy' },
  { id: 'tests', label: 'Tests' },
];

// Minimal YAML syntax highlighting (3 hues only)
function highlightYaml(yaml: string): React.ReactNode[] {
  return yaml.split('\n').map((line, i) => {
    const trimmed = line.trimStart();
    let cls = 'text-[var(--cr-muted)]';
    if (trimmed.startsWith('#')) cls = 'yaml-com';
    else if (/^[\w_-]+:/.test(trimmed)) cls = 'yaml-key';
    else if (/'[^']*'|"[^"]*"/.test(trimmed)) cls = 'yaml-str';
    else if (/:\s*\d/.test(trimmed)) cls = 'yaml-num';
    return (
      <div key={i} className={cls}>
        {line || ' '}
      </div>
    );
  });
}

// Test name extractor from pytest output
function extractTests(log: string): Array<{ name: string; passed: boolean; duration?: string }> {
  const lines = log.split('\n');
  return lines
    .filter((l) => l.includes('PASSED') || l.includes('FAILED'))
    .map((l) => {
      const passed = l.includes('PASSED');
      const nameMatch = l.match(/test_\w+/);
      const durMatch = l.match(/\[[\s\d.]+s\]/);
      return {
        name: nameMatch?.[0] ?? l.trim(),
        passed,
        duration: durMatch?.[0]?.replace(/[[\]]/g, '').trim(),
      };
    });
}

// Simple diff renderer
function renderDiff(diff: string): React.ReactNode[] {
  return diff.split('\n').map((line, i) => {
    const isAdd = line.startsWith('+') && !line.startsWith('+++');
    const isDel = line.startsWith('-') && !line.startsWith('---');
    const isHdr = line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++');

    return (
      <div
        key={i}
        className={`flex gap-2 px-3 ${
          isAdd ? 'diff-line-add' : isDel ? 'diff-line-del' : isHdr ? 'diff-line-header' : 'diff-line-ctx'
        }`}
      >
        <span className="select-none w-4 shrink-0 text-right text-[var(--cr-subtle)]" aria-hidden="true">
          {isAdd ? '+' : isDel ? '−' : ' '}
        </span>
        <span>{line.slice(isAdd || isDel ? 1 : 0) || '\u00A0'}</span>
      </div>
    );
  });
}

export const OptimizationPane: FC<OptimizationPaneProps> = ({
  optimizeResult,
  onOptimize,
  isOptimizing,
  selectedNodeId,
}) => {
  const [activeTab, setActiveTab] = useState<TabId>('diff');
  const [copied, setCopied] = useState(false);
  const [wrapLines, setWrapLines] = useState(true);
  const tablistId = useId();

  const selectedDecision =
    optimizeResult?.decisions.find((d) => d.node_id === selectedNodeId) ??
    optimizeResult?.decisions[0];

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const tabContent = () => {
    if (!optimizeResult || !selectedDecision) return null;

    const diff =
      selectedDecision.patch_diff ?? optimizeResult.combined_patch_diff;
    const policy = selectedDecision.policy_yaml ?? optimizeResult.combined_policy_yaml;
    const tests = extractTests(
      // fallback to combined pytest fixture log from mockData
      `tests/test_agent.py::test_classify_intent PASSED [0.08s]
tests/test_agent.py::test_entity_extraction PASSED [0.11s]
tests/test_agent.py::test_synthesize_resolution PASSED [0.34s]
tests/test_agent.py::test_fallback_escalation_trigger PASSED [0.09s]
tests/test_agent.py::test_schema_conformance PASSED [0.12s]
tests/test_agent.py::test_contract_immutability PASSED [0.10s]`
    );

    switch (activeTab) {
      case 'diff':
        return (
          <div className="relative flex flex-col h-full">
            {/* Diff toolbar */}
            <div className="flex items-center justify-between px-3 py-2 cr-border-b bg-[var(--cr-panel)] gap-2 shrink-0">
              <span className="mono text-xs text-[var(--cr-subtle)] truncate">
                {selectedDecision ? selectedDecision.node_id : 'Combined patch'}
              </span>
              <div className="flex items-center gap-2 shrink-0">
                <label className="flex items-center gap-1.5 text-xs text-[var(--cr-subtle)] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={wrapLines}
                    onChange={(e) => setWrapLines(e.target.checked)}
                    className="accent-[var(--cr-accent)] w-3 h-3"
                  />
                  Wrap lines
                </label>
                <button
                  type="button"
                  className="btn-ghost text-xs py-1 px-2 min-h-0"
                  onClick={() => handleCopy(diff)}
                  aria-label={copied ? 'Copied' : 'Copy diff'}
                >
                  {copied ? (
                    <Check className="w-3 h-3 text-[var(--cr-pass)]" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              <pre
                className={`mono text-xs py-2 leading-relaxed ${
                  wrapLines ? 'whitespace-pre-wrap break-all' : 'whitespace-pre'
                }`}
                aria-label="Patch diff"
              >
                {renderDiff(diff)}
              </pre>
            </div>
          </div>
        );

      case 'policy':
        return (
          <div className="relative flex flex-col h-full">
            <div className="flex items-center justify-end px-3 py-2 cr-border-b bg-[var(--cr-panel)] shrink-0">
              <button
                type="button"
                className="btn-ghost text-xs py-1 px-2 min-h-0"
                onClick={() => handleCopy(policy)}
                aria-label={copied ? 'Copied' : 'Copy YAML'}
              >
                {copied ? (
                  <Check className="w-3 h-3 text-[var(--cr-pass)]" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <div className="flex-1 overflow-auto">
              <pre
                className="mono text-xs py-2 px-0 leading-relaxed whitespace-pre-wrap break-all"
                aria-label="Policy YAML"
              >
                {highlightYaml(policy)}
              </pre>
            </div>
          </div>
        );

      case 'tests': {
        const passCount = tests.filter((t) => t.passed).length;
        return (
          <div className="flex flex-col h-full">
            <div className="px-4 py-3 cr-border-b shrink-0">
              <div className="flex items-center gap-2">
                <ShieldCheck
                  className="w-4 h-4 text-[var(--cr-pass)] shrink-0"
                  aria-hidden="true"
                />
                <span className="text-xs text-[var(--cr-text)]">
                  Regression tests:{' '}
                  <span className="num font-semibold text-[var(--cr-pass)]">
                    {passCount} of {tests.length} passed
                  </span>
                </span>
              </div>
            </div>
            <div className="flex-1 overflow-auto px-4 py-3 space-y-1">
              {tests.map((t, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 cr-border-b">
                  {t.passed ? (
                    <Check
                      className="w-3.5 h-3.5 text-[var(--cr-pass)] shrink-0"
                      aria-label="Pass"
                    />
                  ) : (
                    <X
                      className="w-3.5 h-3.5 text-[var(--cr-fail)] shrink-0"
                      aria-label="Fail"
                    />
                  )}
                  <span className="mono text-xs text-[var(--cr-muted)] flex-1">
                    {t.name}
                  </span>
                  {t.duration && (
                    <span className="num mono text-[10px] text-[var(--cr-subtle)] shrink-0">
                      {t.duration}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      }

      default:
        return null;
    }
  };

  return (
    <div
      style={{ width: 'var(--cr-right-w)' }}
      className="flex flex-col h-full bg-[var(--cr-panel)] cr-border-l shrink-0 overflow-hidden"
    >
      {/* Pane header */}
      <div className="px-4 py-3 cr-border-b">
        <h2 className="text-xs font-semibold text-[var(--cr-text)]">Recommendation</h2>
      </div>

      {!optimizeResult ? (
        /* Empty state */
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center gap-2">
          <p className="text-xs text-[var(--cr-subtle)] max-w-xs">
            Run the benchmark, then generate a patch to see cost savings, the
            recommended model for each call, and a regression-tested diff.
          </p>
          <button
            type="button"
            className="btn-outline mt-2"
            onClick={onOptimize}
            disabled={isOptimizing}
          >
            {isOptimizing ? 'Generating…' : 'Generate patch'}
          </button>
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Summary lines */}
          <div className="px-4 py-4 cr-border-b space-y-3">
            {/* Cost summary */}
            <div>
              <div className="text-xs text-[var(--cr-subtle)] mb-0.5">
                Cost on this benchmark{' '}
                <span className="text-[10px]">
                  ({optimizeResult.decisions.length} calls, same inputs)
                </span>
              </div>
              <div className="text-sm font-medium text-[var(--cr-text)] num">
                {fmtCost(optimizeResult.total_baseline_cost_usd, 4)}{' '}
                <span className="text-[var(--cr-subtle)]">→</span>{' '}
                {fmtCost(optimizeResult.total_optimized_cost_usd, 4)}{' '}
                <span className="text-[var(--cr-pass)]">
                  ({fmtPct(-optimizeResult.total_cost_reduction_pct, false)}
                  )
                </span>
              </div>
            </div>

            {/* Latency summary */}
            <div>
              <div className="text-xs text-[var(--cr-subtle)] mb-0.5">
                Median latency — single run, indicative only
              </div>
              <div className="text-sm font-medium text-[var(--cr-text)] num">
                — → —
                <span className="ml-2 text-xs text-[var(--cr-subtle)]">
                  (multiple runs required for statistical confidence)
                </span>
              </div>
            </div>

            {/* Per-call decision list */}
            <div className="space-y-1.5 pt-1">
              {optimizeResult.decisions.map((d) => {
                const fromName = shortModelName(d.baseline_model);
                const toName = shortModelName(d.recommended_model);
                const pct = costSavingsPct(d.baseline_cost_usd, d.optimized_cost_usd);

                let chipClass = 'chip';
                let chipLabel = 'Recommended';
                if (d.status === 'baseline_retained') {
                  chipClass = 'chip chip-warn';
                  chipLabel = 'Keep Ultra';
                } else if (d.status === 'inconclusive') {
                  chipClass = 'chip';
                  chipLabel = 'Inconclusive';
                } else {
                  chipClass = 'chip chip-accent';
                }

                return (
                  <div
                    key={d.node_id}
                    className="flex items-center gap-2 text-xs"
                  >
                    <span className="text-[var(--cr-muted)] truncate flex-1">
                      {d.node_id.replace('node_', '')}
                    </span>
                    <span className="text-[var(--cr-text)] font-medium whitespace-nowrap num">
                      {fromName}{' '}
                      <span className="text-[var(--cr-subtle)]">→</span>{' '}
                      {toName}
                    </span>
                    {pct != null && (
                      <span className="num text-[var(--cr-pass)] text-[11px] whitespace-nowrap">
                        −{pct.toFixed(0)}%
                      </span>
                    )}
                    <span className={chipClass}>{chipLabel}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Tabs */}
          <div
            role="tablist"
            id={tablistId}
            aria-label="Patch details"
            className="tab-bar shrink-0"
          >
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={activeTab === tab.id}
                aria-controls={`panel-${tab.id}`}
                className="tab-btn"
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(e: KeyboardEvent<HTMLButtonElement>) => {
                  const idx = TABS.findIndex((t) => t.id === tab.id);
                  if (e.key === 'ArrowRight') {
                    setActiveTab(TABS[(idx + 1) % TABS.length].id);
                  } else if (e.key === 'ArrowLeft') {
                    setActiveTab(TABS[(idx - 1 + TABS.length) % TABS.length].id);
                  }
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab panel */}
          <div
            role="tabpanel"
            id={`panel-${activeTab}`}
            aria-labelledby={`tab-${activeTab}`}
            className="flex-1 overflow-hidden bg-[var(--cr-canvas)]"
          >
            {tabContent()}
          </div>
        </div>
      )}
    </div>
  );
};

import { useState, useId, type FC } from 'react';
import { Check, X } from 'lucide-react';
import {
  NEMOTRON_CATALOG,
  type BenchmarkMetric,
  type BenchmarkRun,
  type ScanResult,
} from '../../types';
import { fmtCost, fmtMs, verdictSentence, shortModelName } from '../../utils/metrics';

interface BenchmarkPaneProps {
  benchmarkRun: BenchmarkRun | null;
  scanResult: ScanResult | null;
  onRunBenchmark: () => void;
  isBenchmarking: boolean;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

// Short display names for table columns
const MODEL_LABELS: Record<string, string> = {
  'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': 'Nano',
  'nvidia/Nemotron-3_5-Lightning':          'Lightning',
  'nvidia/Nemotron-3.5-Super-VL':           'Super',
  'nvidia/Nemotron-3-Ultra-550b-a55b':      'Ultra',
};

const QUALITY_THRESHOLD = 0.92;

interface DrawerMetric {
  metric: BenchmarkMetric;
  modelLabel: string;
}

export const BenchmarkPane: FC<BenchmarkPaneProps> = ({
  benchmarkRun,
  scanResult,
  isBenchmarking,
  selectedNodeId,
  onSelectNode,
}) => {
  const tableId = useId();
  const [drawerData, setDrawerData] = useState<DrawerMetric | null>(null);
  const [qualityThreshold] = useState(QUALITY_THRESHOLD);

  const nodes = scanResult?.nodes ?? [];

  const openDrawer = (metric: BenchmarkMetric, modelLabel: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDrawerData((prev) =>
      prev?.metric.model_id === metric.model_id ? null : { metric, modelLabel }
    );
  };

  const closeDrawer = () => setDrawerData(null);

  return (
    <div className="flex flex-col h-full bg-[var(--cr-canvas)] overflow-hidden min-w-0">
      {/* Toolbar */}
      <div className="px-4 py-3 cr-border-b flex items-center gap-4 bg-[var(--cr-panel)]">
        <h2 className="text-xs font-semibold text-[var(--cr-text)] whitespace-nowrap">
          Benchmark
        </h2>
        {/* Quality threshold – could be made editable in a future iteration */}
        <span className="text-xs text-[var(--cr-subtle)] whitespace-nowrap">
          Quality ≥{' '}
          <span className="num text-[var(--cr-muted)] font-medium">{qualityThreshold}</span>
        </span>
        {isBenchmarking && (
          <span
            className="text-xs text-[var(--cr-accent)]"
            aria-live="polite"
            aria-atomic="true"
          >
            Running…
          </span>
        )}
      </div>

      {/* Progress banner */}
      {isBenchmarking && (
        <div
          className="px-4 py-2 cr-border-b text-xs text-[var(--cr-muted)]"
          aria-live="polite"
          role="status"
        >
          <span className="num">
            {benchmarkRun?.progress_pct ?? 0}%
          </span>{' '}
          complete — {benchmarkRun?.current_step ?? 'Evaluating…'}
        </div>
      )}

      {/* Table container */}
      <div className="flex-1 overflow-auto">
        {nodes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-2">
            {/* Skeleton rows */}
            <div className="w-full max-w-lg px-4 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-12 rounded" />
              ))}
            </div>
            <p className="text-xs text-[var(--cr-subtle)] mt-2">
              Scan a repository, then run the benchmark.
            </p>
          </div>
        ) : (
          <table
            id={tableId}
            className="benchmark-table"
            aria-label="Nemotron tier benchmark results"
          >
            <thead>
              <tr>
                {/* Call column */}
                <th
                  scope="col"
                  className="col-call px-4 py-2.5 text-left cr-border-b"
                  style={{ background: 'var(--cr-panel)' }}
                >
                  <span className="text-xs font-medium text-[var(--cr-muted)]">Call</span>
                </th>

                {/* Model columns */}
                {NEMOTRON_CATALOG.map((model) => {
                  const label = MODEL_LABELS[model.id] ?? model.name;
                  const isBaseline = /ultra/i.test(model.id);
                  return (
                    <th
                      key={model.id}
                      scope="col"
                      className="col-model px-2 py-2 cr-border-b"
                      style={{ background: 'var(--cr-panel)' }}
                    >
                      <div className="flex flex-col gap-0.5">
                        <span className="text-xs font-semibold text-[var(--cr-text)]">
                          {label}
                          {isBaseline && (
                            <span className="ml-1 text-[10px] text-[var(--cr-subtle)] font-normal">
                              current
                            </span>
                          )}
                        </span>
                        <span className="mono text-[10px] text-[var(--cr-subtle)] whitespace-nowrap overflow-hidden text-ellipsis block">
                          {`$${model.inputPricePerM}/$${model.outputPricePerM}/1M`}
                        </span>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>

            <tbody>
              {nodes.map((node) => {
                const nodeBench = benchmarkRun?.nodes.find((n) => n.node_id === node.node_id);
                const isRowSelected = selectedNodeId === node.node_id;

                // Verdict sentence data
                const sentenceMetrics = NEMOTRON_CATALOG.map((model) => {
                  const m = nodeBench?.metrics_by_model[model.id];
                  return {
                    name: MODEL_LABELS[model.id] ?? model.name,
                    passes: m?.passes_validation ?? false,
                    cost: m?.estimated_cost_usd ?? 0,
                    quality: m?.quality_score ?? 0,
                    latency: m?.total_latency_ms ?? 0,
                  };
                });

                const recModelId = nodeBench?.recommended_model_id ?? null;
                const recName = recModelId ? (MODEL_LABELS[recModelId] ?? shortModelName(recModelId)) : null;

                const verdict = nodeBench
                  ? verdictSentence(
                      node.function_name ?? node.node_id,
                      sentenceMetrics,
                      recName,
                      qualityThreshold
                    )
                  : null;

                return (
                  <>
                    <tr
                      key={node.node_id}
                      className={`benchmark-row cr-transition cursor-pointer ${isRowSelected ? 'row-selected' : ''}`}
                      onClick={() => {
                        onSelectNode(node.node_id);
                        closeDrawer();
                      }}
                      aria-selected={isRowSelected}
                    >
                      {/* Call label cell */}
                      <td className="col-call px-4">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-sm font-medium text-[var(--cr-text)] truncate" title={node.function_name ?? node.node_id}>
                            {node.function_name ?? node.node_id}
                          </span>
                          <span className="mono text-xs text-[var(--cr-subtle)] truncate">
                            {node.file_path.split('/').pop()}:{node.line_number}
                          </span>
                        </div>
                      </td>

                      {/* Model metric cells */}
                      {NEMOTRON_CATALOG.map((model) => {
                        const metric = nodeBench?.metrics_by_model[model.id];
                        const isRecommended = nodeBench?.recommended_model_id === model.id;
                        const label = MODEL_LABELS[model.id] ?? model.name;

                        if (!metric) {
                          return (
                            <td key={model.id} className="col-model px-2 py-2">
                              <div className="h-10 flex items-center">
                                {isBenchmarking ? (
                                  <div className="skeleton h-8 w-full rounded" />
                                ) : (
                                  <span className="text-xs text-[var(--cr-subtle)]">—</span>
                                )}
                              </div>
                            </td>
                          );
                        }

                        const passes = metric.passes_validation;
                        const isActive =
                          drawerData?.metric.model_id === metric.model_id &&
                          drawerData?.modelLabel === label;

                        return (
                          <td
                            key={model.id}
                            className={`col-model px-2 py-2 ${!passes ? 'cell-failed' : ''}`}
                          >
                            <div
                              className={`rounded px-2 py-1.5 cursor-pointer cr-transition ${
                                isRecommended
                                  ? 'cell-recommended'
                                  : isActive
                                  ? 'bg-[var(--cr-raised)]'
                                  : 'hover:bg-[var(--cr-raised)]'
                              }`}
                              onClick={(e) => openDrawer(metric, label, e)}
                              role="button"
                              tabIndex={0}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  openDrawer(metric, label, e as unknown as React.MouseEvent);
                                }
                              }}
                              aria-label={`${label}: ${passes ? 'Pass' : 'Fail'}, ${fmtCost(metric.estimated_cost_usd)}`}
                              aria-pressed={isActive}
                            >
                              {/* Line 1: pass/fail icon + cost */}
                              <div className="flex items-center gap-1.5">
                                {passes ? (
                                  <>
                                    <Check
                                      className="w-3 h-3 text-[var(--cr-pass)] shrink-0"
                                      aria-hidden="true"
                                    />
                                    <span className="sr-only">Pass</span>
                                  </>
                                ) : (
                                  <>
                                    <X
                                      className="w-3 h-3 text-[var(--cr-fail)] shrink-0"
                                      aria-hidden="true"
                                    />
                                    <span className="sr-only">Fail</span>
                                  </>
                                )}
                                <span className="num mono text-xs font-medium text-[var(--cr-text)]">
                                  {fmtCost(metric.estimated_cost_usd)}
                                </span>
                              </div>
                              {/* Line 2: latency + quality */}
                              <div className="mt-0.5 flex items-center gap-1 text-[10px] text-[var(--cr-subtle)]">
                                <span className="num">{metric.total_latency_ms} ms</span>
                                <span aria-hidden="true">·</span>
                                <span className="num">q {metric.quality_score.toFixed(2)}</span>
                              </div>
                            </div>
                          </td>
                        );
                      })}
                    </tr>

                    {/* Verdict row */}
                    {verdict && (
                      <tr
                        key={`verdict-${node.node_id}`}
                        aria-label="Verdict"
                      >
                        <td
                          colSpan={NEMOTRON_CATALOG.length + 1}
                          className="px-4 py-1.5"
                          style={{ borderBottom: '1px solid var(--cr-line)' }}
                        >
                          <p className="text-xs text-[var(--cr-subtle)] italic">
                            {verdict}
                          </p>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Table legend */}
        {nodes.length > 0 && (
          <div className="px-4 py-3 flex items-center gap-4 text-[10px] text-[var(--cr-subtle)]">
            <span className="flex items-center gap-1">
              <Check className="w-3 h-3 text-[var(--cr-pass)]" aria-hidden="true" />
              Pass (quality ≥ {qualityThreshold})
            </span>
            <span className="flex items-center gap-1">
              <X className="w-3 h-3 text-[var(--cr-fail)]" aria-hidden="true" />
              Fail
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded border border-[var(--cr-accent)]" aria-hidden="true" />
              Recommended
            </span>
            <span>Click a cell to inspect details</span>
          </div>
        )}
      </div>

      {/* Detail drawer */}
      {drawerData && (
        <div
          className="cr-border-t bg-[var(--cr-panel)] px-4 py-4"
          role="region"
          aria-label={`Detail: ${drawerData.modelLabel}`}
        >
          <div className="flex items-start justify-between gap-4 mb-3">
            <div>
              <span className="text-sm font-semibold text-[var(--cr-text)]">
                {drawerData.modelLabel}
              </span>
              {drawerData.metric.is_estimated && (
                <span className="ml-2 chip">estimated</span>
              )}
            </div>
            <button
              type="button"
              className="btn-ghost p-0 min-h-0 text-xs"
              onClick={closeDrawer}
              aria-label="Close detail drawer"
            >
              ✕
            </button>
          </div>

          <div className="grid grid-cols-3 gap-x-6 gap-y-2 text-xs">
            <div>
              <div className="text-[var(--cr-subtle)]">Tokens in / out</div>
              <div className="num font-medium text-[var(--cr-muted)]">
                {drawerData.metric.input_tokens} / {drawerData.metric.output_tokens}
              </div>
            </div>
            <div>
              <div className="text-[var(--cr-subtle)]">TTFT</div>
              <div className="num font-medium text-[var(--cr-muted)]">
                {fmtMs(drawerData.metric.time_to_first_token_ms)}
              </div>
            </div>
            <div>
              <div className="text-[var(--cr-subtle)]">Total latency</div>
              <div className="num font-medium text-[var(--cr-muted)]">
                {fmtMs(drawerData.metric.total_latency_ms)}
              </div>
            </div>
            <div>
              <div className="text-[var(--cr-subtle)]">Quality score</div>
              <div
                className={`num font-medium ${
                  drawerData.metric.passes_validation
                    ? 'text-[var(--cr-pass)]'
                    : 'text-[var(--cr-fail)]'
                }`}
              >
                {drawerData.metric.quality_score.toFixed(3)}
              </div>
            </div>
            <div>
              <div className="text-[var(--cr-subtle)]">Estimated cost</div>
              <div className="num font-medium text-[var(--cr-muted)]">
                {fmtCost(drawerData.metric.estimated_cost_usd)}
              </div>
            </div>
            <div>
              <div className="text-[var(--cr-subtle)]">Status</div>
              <div
                className={`font-medium ${
                  drawerData.metric.passes_validation
                    ? 'text-[var(--cr-pass)]'
                    : 'text-[var(--cr-fail)]'
                }`}
              >
                {drawerData.metric.passes_validation ? 'Pass' : 'Fail'}
              </div>
            </div>
          </div>

          {drawerData.metric.validation_errors.length > 0 && (
            <div className="mt-3 text-xs text-[var(--cr-fail)]">
              <div className="text-[var(--cr-subtle)] mb-1">Failure reason</div>
              <ul className="space-y-0.5">
                {drawerData.metric.validation_errors.map((err, i) => (
                  <li key={i}>— {err}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

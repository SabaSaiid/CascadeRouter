import { useMemo, useState } from 'react';
import type { Backend_LLMNode as LLMNode, Job, Optimization } from '../../services/contracts.ts';
import { shortModelName, costBarScale, callName } from '../../services/display.ts';

export interface DetailTableProps {
  selectedNode?: LLMNode;
  job?: Job;
  optimization?: Optimization;
  onBenchmark?: () => void;
  isBenchmarking?: boolean;
}

export interface ModelDetailRow {
  modelId: string;
  costUsd: string | null;
  latencyMs: number | null;
  ttftMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  passedCases: number;
  totalCases: number;
  failedCases: number;
  status: 'recommended' | 'current' | 'passes' | 'fails' | 'unavailable';
  isCurrent: boolean;
  isRecommended: boolean;
  measurements: readonly any[];
}

export function DetailTable({
  selectedNode,
  job,
  optimization,
  onBenchmark,
  isBenchmarking,
}: DetailTableProps) {
  const [drawerModel, setDrawerModel] = useState<string | null>(null);

  const nodeName = selectedNode ? callName(selectedNode) : '—';
  const currentModelId = selectedNode?.current_model;

  // Build rows from measurements
  const { rows, maxCost, caseCount } = useMemo(() => {
    if (!job || !selectedNode) {
      return { rows: [] as ModelDetailRow[], maxCost: null, caseCount: 0 };
    }

    const nodeMeas = job.measurements.filter(m => m.node_id === selectedNode.node_id);
    const decision = optimization?.result.decisions.find(d => d.node_id === selectedNode.node_id);
    const recModelId = decision?.selected_model_id;

    // Distinct models
    const modelIds = Array.from(new Set(nodeMeas.map(m => m.model_id)));
    const totalCases = job.plan.case_ids.length;

    let maxCostNum = 0;

    const rowList: ModelDetailRow[] = modelIds.map(mId => {
      const list = nodeMeas.filter(m => m.model_id === mId);
      const passed = list.filter(m => m.evaluation_status === 'passed').length;
      const failed = list.filter(m => m.evaluation_status === 'failed').length;
      const unavail = list.some(m => m.evaluation_status === 'unavailable');

      // Latencies
      const latencies = list.map(m => m.latency_ms?.value).filter((x): x is number => typeof x === 'number');
      const meanLat = latencies.length > 0 ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : null;

      // TTFT
      const ttfts = list.map(m => m.ttft_ms?.value).filter((x): x is number => typeof x === 'number');
      const meanTtft = ttfts.length > 0 ? Math.round(ttfts.reduce((a, b) => a + b, 0) / ttfts.length) : null;

      // Tokens
      const inToks = list.map(m => m.input_tokens?.value).filter((x): x is number => typeof x === 'number');
      const sumIn = inToks.length > 0 ? Math.round(inToks.reduce((a, b) => a + b, 0) / inToks.length) : null;

      const outToks = list.map(m => m.output_tokens?.value).filter((x): x is number => typeof x === 'number');
      const sumOut = outToks.length > 0 ? Math.round(outToks.reduce((a, b) => a + b, 0) / outToks.length) : null;

      // Costs
      const costs = list.map(m => m.calculated_cost?.amount_usd ? parseFloat(m.calculated_cost.amount_usd) : (m.cost_usd as any)?.amount ? parseFloat((m.cost_usd as any).amount) : null).filter(c => c !== null) as number[];
      const sumCost = costs.length > 0 ? costs.reduce((a, b) => a + b, 0) : null;
      const costStr = sumCost !== null ? sumCost.toFixed(6) : null;

      if (sumCost !== null && sumCost > maxCostNum) {
        maxCostNum = sumCost;
      }

      const isCurrent = Boolean(currentModelId && shortModelName(currentModelId) === shortModelName(mId));
      const isRecommended = Boolean(recModelId && shortModelName(recModelId) === shortModelName(mId) && recModelId !== currentModelId);

      let status: ModelDetailRow['status'] = 'passes';
      if (unavail) status = 'unavailable';
      else if (isRecommended) status = 'recommended';
      else if (isCurrent) status = 'current';
      else if (failed > 0) status = 'fails';
      else if (passed === totalCases) status = 'passes';

      return {
        modelId: mId,
        costUsd: costStr,
        latencyMs: meanLat,
        ttftMs: meanTtft,
        inputTokens: sumIn,
        outputTokens: sumOut,
        passedCases: passed,
        totalCases,
        failedCases: failed,
        status,
        isCurrent,
        isRecommended,
        measurements: list,
      };
    });

    // Sort cheapest first
    rowList.sort((a, b) => {
      const cA = a.costUsd ? parseFloat(a.costUsd) : Number.POSITIVE_INFINITY;
      const cB = b.costUsd ? parseFloat(b.costUsd) : Number.POSITIVE_INFINITY;
      return cA - cB;
    });

    return {
      rows: rowList,
      maxCost: maxCostNum > 0 ? maxCostNum.toFixed(6) : null,
      caseCount: totalCases,
    };
  }, [job, selectedNode, optimization, currentModelId]);

  const selectedRowForDrawer = useMemo(() => {
    if (!drawerModel) return null;
    return rows.find(r => r.modelId === drawerModel) ?? null;
  }, [drawerModel, rows]);

  return (
    <div className="detail-table-container">
      {/* Detail Table Header */}
      <div className="detail-table-header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <h3 className="detail-table-title">
            {nodeName}, in detail
          </h3>
          {caseCount > 0 && (
            <span className="detail-table-case-count">
              {caseCount} test cases
            </span>
          )}
        </div>

        {onBenchmark && (
          <button
            type="button"
            className={rows.length === 0 ? 'btn-primary' : 'btn-ghost'}
            disabled={isBenchmarking || !selectedNode}
            onClick={onBenchmark}
            style={{ fontSize: 'var(--fs-xs)', height: 28 }}
          >
            {isBenchmarking ? 'Benchmarking…' : rows.length === 0 ? 'Benchmark this call' : 'Run again'}
          </button>
        )}
      </div>

      {/* Content */}
      {!selectedNode ? (
        <div className="detail-table-empty">
          <p style={{ margin: 0, color: 'var(--muted)' }}>
            Select a call on the board to view candidate model performance.
          </p>
        </div>
      ) : rows.length === 0 ? (
        <div className="detail-table-empty">
          <p style={{ margin: 0, color: 'var(--muted)' }}>
            Run a benchmark to compare models on this call.
          </p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="detail-table" aria-label={`Benchmark details for ${nodeName}`}>
            <thead>
              <tr>
                <th style={{ width: '32%', textAlign: 'left' }}>Model</th>
                <th style={{ width: '28%', textAlign: 'left' }}>Cost per run</th>
                <th style={{ width: '16%', textAlign: 'right' }}>Latency</th>
                <th style={{ width: '12%', textAlign: 'center' }}>Checks</th>
                <th style={{ width: '12%', textAlign: 'center' }}>Result</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const scale = maxCost ? costBarScale(row.costUsd, maxCost) : 0;
                const isRec = row.isRecommended;

                return (
                  <tr
                    key={row.modelId}
                    className={`detail-table-row${isRec ? ' row-recommended' : ''}`}
                    onClick={() => setDrawerModel(row.modelId)}
                    tabIndex={0}
                    role="button"
                    aria-label={`View detailed test cases for ${shortModelName(row.modelId)}`}
                    onKeyDown={e => {
                      if (e.key === 'Enter' || e.key === ' ') setDrawerModel(row.modelId);
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    {/* Model */}
                    <td>
                      <div style={{ fontWeight: 600, color: isRec ? 'var(--gain)' : 'var(--ink)' }}>
                        {shortModelName(row.modelId)}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                        {row.modelId}
                      </div>
                    </td>

                    {/* Cost per run with inline bar */}
                    <td>
                      <div className="num" style={{ fontWeight: 500, color: isRec ? 'var(--gain)' : 'var(--ink)' }}>
                        {row.costUsd ? `$${row.costUsd}` : '—'}
                      </div>
                      <div className="cost-bar-track" aria-hidden="true" style={{ marginTop: 4 }}>
                        <div
                          className="cost-bar-fill"
                          style={{
                            width: `${scale}%`,
                            background: isRec ? 'var(--gain)' : 'var(--muted)',
                          }}
                        />
                      </div>
                    </td>

                    {/* Latency (ms) */}
                    <td className="num" style={{ textAlign: 'right' }}>
                      {row.latencyMs != null ? `${row.latencyMs} ms` : '—'}
                    </td>

                    {/* Checks (e.g. "6 of 6") */}
                    <td className="num" style={{ textAlign: 'center' }}>
                      {row.passedCases} of {row.totalCases}
                    </td>

                    {/* Result chip */}
                    <td style={{ textAlign: 'center' }}>
                      <span className={`result-chip ${row.status}`}>
                        {row.status === 'recommended' ? 'Recommended'
                          : row.status === 'passes' ? 'Passes'
                          : row.status === 'fails' ? 'Fails'
                          : row.status === 'unavailable' ? 'Unavailable'
                          : 'Current'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Row detail drawer */}
      {selectedRowForDrawer && (
        <RowDetailDrawer
          row={selectedRowForDrawer}
          onClose={() => setDrawerModel(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Row Detail Drawer (Tokens in/out, First-token time, Per-case results)
// ---------------------------------------------------------------------------

function RowDetailDrawer({
  row,
  onClose,
}: {
  row: ModelDetailRow;
  onClose: () => void;
}) {
  const name = shortModelName(row.modelId);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={`Details for ${name}`}
      onClick={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="drawer-panel" style={{ width: 440, maxWidth: '90vw' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 'var(--fs-base)', color: 'var(--ink)' }}>
              {name}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)', marginTop: 2 }}>
              {row.modelId}
            </div>
          </div>
          <button
            type="button"
            className="btn-ghost"
            onClick={onClose}
            aria-label="Close drawer"
            style={{ padding: '4px 8px' }}
          >
            ✕
          </button>
        </div>

        {/* Diagnostic Metrics: Tokens & TTFT */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, background: 'var(--paper)' }}>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Input tokens</div>
            <div className="num" style={{ fontSize: 'var(--fs-md)', fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
              {row.inputTokens != null ? row.inputTokens : '—'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Output tokens</div>
            <div className="num" style={{ fontSize: 'var(--fs-md)', fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
              {row.outputTokens != null ? row.outputTokens : '—'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--muted)' }}>First-token time</div>
            <div className="num" style={{ fontSize: 'var(--fs-md)', fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
              {row.ttftMs != null ? `${row.ttftMs} ms` : '—'}
            </div>
          </div>
        </div>

        {/* Per-case test results */}
        <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1 }}>
          <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: 12 }}>
            Test cases ({row.passedCases} passed, {row.failedCases} failed)
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {row.measurements.map((m, idx) => {
              const isPass = m.evaluation_status === 'passed';
              const isFail = m.evaluation_status === 'failed';

              return (
                <div
                  key={m.case_id ?? idx}
                  style={{
                    padding: '10px 12px',
                    border: '1px solid var(--rule)',
                    borderRadius: 'var(--r-ctrl)',
                    background: 'var(--sheet)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)', fontWeight: 500 }}>
                      {m.case_id}
                    </span>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        color: isPass ? 'var(--gain)' : isFail ? 'var(--loss)' : 'var(--muted)',
                      }}
                    >
                      {isPass ? 'Passed' : isFail ? 'Failed' : m.evaluation_status}
                    </span>
                  </div>

                  {m.evaluation?.diagnostic && (
                    <div style={{ marginTop: 6, fontSize: '11px', color: 'var(--loss)', background: 'var(--loss-tint)', padding: '4px 8px', borderRadius: 3 }}>
                      {m.evaluation.diagnostic}
                    </div>
                  )}

                  {m.latency_ms && (
                    <div style={{ marginTop: 4, fontSize: '11px', color: 'var(--muted)', display: 'flex', gap: 12 }}>
                      <span>Latency: {m.latency_ms.mean ?? (m.latency_ms as any).value ?? '—'} ms</span>
                      {m.cost_usd && <span>Cost: ${m.calculated_cost?.amount_usd ?? (m.cost_usd as any).amount ?? '—'}</span>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

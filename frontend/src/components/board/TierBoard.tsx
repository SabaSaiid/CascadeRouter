/* oxlint-disable */
import { useMemo } from 'react';
import type { Backend_LLMNode as LLMNode, Job, Optimization } from '../../services/contracts.ts';
import {
  shortModelName,
  getModelPricing,
  orderColumns,
  getStationState,
  stationAriaLabel,
  hiddenRowSentence,
  savingPercentage,
  type StationState,
} from '../../services/display.ts';

export interface BoardCallItem {
  id: string;
  name: string;
  location: string;
  currentModel: string;
  // For illustration / static fixture overrides
  illustrationPick?: string | null;
  illustrationSavings?: string | null;
  illustrationStations?: Record<string, StationState>;
}

export interface TierBoardProps {
  calls?: readonly LLMNode[];
  illustrationCalls?: readonly BoardCallItem[];
  selectedId?: string;
  onSelectCall?: (id: string) => void;
  job?: Job;
  optimization?: Optimization;
  onBenchmarkCall?: (nodeId: string) => void;
  benchmarkingNodeId?: string;
  progressUnits?: { completed: number; total: number };
  isIllustration?: boolean;
  mandatoryLabel?: string;
}

const DEFAULT_TIERS = [
  'nvidia/Nano',
  'nvidia/Lightning',
  'nvidia/Flash',
  'nvidia/Ultra',
];

export function TierBoard({
  calls = [],
  illustrationCalls,
  selectedId,
  onSelectCall,
  job,
  optimization,
  onBenchmarkCall,
  benchmarkingNodeId,
  progressUnits,
  isIllustration = false,
  mandatoryLabel,
}: TierBoardProps) {
  // Determine model tiers to display as columns (baseline + candidates)
  const modelTiers = useMemo(() => {
    if (isIllustration) {
      return DEFAULT_TIERS;
    }
    const set = new Set<string>();
    // From job plan if available
    if (job?.plan.models) {
      for (const m of job.plan.models) set.add(m.identifier);
    }
    // From current calls
    for (const c of calls) {
      if (c.current_model) set.add(c.current_model);
    }
    // Standard tiers if fewer than 4
    if (set.size < 4) {
      set.add('meta-llama/Meta-Llama-3.1-8B-Instruct');
      set.add('nvidia/Llama-3.1-Nemotron-70B-Instruct');
      set.add('meta-llama/Meta-Llama-3.1-70B-Instruct');
      set.add('meta-llama/Meta-Llama-3.1-405B-Instruct');
    }
    return orderColumns(Array.from(set));
  }, [isIllustration, job?.plan.models, calls]);

  // Normalise call list
  const normalizedCalls: BoardCallItem[] = useMemo(() => {
    if (isIllustration && illustrationCalls) {
      return [...illustrationCalls];
    }
    return calls.map(n => {
      const fn = n.function_name;
      const file = n.file_path.split('/').pop() ?? n.file_path;
      const name = fn ?? `${file}, line ${n.line_number}`;
      const location = `${file}:${n.line_number}`;
      return {
        id: n.node_id,
        name,
        location,
        currentModel: n.current_model ?? 'meta-llama/Meta-Llama-3.1-70B-Instruct',
      };
    });
  }, [isIllustration, illustrationCalls, calls]);

  return (
    <section className="tier-board-container" aria-labelledby="tier-board-heading">
      {/* Board Header */}
      <div className="tier-board-header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <h2 id="tier-board-heading" className="tier-board-title">
            Where each call runs
          </h2>
          <span className="tier-board-subtitle">
            Cheaper tiers on the left. Ring: runs here today. Green dot: cheapest tier that passed every check.
          </span>
        </div>
        {mandatoryLabel && (
          <span className="tier-board-badge" data-testid="example-mandatory-label">
            {mandatoryLabel}
          </span>
        )}
      </div>

      {/* Live progress announcement for screen readers */}
      {progressUnits && (
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          Benchmarking in progress: {progressUnits.completed} of {progressUnits.total} units complete.
        </div>
      )}

      {/* Empty State */}
      {normalizedCalls.length === 0 ? (
        <div className="tier-board-empty">
          <p style={{ margin: 0, color: 'var(--muted)' }}>
            No calls discovered yet. Scan a repository to view LLM routing tiers.
          </p>
        </div>
      ) : (
        <div className="tier-board-table-wrapper" style={{ overflowX: 'auto' }}>
          <div className="tier-board-table" style={{ minWidth: 780 }}>
            {/* Column Headers */}
            <div className="tier-board-col-headers" style={{ display: 'flex', borderBottom: '1px solid var(--rule)' }}>
              <div className="tier-board-col-call-meta" style={{ width: 260, minWidth: 260, padding: '10px 16px', color: 'var(--muted)', fontSize: 'var(--fs-xs)' }}>
                Call &amp; location
              </div>
              <div className="tier-board-col-tiers" style={{ display: 'flex', flex: 1 }}>
                {modelTiers.map((modelId) => {
                  const pricing = getModelPricing(modelId);
                  return (
                    <div
                      key={modelId}
                      className="tier-board-col-header"
                      style={{
                        flex: 1,
                        padding: '10px 12px',
                        textAlign: 'center',
                        borderLeft: '1px solid var(--rule)',
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: 'var(--fs-sm)', color: 'var(--ink)' }}>
                        {shortModelName(modelId)}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                        {pricing.label}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Rows */}
            <div className="tier-board-rows">
              {normalizedCalls.map(call => {
                const isSelected = selectedId === call.id;
                const isBenchmarking = benchmarkingNodeId === call.id;

                // Check decision for this node
                const decision = optimization?.result.decisions.find(d => d.node_id === call.id);
                const hasJob = Boolean(job && job.plan.node_ids.includes(call.id));

                // Recommended model
                let recModelId: string | null = null;
                let savingPctStr: string | null = null;

                if (isIllustration) {
                  recModelId = call.illustrationPick ?? null;
                  savingPctStr = call.illustrationSavings ?? null;
                } else if (decision && decision.status === 'recommended') {
                  recModelId = decision.selected_model_id ?? null;
                  if (decision.baseline_model_id && recModelId && recModelId !== decision.baseline_model_id) {
                    const baseCand = decision.candidates.find(c => c.model.identifier === decision.baseline_model_id);
                    const selCand = decision.candidates.find(c => c.model.identifier === recModelId);
                    savingPctStr = savingPercentage(baseCand?.cost_total_usd, selCand?.cost_total_usd);
                  }
                } else if (decision && decision.status === 'baseline_retained') {
                  recModelId = decision.baseline_model_id;
                  savingPctStr = null;
                }

                const currentModelId = call.currentModel;
                const hiddenSentence = hiddenRowSentence({
                  callName: call.name,
                  currentModel: currentModelId,
                  recommendedModel: recModelId,
                  savingPct: savingPctStr,
                });

                // Station states
                const stationStates: Record<string, StationState> = {};
                for (const mId of modelTiers) {
                  if (isIllustration && call.illustrationStations) {
                    stationStates[mId] = call.illustrationStations[mId] ?? 'not_tested';
                  } else if (hasJob) {
                    const meas = job?.measurements.filter(m => m.node_id === call.id && m.model_id === mId) ?? [];
                    if (meas.length === 0) {
                      stationStates[mId] = 'not_tested';
                    } else {
                      const anyFailed = meas.some(m => m.evaluation_status === 'failed');
                      const allPassed = meas.every(m => m.evaluation_status === 'passed') && meas.length > 0;
                      const unavail = meas.some(m => m.evaluation_status === 'unavailable');
                      stationStates[mId] = getStationState({
                        tested: true,
                        passedAll: allPassed,
                        failed: anyFailed,
                        unavailable: unavail,
                      });
                    }
                  } else {
                    stationStates[mId] = 'not_tested';
                  }
                }

                // Indices for Now & Pick
                const nowIdx = modelTiers.findIndex(m => shortModelName(m) === shortModelName(currentModelId));
                const pickIdx = recModelId ? modelTiers.findIndex(m => shortModelName(m) === shortModelName(recModelId)) : -1;
                const hasCheaperPick = pickIdx !== -1 && pickIdx < nowIdx;

                return (
                  <div
                    key={call.id}
                    className={`tier-board-row${isSelected ? ' selected' : ''}`}
                    onClick={() => onSelectCall?.(call.id)}
                    tabIndex={0}
                    role="button"
                    aria-label={`Call: ${call.name}. ${hiddenSentence}`}
                    onKeyDown={e => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        onSelectCall?.(call.id);
                      }
                    }}
                    style={{
                      display: 'flex',
                      height: 72,
                      minHeight: 72,
                      alignItems: 'center',
                      borderBottom: '1px solid var(--rule)',
                      background: isSelected ? 'color-mix(in srgb, var(--navy) 4%, var(--sheet))' : 'var(--sheet)',
                      borderLeft: isSelected ? '3px solid var(--navy)' : '3px solid transparent',
                      cursor: 'pointer',
                      transition: 'background 0.15s ease',
                    }}
                  >
                    {/* Screen reader only sentence */}
                    <span className="sr-only">{hiddenSentence}</span>

                    {/* Left Cell: Call name + Location */}
                    <div
                      className="tier-board-cell-meta"
                      style={{
                        width: isSelected ? 257 : 260,
                        minWidth: isSelected ? 257 : 260,
                        padding: '0 16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        gap: 3,
                      }}
                    >
                      <span
                        className="tier-board-call-name"
                        style={{
                          fontSize: 'var(--fs-sm)',
                          fontWeight: 600,
                          color: 'var(--ink)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {call.name}
                      </span>
                      <span
                        className="tier-board-call-loc"
                        style={{
                          fontSize: '11px',
                          color: 'var(--muted)',
                          fontFamily: 'var(--font-mono)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {call.location}
                      </span>
                    </div>

                    {/* Right Cell: Track & Stations */}
                    <div
                      className="tier-board-cell-track"
                      style={{
                        flex: 1,
                        height: '100%',
                        position: 'relative',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      {/* Untested Notice & Benchmark Button */}
                      {!isIllustration && !hasJob && !isBenchmarking && (
                        <div
                          style={{
                            position: 'absolute',
                            right: 16,
                            top: 8,
                            zIndex: 4,
                          }}
                        >
                          <button
                            type="button"
                            className="btn-link"
                            onClick={(e) => {
                              e.stopPropagation();
                              onBenchmarkCall?.(call.id);
                            }}
                            style={{
                              fontSize: 'var(--fs-xs)',
                              padding: '2px 8px',
                              background: 'var(--sheet)',
                              border: '1px solid var(--rule)',
                              borderRadius: 'var(--r-chip)',
                            }}
                          >
                            Benchmark this call
                          </button>
                        </div>
                      )}

                      {/* In-flight Benchmarking Indicator */}
                      {isBenchmarking && (
                        <div
                          style={{
                            position: 'absolute',
                            right: 16,
                            top: 8,
                            fontSize: 'var(--fs-xs)',
                            color: 'var(--navy)',
                            fontWeight: 500,
                            zIndex: 4,
                          }}
                        >
                          Benchmarking…
                        </div>
                      )}

                      {/* SVG Track, Arc, and Connecting Line */}
                      <svg
                        style={{
                          position: 'absolute',
                          left: 0,
                          top: 0,
                          width: '100%',
                          height: '100%',
                          pointerEvents: 'none',
                        }}
                        preserveAspectRatio="none"
                      >
                        {/* 2px Track Line through stations */}
                        <line
                          x1="12.5%"
                          y1="34"
                          x2="87.5%"
                          y2="34"
                          stroke="var(--rule)"
                          strokeWidth="2"
                        />

                        {/* Dashed green arc if cheaper pick exists */}
                        {hasCheaperPick && (
                          <TrackArc
                            startCol={nowIdx}
                            endCol={pickIdx}
                            totalCols={modelTiers.length}
                            savingText={savingPctStr ? `${savingPctStr} less` : undefined}
                          />
                        )}
                      </svg>

                      {/* Stations Container */}
                      <div
                        style={{
                          display: 'flex',
                          width: '100%',
                          height: '100%',
                          alignItems: 'center',
                          position: 'relative',
                          zIndex: 2,
                        }}
                      >
                        {modelTiers.map((mId, colIdx) => {
                          const state = stationStates[mId] ?? 'not_tested';
                          const isNow = colIdx === nowIdx;
                          const isPick = colIdx === pickIdx;
                          const ariaLabel = stationAriaLabel(mId, state);

                          return (
                            <div
                              key={mId}
                              style={{
                                flex: 1,
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                height: '100%',
                                position: 'relative',
                              }}
                            >
                              {/* Station Dot */}
                              <div
                                role="img"
                                aria-label={ariaLabel}
                                className={`tier-station ${state}${isNow ? ' is-now' : ''}${isPick ? ' is-pick' : ''}`}
                                style={{
                                  position: 'relative',
                                  width: isPick ? 20 : 16,
                                  height: isPick ? 20 : 16,
                                  borderRadius: '50%',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  background: state === 'passed' ? 'var(--gain)' : '#FFFFFF',
                                  border: state === 'passed' ? '2px solid var(--gain)'
                                    : state === 'failed' ? '2px solid var(--loss)'
                                    : '2px solid var(--rule)',
                                  boxShadow: isNow ? '0 0 0 3px #FFFFFF, 0 0 0 5px var(--navy)' : undefined,
                                  transition: 'all 0.15s ease',
                                }}
                              >
                                {state === 'failed' && (
                                  <span
                                    aria-hidden="true"
                                    style={{
                                      color: 'var(--loss)',
                                      fontSize: '11px',
                                      fontWeight: 'bold',
                                      lineHeight: 1,
                                    }}
                                  >
                                    ×
                                  </span>
                                )}
                              </div>

                              {/* Station Label beneath ("Now" or "Pick") */}
                              <div style={{ height: 16, marginTop: 4, display: 'flex', alignItems: 'center' }}>
                                {isNow && (
                                  <span
                                    style={{
                                      fontSize: '11px',
                                      fontWeight: 600,
                                      color: 'var(--navy)',
                                      letterSpacing: '0.02em',
                                    }}
                                  >
                                    Now
                                  </span>
                                )}
                                {!isNow && isPick && (
                                  <span
                                    style={{
                                      fontSize: '11px',
                                      fontWeight: 600,
                                      color: 'var(--gain)',
                                      letterSpacing: '0.02em',
                                    }}
                                  >
                                    Pick
                                  </span>
                                )}
                                {state === 'unavailable' && !isNow && !isPick && (
                                  <span style={{ fontSize: '10px', color: 'var(--muted)' }}>
                                    n/a
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* "No cheaper tier passed every check" text on track if applicable */}
                      {!hasCheaperPick && (hasJob || isIllustration) && (
                        <div
                          className="no-cheaper-msg"
                          style={{
                            position: 'absolute',
                            left: 0,
                            right: 0,
                            top: 8,
                            textAlign: 'center',
                            fontSize: '11px',
                            color: 'var(--muted)',
                            pointerEvents: 'none',
                            zIndex: 3,
                          }}
                        >
                          No cheaper tier passed every check
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Cubic Bezier Track Arc
// ---------------------------------------------------------------------------

function TrackArc({
  startCol,
  endCol,
  totalCols,
  savingText,
}: {
  startCol: number;
  endCol: number;
  totalCols: number;
  savingText?: string;
}) {
  // Compute percentage centers of start and end columns
  const startPct = ((startCol + 0.5) / totalCols) * 100;
  const endPct = ((endCol + 0.5) / totalCols) * 100;

  const yBase = 24;
  const peakY = 8;
  const midPct = (startPct + endPct) / 2;

  // Cubic curve path: start at startPct (Now), arch up to peak, land at endPct (Pick)
  // Control point 1 is between start and mid; control point 2 between mid and end.
  const pathD = `M ${startPct}% ${yBase} C ${startPct - (startPct - endPct) * 0.25}% ${peakY}, ${endPct + (startPct - endPct) * 0.25}% ${peakY}, ${endPct}% ${yBase}`;

  return (
    <g className="route-arc">
      <path
        d={pathD}
        fill="none"
        stroke="var(--gain)"
        strokeWidth="2"
        strokeDasharray="4 3"
      />
      {savingText && (
        <g>
          <rect
            x={`calc(${midPct}% - 28px)`}
            y={2}
            width="56"
            height="15"
            rx="3"
            fill="var(--gain-tint)"
            stroke="var(--gain)"
            strokeWidth="1"
          />
          <text
            x={`${midPct}%`}
            y={13}
            textAnchor="middle"
            fill="var(--gain)"
            fontSize="10"
            fontWeight="600"
            fontFamily="var(--font-sans)"
          >
            {savingText}
          </text>
        </g>
      )}
    </g>
  );
}

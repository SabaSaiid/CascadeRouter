import type { FC } from 'react';
import { Cpu, Check } from 'lucide-react';
import type { DataSourceMode } from '../../types';
import { DataSourceBadge } from './DataSourceBadge';
import { fmtCost } from '../../utils/metrics';

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
  totalSpendUsd?: number;
}

type StepState = 'pending' | 'current' | 'done';

interface Step {
  label: string;
  state: StepState;
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
  totalSpendUsd,
}) => {
  // Derive progress trail state
  const steps: Step[] = [
    {
      label: 'Scanned',
      state: hasScanResults ? 'done' : isScanning ? 'current' : 'pending',
    },
    {
      label: 'Benchmarked',
      state: hasBenchmarkResults
        ? 'done'
        : isBenchmarking
        ? 'current'
        : hasScanResults
        ? 'pending'
        : 'pending',
    },
    {
      label: 'Patch tested',
      state: isOptimizing ? 'current' : hasBenchmarkResults ? 'pending' : 'pending',
    },
  ];

  // Determine the single primary action
  const nextAction = (() => {
    if (!hasScanResults) return { label: isScanning ? 'Scanning…' : 'Scan repository', handler: onScan, disabled: isScanning };
    if (!hasBenchmarkResults) return { label: isBenchmarking ? 'Benchmarking…' : 'Run benchmark', handler: onBenchmark, disabled: isBenchmarking };
    return { label: isOptimizing ? 'Generating…' : 'Generate patch', handler: onOptimize, disabled: isOptimizing };
  })();

  const spendCap = 10.0;
  const spendPct = totalSpendUsd != null ? Math.min(100, (totalSpendUsd / spendCap) * 100) : 0;

  return (
    <>
      <header
        style={{ height: 'var(--cr-header-h)' }}
        className="shrink-0 cr-border-b bg-[var(--cr-panel)] px-4 flex items-center gap-4 z-20"
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div
            className="w-7 h-7 rounded-[var(--cr-r-control)] bg-[var(--cr-raised)] cr-border flex items-center justify-center"
            aria-hidden="true"
          >
            <Cpu className="w-4 h-4 text-[var(--cr-accent)]" />
          </div>
          <h1 className="text-sm font-semibold text-[var(--cr-text)] whitespace-nowrap">
            CascadeRouter
          </h1>
          <span className="chip chip-accent mono text-[11px]">IDE</span>
        </div>

        {/* Divider */}
        <div className="w-px h-5 bg-[var(--cr-line)] shrink-0" aria-hidden="true" />

        {/* Progress trail */}
        <nav aria-label="Workflow progress" className="hidden md:flex items-center gap-0 shrink-0">
          {steps.map((step, i) => (
            <span key={step.label} className="flex items-center gap-0">
              <span
                className={`trail-step ${step.state}`}
                aria-current={step.state === 'current' ? 'step' : undefined}
              >
                <span className="trail-dot" aria-hidden="true" />
                {step.state === 'done' && (
                  <Check className="w-3 h-3 text-[var(--cr-pass)]" aria-hidden="true" />
                )}
                <span>{step.label}</span>
              </span>
              {i < steps.length - 1 && (
                <span className="trail-connector mx-2" aria-hidden="true" />
              )}
            </span>
          ))}
        </nav>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Spend indicator */}
        {totalSpendUsd != null && (
          <div className="hidden lg:block shrink-0 text-right">
            <div className="text-xs text-[var(--cr-subtle)] whitespace-nowrap">
              Spend{' '}
              <span className="num text-[var(--cr-muted)]">{fmtCost(totalSpendUsd, 4)}</span>
              {' '}of{' '}
              <span className="num text-[var(--cr-muted)]">$10.00</span> cap
            </div>
            <div className="spend-bar-track w-28">
              <div className="spend-bar-fill" style={{ width: `${spendPct}%` }} />
            </div>
          </div>
        )}

        {/* Data source badge */}
        <DataSourceBadge mode={dataSourceMode} onModeChange={onModeChange} />

        {/* Single primary CTA */}
        <button
          id="btn-next-action"
          type="button"
          onClick={nextAction.handler}
          disabled={nextAction.disabled}
          className="btn-primary shrink-0"
        >
          {nextAction.label}
        </button>
      </header>

      {/* Mock data warning strip */}
      {dataSourceMode === 'mock' && (
        <div className="mock-banner" role="status" aria-live="polite">
          <span>⚠</span>
          <span>Mock data — not real model results</span>
        </div>
      )}
    </>
  );
};

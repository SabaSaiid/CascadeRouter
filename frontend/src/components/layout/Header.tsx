import { useState } from 'react';
import type { Health, Scan, Job, Optimization } from '../../services/contracts.ts';
import type { ApiFailure } from '../../services/transport.ts';
import { dataSourceLabel, type WorkflowStep } from '../../services/display.ts';

type TrailStepDef = {
  key: string;
  label: string;
  state: 'done' | 'current' | 'pending';
};

function ProgressTrail({
  analysis,
  job,
  optimization,
}: {
  analysis?: Scan;
  job?: Job;
  optimization?: Optimization;
}) {
  const scanDone = Boolean(analysis);
  const benchmarkDone = Boolean(job && job.status === 'complete');
  const recommendDone = Boolean(optimization);
  const patchDone = false;

  const currentStep = !scanDone ? 'scan' : !benchmarkDone ? 'benchmark' : !recommendDone ? 'recommend' : 'patch';

  const steps: TrailStepDef[] = [
    { key: 'scan',      label: 'Scan',      state: scanDone ? 'done' : currentStep === 'scan' ? 'current' : 'pending' },
    { key: 'benchmark', label: 'Benchmark', state: benchmarkDone ? 'done' : currentStep === 'benchmark' ? 'current' : 'pending' },
    { key: 'recommend', label: 'Recommend', state: recommendDone ? 'done' : currentStep === 'recommend' ? 'current' : 'pending' },
    { key: 'patch',     label: 'Patch',     state: patchDone ? 'done' : currentStep === 'patch' ? 'current' : 'pending' },
  ];

  return (
    <nav className="progress-trail" aria-label="Workflow progress">
      {steps.map((s, i) => (
        <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center' }}>
          <span
            className={`trail-step ${s.state}`}
            aria-current={s.state === 'current' ? 'step' : undefined}
          >
            <span
              className={`trail-dot ${s.state}`}
              aria-hidden="true"
            />
            <span className="sr-only">
              {s.state === 'done' ? 'Done: ' : s.state === 'current' ? 'Current: ' : 'Pending: '}
            </span>
            <span style={{ fontSize: 'var(--fs-xs)' }}>{s.label}</span>
          </span>
          {i < steps.length - 1 && (
            <span className="trail-connector" aria-hidden="true" />
          )}
        </span>
      ))}
    </nav>
  );
}

export function Header({
  demo,
  health,
  healthError,
  healthLoading,
  analysis,
  job,
  optimization,
  onCheckHealth,
  onOpenDemo,
  onGoHome,
  step: _step,
  onRetrieveAnalysis,
  onRetrieveRun,
  onRetrievePatch,
  onRetrieveValidation,
}: {
  demo: boolean;
  health?: Health;
  healthError?: ApiFailure;
  healthLoading: boolean;
  analysis?: Scan;
  job?: Job;
  optimization?: Optimization;
  onCheckHealth: () => void;
  onOpenDemo: () => void;
  onGoHome?: () => void;
  step?: WorkflowStep;
  onRetrieveAnalysis?: (id: string) => void;
  onRetrieveRun?: (id: string) => void;
  onRetrievePatch?: (id: string) => void;
  onRetrieveValidation?: (id: string) => void;
}) {
  const [popoverOpen, setPopoverOpen] = useState(false);

  const hasData = Boolean(demo || analysis || (job && job.status === 'complete'));
  const dataSource = demo ? 'mock' : analysis?.data_source;
  const dsLabel = dataSourceLabel(dataSource, health?.benchmark_provenance, analysis?.timestamp);

  const dsKindStyle: Record<string, React.CSSProperties> = {
    mock:     { background: 'var(--caution-tint)', color: 'var(--caution)', borderColor: 'color-mix(in srgb, var(--caution) 30%, transparent)' },
    emulated: { background: 'var(--caution-tint)', color: 'var(--caution)', borderColor: 'color-mix(in srgb, var(--caution) 30%, transparent)' },
    recorded: { background: 'var(--chip-bg)',       color: 'var(--muted)',   borderColor: 'var(--rule)' },
    live:     { background: 'var(--gain-tint)',     color: 'var(--gain)',   borderColor: 'color-mix(in srgb, var(--gain) 30%, transparent)' },
  };

  return (
    <>
      <header className="app-header">
        {/* Wordmark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexShrink: 0 }}>
          {onGoHome ? (
            <button
              type="button"
              className="wordmark-btn"
              onClick={onGoHome}
              title="Return to home screen"
              aria-label="CascadeRouter Home"
            >
              <span className="wordmark">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--navy)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polyline points="7 4 12 9 7 14" />
                  <polyline points="13 10 18 15 13 20" />
                  <circle cx="5" cy="19" r="1.5" fill="var(--gain)" stroke="var(--gain)" />
                </svg>
                CascadeRouter
              </span>
            </button>
          ) : (
            <span className="wordmark">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--navy)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="7 4 12 9 7 14" />
                <polyline points="13 10 18 15 13 20" />
                <circle cx="5" cy="19" r="1.5" fill="var(--gain)" stroke="var(--gain)" />
              </svg>
              CascadeRouter
            </span>
          )}

          {/* Progress trail */}
          <ProgressTrail analysis={analysis} job={job} optimization={optimization} />
        </div>

        {/* Right side controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0, flexWrap: 'wrap' }}>
          {/* Data-source chip: appears only once a scan or run exists (or in mock mode) */}
          {hasData && dataSource && (
            <span
              className="chip"
              style={{ ...(dsKindStyle[dsLabel.kind] ?? dsKindStyle.live), fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)' }}
            >
              {dsLabel.text}
            </span>
          )}

          {/* Backend status grouped as one unit */}
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
            {health ? (
              <>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--gain)', flexShrink: 0 }} aria-hidden="true" />
                <span style={{ color: 'var(--ink)', fontWeight: 500 }}>Backend connected</span>
              </>
            ) : healthError ? (
              <>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--loss)', flexShrink: 0 }} aria-hidden="true" />
                <span style={{ color: 'var(--loss)' }}>{healthError.kind === 'unavailable' ? 'Backend unavailable' : 'Connection failed'}</span>
                {!demo && (
                  <button
                    type="button"
                    className="btn-link"
                    disabled={healthLoading}
                    onClick={onCheckHealth}
                    style={{ padding: '0 4px' }}
                  >
                    {healthLoading ? 'Checking…' : 'Retry'}
                  </button>
                )}
              </>
            ) : (
              <>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--field-border)', flexShrink: 0 }} aria-hidden="true" />
                <span>Backend not checked</span>
                {!demo && (
                  <button
                    type="button"
                    className="btn-link"
                    disabled={healthLoading || demo}
                    onClick={onCheckHealth}
                    style={{ padding: '0 4px' }}
                  >
                    {healthLoading ? 'Checking…' : 'Check'}
                  </button>
                )}
              </>
            )}
          </div>

          {/* Use sample data toggle */}
          <button
            type="button"
            className="btn-outline"
            onClick={onOpenDemo}
            title="Loads built-in mock data. Nothing is sent to a model."
            style={{ fontSize: 'var(--fs-xs)', height: 32 }}
          >
            {demo ? 'Exit sample data' : 'Use sample data'}
          </button>

          {/* Open earlier result secondary button */}
          <button
            type="button"
            className="btn-outline"
            onClick={() => setPopoverOpen(true)}
            style={{ fontSize: 'var(--fs-xs)', height: 32 }}
          >
            Open earlier result
          </button>
        </div>
      </header>

      {/* Earlier-result popover */}
      {popoverOpen && (
        <EarlierResultPopover
          onClose={() => setPopoverOpen(false)}
          onRetrieveAnalysis={id => { onRetrieveAnalysis?.(id); setPopoverOpen(false); }}
          onRetrieveRun={id => { onRetrieveRun?.(id); setPopoverOpen(false); }}
          onRetrievePatch={id => { onRetrievePatch?.(id); setPopoverOpen(false); }}
          onRetrieveValidation={id => { onRetrieveValidation?.(id); setPopoverOpen(false); }}
        />
      )}
    </>
  );
}

/** Popover containing the four ID retrieve fields — removed from the main flow. */
function EarlierResultPopover({
  onClose,
  onRetrieveAnalysis,
  onRetrieveRun,
  onRetrievePatch,
  onRetrieveValidation,
}: {
  onClose: () => void;
  onRetrieveAnalysis?: (id: string) => void;
  onRetrieveRun?: (id: string) => void;
  onRetrievePatch?: (id: string) => void;
  onRetrieveValidation?: (id: string) => void;
}) {
  return (
    <div
      className="popover-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Open earlier result"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="popover-panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 'var(--fs-base)', fontWeight: 600 }}>Open earlier result</h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close popover" style={{ padding: '4px 8px' }}>✕</button>
        </div>
        <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginBottom: 16 }}>
          Paste any stored ID to retrieve a previous result. Fields are independent.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <IdField label="Analysis ID" pattern="analysis_[0-9a-f]{32}" placeholder="analysis_…" onRetrieve={onRetrieveAnalysis} />
          <IdField label="Run ID" pattern="run_[0-9a-f]{32}" placeholder="run_…" onRetrieve={onRetrieveRun} />
          <IdField label="Patch ID" pattern="patch_[0-9a-f]{32}" placeholder="patch_…" onRetrieve={onRetrievePatch} />
          <IdField label="Validation ID" pattern="validation_[0-9a-f]{64}" placeholder="validation_…" onRetrieve={onRetrieveValidation} />
        </div>
        <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginTop: 12 }}>
          Retrieval connects to the configured local backend. No automatic operations.
        </p>
      </div>
    </div>
  );
}

function IdField({
  label,
  pattern,
  placeholder,
  onRetrieve,
}: {
  label: string;
  pattern: string;
  placeholder: string;
  onRetrieve?: (value: string) => void;
}) {
  const [value, setValue] = useState('');
  const valid = value === '' || new RegExp(`^${pattern}$`).test(value);
  const canRetrieve = value.trim() !== '' && valid;

  return (
    <div>
      <label className="field-label">
        {label}
        <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
          <input
            className={`field-input mono`}
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder={placeholder}
            pattern={pattern}
            autoComplete="off"
            spellCheck={false}
            style={{ borderColor: !valid && value ? 'var(--loss)' : undefined }}
          />
          <button
            type="button"
            className="btn-ghost"
            disabled={!canRetrieve}
            onClick={() => onRetrieve?.(value.trim())}
            style={{ flexShrink: 0, padding: '0 12px' }}
          >
            Retrieve
          </button>
        </div>
      </label>
      {!valid && value && (
        <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--loss)', marginTop: 4 }}>
          Format does not match expected ID pattern.
        </p>
      )}
    </div>
  );
}

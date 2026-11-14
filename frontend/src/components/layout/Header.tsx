import { useEffect, useRef, useState } from 'react';
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

export interface HeaderProps {
  demo: boolean;
  health?: Health;
  healthError?: ApiFailure;
  healthLoading: boolean;
  analysis?: Scan;
  job?: Job;
  optimization?: Optimization;
  onCheckHealth: () => void;
  onGoHome?: () => void;
  step?: WorkflowStep;
  onOpenSettings?: () => void;
  onOpenHowItWorks?: () => void;
  onOpenSecurityTerms?: () => void;
  onOpenEarlierResult?: () => void;
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
  onGoHome,
  onOpenSettings,
  onOpenHowItWorks,
  onOpenSecurityTerms,
  onOpenEarlierResult,
}: HeaderProps) {
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMoreMenuOpen(false);
      }
    };
    if (moreMenuOpen) {
      window.addEventListener('mousedown', handleOutsideClick);
    }
    return () => window.removeEventListener('mousedown', handleOutsideClick);
  }, [moreMenuOpen]);

  const hasData = Boolean(demo || analysis || (job && job.status === 'complete'));
  const dataSource = demo ? 'mock' : analysis?.data_source;
  const dsLabel = dataSourceLabel(dataSource, health?.benchmark_provenance, analysis?.timestamp);

  // In section 1 & 2:
  // "The 'Mock data' chip (the amber banner is enough)."
  // "Mention 'NVIDIA Nemotron on Nebius Token Factory' only when the data source is live."
  // So do NOT render chip when mock.
  const showDataChip = hasData && dataSource && dataSource !== 'mock';
  const chipText = dataSource === 'live'
    ? 'NVIDIA Nemotron on Nebius Token Factory'
    : dsLabel.text;

  return (
    <header className="app-header" style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', borderBottom: '1px solid var(--rule)', background: 'var(--sheet)', zIndex: 10 }}>
      {/* Wordmark and Progress Trail */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexShrink: 0 }}>
        {onGoHome ? (
          <button
            type="button"
            className="wordmark-btn"
            onClick={onGoHome}
            title="Return to home screen"
            aria-label="CascadeRouter Home"
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
          >
            <span className="wordmark" style={{ fontFamily: 'var(--font-serif)', fontSize: '20px', fontWeight: 600, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--navy)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="7 4 12 9 7 14" />
                <polyline points="13 10 18 15 13 20" />
                <circle cx="5" cy="19" r="1.5" fill="var(--gain)" stroke="var(--gain)" />
              </svg>
              CascadeRouter
            </span>
          </button>
        ) : (
          <span className="wordmark" style={{ fontFamily: 'var(--font-serif)', fontSize: '20px', fontWeight: 600, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 8 }}>
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

      {/* Right Controls: Data-source chip, Backend status, ONE More button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
        {/* Data-source chip: appears only once data exists and not in mock mode */}
        {showDataChip && (
          <span
            className="chip"
            style={{
              background: dataSource === 'live' ? 'var(--gain-tint)' : 'var(--chip-bg)',
              color: dataSource === 'live' ? 'var(--gain)' : 'var(--muted)',
              border: `1px solid ${dataSource === 'live' ? 'color-mix(in srgb, var(--gain) 30%, transparent)' : 'var(--rule)'}`,
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--fs-xs)',
              padding: '2px 8px',
              borderRadius: 'var(--r-chip)',
            }}
          >
            {chipText}
          </span>
        )}

        {/* Backend status grouped as one unit with "Check" */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
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

        {/* ONE "More" button with dropdown */}
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button
            type="button"
            className="btn-outline"
            onClick={() => setMoreMenuOpen(!moreMenuOpen)}
            aria-expanded={moreMenuOpen}
            aria-haspopup="true"
            style={{ fontSize: 'var(--fs-xs)', height: 32, padding: '0 12px' }}
          >
            More
          </button>

          {moreMenuOpen && (
            <div
              className="more-dropdown-menu"
              role="menu"
              style={{
                position: 'absolute',
                right: 0,
                top: 'calc(100% + 6px)',
                width: 190,
                background: 'var(--sheet)',
                border: '1px solid var(--rule)',
                borderRadius: 'var(--r-ctrl)',
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                zIndex: 100,
                display: 'flex',
                flexDirection: 'column',
                padding: '4px 0',
              }}
            >
              <button
                type="button"
                className="dropdown-menu-item"
                role="menuitem"
                onClick={() => {
                  setMoreMenuOpen(false);
                  onOpenEarlierResult?.();
                }}
                style={{
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                  padding: '8px 16px',
                  fontSize: 'var(--fs-xs)',
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  width: '100%',
                }}
              >
                Open earlier result
              </button>
              <button
                type="button"
                className="dropdown-menu-item"
                role="menuitem"
                onClick={() => {
                  setMoreMenuOpen(false);
                  onOpenSettings?.();
                }}
                style={{
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                  padding: '8px 16px',
                  fontSize: 'var(--fs-xs)',
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  width: '100%',
                }}
              >
                Settings
              </button>
              <button
                type="button"
                className="dropdown-menu-item"
                role="menuitem"
                onClick={() => {
                  setMoreMenuOpen(false);
                  onOpenHowItWorks?.();
                }}
                style={{
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                  padding: '8px 16px',
                  fontSize: 'var(--fs-xs)',
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  width: '100%',
                }}
              >
                How it works
              </button>
              <button
                type="button"
                className="dropdown-menu-item"
                role="menuitem"
                onClick={() => {
                  setMoreMenuOpen(false);
                  onOpenSecurityTerms?.();
                }}
                style={{
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                  padding: '8px 16px',
                  fontSize: 'var(--fs-xs)',
                  color: 'var(--ink)',
                  cursor: 'pointer',
                  width: '100%',
                }}
              >
                Security and terms
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

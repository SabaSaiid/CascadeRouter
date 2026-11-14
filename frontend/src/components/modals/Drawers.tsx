/* oxlint-disable */
import { useEffect, useState } from 'react';

// ---------------------------------------------------------------------------
// Settings Drawer
// ---------------------------------------------------------------------------

export interface SettingsDrawerProps {
  onClose: () => void;
  strictAllChecks: boolean;
  onStrictAllChecksChange: (enabled: boolean) => void;
}

export function SettingsDrawer({
  onClose,
  strictAllChecks,
  onStrictAllChecksChange,
}: SettingsDrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-drawer-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="drawer-panel" style={{ width: 400, maxWidth: '90vw' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 id="settings-drawer-title" style={{ margin: 0, fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)' }}>
            Settings
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close settings drawer" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={strictAllChecks}
              onChange={e => onStrictAllChecksChange(e.target.checked)}
              style={{ marginTop: 3, width: 16, height: 16, accentColor: 'var(--navy)' }}
            />
            <div>
              <div style={{ fontWeight: 500, color: 'var(--ink)', fontSize: 'var(--fs-sm)' }}>
                Only recommend a model if it passes every check
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', marginTop: 4, lineHeight: 1.4 }}>
                When enabled, candidate models are considered for routing only if they achieve a 100% test pass rate across all evaluated test cases.
              </div>
            </div>
          </label>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// How It Works Drawer
// ---------------------------------------------------------------------------

export interface HowItWorksDrawerProps {
  onClose: () => void;
}

export function HowItWorksDrawer({ onClose }: HowItWorksDrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="how-it-works-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="drawer-panel" style={{ width: 480, maxWidth: '90vw' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 id="how-it-works-title" style={{ margin: 0, fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)' }}>
            How it works
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close drawer" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 20, overflowY: 'auto' }}>
          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              1. Scan
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Finds every LLM call in your code without running it. CascadeRouter parses Python files statically using Abstract Syntax Tree (AST) inspection to detect model IDs, parameters, and variable dependencies.
            </p>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              2. Benchmark
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Runs your test cases on each candidate model and records cost, speed, time-to-first-token, and pass/fail status. Measurements are recorded with cryptographic digests for full provenance.
            </p>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              3. Recommend
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Picks the cheapest model that passes every quality check. If no cheaper model passes all assertions, the call stays on its current baseline model.
            </p>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              4. Patch
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Shows the one-line change via unified diff. Only the model string literal changes. A timestamped .bak backup file is saved automatically before anything is written to disk.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Security & Terms Drawer
// ---------------------------------------------------------------------------

export interface SecurityTermsDrawerProps {
  onClose: () => void;
}

export function SecurityTermsDrawer({ onClose }: SecurityTermsDrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="security-terms-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="drawer-panel" style={{ width: 480, maxWidth: '90vw' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 id="security-terms-title" style={{ margin: 0, fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)' }}>
            Security and terms
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close drawer" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 18, overflowY: 'auto' }}>
          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Zero code execution guarantee
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              CascadeRouter parses repository files statically. Repository code is never imported, evaluated, or executed locally or remotely.
            </p>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Data sovereignty
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Your source code stays on your machine. Only test case prompt assertions configured for benchmarking are transmitted to the inference provider.
            </p>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Non-destructive atomic patching
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Edits replace only the model string literal. A .bak backup is always written before modifying any target file.
            </p>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              License
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-xs)', lineHeight: 1.5 }}>
              Released under the MIT License.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Open Earlier Result Popover / Drawer
// ---------------------------------------------------------------------------

export interface RecentSessionsDrawerProps {
  onClose: () => void;
  onRetrieveAnalysis?: (id: string) => void;
  onRetrieveRun?: (id: string) => void;
}

export function RecentSessionsDrawer({
  onClose,
  onRetrieveAnalysis,
  onRetrieveRun,
}: RecentSessionsDrawerProps) {
  const [sessions, setSessions] = useState<{ id: string; type: 'analysis' | 'run'; label: string; date: string }[]>([]);

  useEffect(() => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const raw = window.localStorage.getItem('cascaderouter_recent_sessions');
        if (raw) setSessions(JSON.parse(raw));
      }
    } catch {
      // ignore
    }
  }, []);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="recent-sessions-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="drawer-panel" style={{ width: 400, maxWidth: '90vw' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 id="recent-sessions-title" style={{ margin: 0, fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)' }}>
            Open earlier result
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close drawer" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <div style={{ padding: '16px 20px', overflowY: 'auto' }}>
          {sessions.length === 0 ? (
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 'var(--fs-sm)' }}>
              No recent sessions found on this workstation.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {sessions.map(s => (
                <button
                  key={s.id}
                  type="button"
                  className="btn-outline"
                  onClick={() => {
                    if (s.type === 'analysis') onRetrieveAnalysis?.(s.id);
                    else onRetrieveRun?.(s.id);
                    onClose();
                  }}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    textAlign: 'left',
                    padding: '8px 12px',
                    height: 'auto',
                  }}
                >
                  <div style={{ fontWeight: 500, fontSize: 'var(--fs-xs)', color: 'var(--ink)' }}>
                    {s.label}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                    {s.id} • {s.date}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { type ThemeMode } from '../../services/theme.ts';

export interface SettingsModalProps {
  onClose: () => void;
  currentTheme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
  isLiveNebius?: boolean;
}

export function SettingsModal({
  onClose,
  currentTheme,
  onThemeChange,
  isLiveNebius = false,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<'general' | 'inference' | 'safety'>('general');
  const [apiKey, setApiKey] = useState(() => {
    try {
      return localStorage.getItem('cascaderouter_nebius_api_key') || '';
    } catch {
      return '';
    }
  });
  const [showKey, setShowKey] = useState(false);
  const [autoBackup, setAutoBackup] = useState(true);
  const [strictPass, setStrictPass] = useState(true);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleSave = () => {
    try {
      if (apiKey.trim()) {
        localStorage.setItem('cascaderouter_nebius_api_key', apiKey.trim());
      } else {
        localStorage.removeItem('cascaderouter_nebius_api_key');
      }
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 2000);
    } catch {
      // Ignore localStorage restrictions
    }
  };

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-dialog-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal-dialog">
        <div className="modal-header">
          <h2 id="settings-dialog-title" className="modal-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            Compiler Settings & Preferences
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close settings dialog" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <nav className="modal-tabs" aria-label="Settings categories">
          <button
            type="button"
            className={`modal-tab-btn${activeTab === 'general' ? ' active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            General & Theme
          </button>
          <button
            type="button"
            className={`modal-tab-btn${activeTab === 'inference' ? ' active' : ''}`}
            onClick={() => setActiveTab('inference')}
          >
            Nebius & Hardware
          </button>
          <button
            type="button"
            className={`modal-tab-btn${activeTab === 'safety' ? ' active' : ''}`}
            onClick={() => setActiveTab('safety')}
          >
            Safety & Backups
          </button>
        </nav>

        <div className="modal-body">
          {activeTab === 'general' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div>
                <span className="field-label" style={{ marginBottom: 8, display: 'block' }}>Interface Theme</span>
                <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)', margin: '0 0 10px' }}>
                  Choose your preferred appearance for the compiler workbench.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  <button
                    type="button"
                    className={`btn-outline${currentTheme === 'dark' ? ' active' : ''}`}
                    onClick={() => onThemeChange('dark')}
                    style={{
                      height: 48,
                      flexDirection: 'column',
                      justifyContent: 'center',
                      background: currentTheme === 'dark' ? 'var(--navy)' : 'transparent',
                      color: currentTheme === 'dark' ? '#fff' : 'var(--ink)',
                      borderColor: currentTheme === 'dark' ? 'var(--navy)' : 'var(--rule)',
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>Dark Theme</span>
                    <span style={{ fontSize: '11px', opacity: 0.8 }}>Pro Developer</span>
                  </button>
                  <button
                    type="button"
                    className={`btn-outline${currentTheme === 'light' ? ' active' : ''}`}
                    onClick={() => onThemeChange('light')}
                    style={{
                      height: 48,
                      flexDirection: 'column',
                      justifyContent: 'center',
                      background: currentTheme === 'light' ? 'var(--navy)' : 'transparent',
                      color: currentTheme === 'light' ? '#fff' : 'var(--ink)',
                      borderColor: currentTheme === 'light' ? 'var(--navy)' : 'var(--rule)',
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>Light Theme</span>
                    <span style={{ fontSize: '11px', opacity: 0.8 }}>High Clarity</span>
                  </button>
                  <button
                    type="button"
                    className={`btn-outline${currentTheme === 'system' ? ' active' : ''}`}
                    onClick={() => onThemeChange('system')}
                    style={{
                      height: 48,
                      flexDirection: 'column',
                      justifyContent: 'center',
                      background: currentTheme === 'system' ? 'var(--navy)' : 'transparent',
                      color: currentTheme === 'system' ? '#fff' : 'var(--ink)',
                      borderColor: currentTheme === 'system' ? 'var(--navy)' : 'var(--rule)',
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>System Default</span>
                    <span style={{ fontSize: '11px', opacity: 0.8 }}>OS Sync</span>
                  </button>
                </div>
              </div>

              <div style={{ borderTop: '1px solid var(--rule)', paddingTop: 16 }}>
                <span className="field-label" style={{ marginBottom: 8, display: 'block' }}>Compiler Strategy</span>
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={strictPass}
                    onChange={e => setStrictPass(e.target.checked)}
                    style={{ marginTop: 3 }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 'var(--fs-sm)' }}>Strict 100% Pass Rate Constraint</div>
                    <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
                      Only propose model replacement if candidate model passes every test assertion and schema check.
                    </div>
                  </div>
                </label>
              </div>
            </div>
          )}

          {activeTab === 'inference' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <label className="field-label" htmlFor="nebius-key-input">
                  Nebius Token Factory API Key (Optional)
                  <span style={{ fontWeight: 400, color: 'var(--muted)', fontSize: '11px' }}>
                    Connects empirical benchmarks directly to live Nebius Token Factory endpoints.
                  </span>
                </label>
                <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                  <input
                    id="nebius-key-input"
                    className="field-input mono"
                    type={showKey ? 'text' : 'password'}
                    placeholder="eyJhbGciOiJSUzI1NiIsInR5cCI6..."
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    className="btn-outline"
                    onClick={() => setShowKey(!showKey)}
                    style={{ flexShrink: 0 }}
                  >
                    {showKey ? 'Hide' : 'Show'}
                  </button>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                  <button type="button" className="btn-primary" onClick={handleSave} style={{ minWidth: 100, height: 32 }}>
                    Save Key
                  </button>
                  {savedSuccess && (
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--gain)', fontWeight: 600 }}>
                      ✓ Saved to browser storage!
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: 10, lineHeight: 1.4 }}>
                  💡 <strong>Pro Tip:</strong> To run live cloud benchmarks directly against Nebius Token Factory, launch the backend with <code className="mono" style={{ background: 'var(--paper)', padding: '2px 4px', borderRadius: 4 }}>export NEBIUS_API_KEY=&quot;...&quot; &amp;&amp; bash start.sh</code>. Without an API key, CascadeRouter automatically operates in calibrated high-fidelity emulation mode with zero cloud expenditure.
                </div>
              </div>

              <div style={{ background: 'var(--paper)', padding: 14, borderRadius: 'var(--r-sheet)', border: '1px solid var(--rule)' }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--fs-xs)', marginBottom: 6 }}>Hardware & Endpoints</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '12px', color: 'var(--muted)' }}>
                  <div><strong>Inference Provider:</strong> Nebius Token Factory (NVIDIA H100 SXM5)</div>
                  <div><strong>Remote Endpoint:</strong> <code>https://api.tokenfactory.nebius.com/v1</code></div>
                  <div><strong>Local Backend:</strong> <code>http://localhost:8000</code></div>
                  <div><strong>Status:</strong> {isLiveNebius ? <span style={{ color: 'var(--gain)', fontWeight: 600 }}>● Live Cloud Connected</span> : <span style={{ color: 'var(--gain)', fontWeight: 600 }}>● Ready (Live &amp; Calibrated Emulation Active)</span>}</div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'safety' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <span className="field-label" style={{ marginBottom: 8, display: 'block' }}>Codebase Safety Guarantees</span>
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', marginBottom: 12 }}>
                  <input
                    type="checkbox"
                    checked={autoBackup}
                    onChange={e => setAutoBackup(e.target.checked)}
                    style={{ marginTop: 3 }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 'var(--fs-sm)' }}>Create Automated Backup Files (.bak)</div>
                    <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
                      Before writing any patch to your Python codebase, save an exact copy with <code>.bak</code> suffix for 1-second instant rollback.
                    </div>
                  </div>
                </label>
              </div>

              <div style={{ padding: 12, background: 'color-mix(in srgb, var(--gain) 8%, var(--sheet))', borderRadius: 'var(--r-ctrl)', border: '1px solid color-mix(in srgb, var(--gain) 25%, transparent)' }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--fs-xs)', color: 'var(--gain)', marginBottom: 4 }}>
                  Zero-Execution Sandbox Guarantee
                </div>
                <p style={{ margin: 0, fontSize: '12px', color: 'var(--ink)' }}>
                  CascadeRouter inspects your code solely through static Abstract Syntax Tree (AST) analysis. It never imports, executes, or sandboxes untrusted code.
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-outline" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}


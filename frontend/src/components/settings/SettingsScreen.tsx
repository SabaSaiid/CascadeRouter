import { useState } from 'react';
import type { AppSettings } from '../../services/settings.ts';
import {
  isValidIdentifier,
  parseCandidateModelIds,
  deriveQualityThreshold,
} from '../../services/settings.ts';
import { APP_VERSION } from '../../version.ts';
import type { Health } from '../../services/contracts.ts';

export interface SettingsScreenProps {
  settings: AppSettings;
  onUpdateSettings: (newSettings: AppSettings) => void;
  health?: Health;
  backendBaseUrl?: string;
  onResetDefaults: () => void;
}

export function SettingsScreen({
  settings,
  onUpdateSettings,
  health,
  backendBaseUrl,
  onResetDefaults,
}: SettingsScreenProps) {
  const [candidatesError, setCandidatesError] = useState<string>();
  const [baselineError, setBaselineError] = useState<string>();
  const [caseSetError, setCaseSetError] = useState<string>();
  const [profileError, setProfileError] = useState<string>();

  // Determine availability of data source options
  const isLiveAvailable = Boolean(health && health.scan_available);
  const isRecordedAvailable = Boolean(health && health.benchmark_provenance === 'recorded');

  const handleStrictToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const strictAllChecks = e.target.checked;
    onUpdateSettings({
      ...settings,
      strictAllChecks,
    });
  };

  const handlePassRateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value, 10);
    const clamped = isNaN(val) ? 100 : Math.max(50, Math.min(100, val));
    onUpdateSettings({
      ...settings,
      passRateRequired: clamped,
    });
  };

  const handleBaselineChange = (val: string) => {
    if (!isValidIdentifier(val.trim())) {
      setBaselineError('Must match pattern: letters, numbers, _, ., /, -');
    } else {
      setBaselineError(undefined);
    }
    onUpdateSettings({
      ...settings,
      baselineModelId: val,
    });
  };

  const handleCandidatesChange = (val: string) => {
    const parsed = parseCandidateModelIds(val);
    if (parsed.error) {
      setCandidatesError(parsed.error);
    } else {
      setCandidatesError(undefined);
    }
    onUpdateSettings({
      ...settings,
      candidateModelIds: val,
    });
  };

  const handleCaseSetChange = (val: string) => {
    if (!isValidIdentifier(val.trim())) {
      setCaseSetError('Must match pattern: letters, numbers, _, ., /, -');
    } else {
      setCaseSetError(undefined);
    }
    onUpdateSettings({
      ...settings,
      caseSetId: val,
    });
  };

  const handleProfileChange = (val: string) => {
    if (!isValidIdentifier(val.trim())) {
      setProfileError('Must match pattern: letters, numbers, _, ., /, -');
    } else {
      setProfileError(undefined);
    }
    onUpdateSettings({
      ...settings,
      evaluationProfileId: val,
    });
  };

  const handleDataSourceChange = (source: 'live' | 'recorded' | 'sample') => {
    onUpdateSettings({
      ...settings,
      dataSource: source,
    });
  };

  const handleAppearanceChange = (appearance: 'light' | 'dark' | 'system') => {
    onUpdateSettings({
      ...settings,
      appearance,
    });
  };

  const currentThreshold = deriveQualityThreshold(
    settings.strictAllChecks,
    settings.passRateRequired
  );

  return (
    <div className="settings-container">
      <div className="settings-header">
        <h2 className="settings-title">Settings</h2>
        <p className="settings-subtitle">
          Configure compiler rules, benchmark presets, data sources and appearance.
        </p>
      </div>

      <div className="settings-form">
        {/* Group 1: Recommendation rules */}
        <section className="settings-group">
          <div className="settings-label-col">
            <h3 className="settings-group-title">Recommendation rules</h3>
            <p className="settings-group-desc">
              Controls the quality threshold passed to the compiler optimizer.
            </p>
          </div>

          <div className="settings-content-col">
            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                checked={settings.strictAllChecks}
                onChange={handleStrictToggle}
                aria-describedby="threshold-desc"
              />
              <span className="checkbox-label-text">
                Only recommend a model if it passes every check
              </span>
            </label>

            <div className="settings-field-indented">
              <label
                className={`settings-input-row${settings.strictAllChecks ? ' disabled' : ''}`}
              >
                <span className="input-label-text">Pass rate required</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="number"
                    min={50}
                    max={100}
                    step={1}
                    value={settings.passRateRequired}
                    onChange={handlePassRateChange}
                    disabled={settings.strictAllChecks}
                    className="input-number"
                    aria-label="Pass rate required percentage"
                  />
                  <span className="unit-label">%</span>
                </div>
              </label>

              <div id="threshold-desc" className="settings-note-subline">
                Contract quality threshold: <code>{currentThreshold}</code>
              </div>
            </div>
          </div>
        </section>

        <hr className="settings-divider" />

        {/* Group 2: Benchmark defaults */}
        <section className="settings-group">
          <div className="settings-label-col">
            <h3 className="settings-group-title">Benchmark defaults</h3>
            <p className="settings-group-desc">
              Pre-fills every call benchmark and &ldquo;Benchmark all&rdquo;.
            </p>
          </div>

          <div className="settings-content-col">
            <div className="settings-field">
              <label className="field-label" htmlFor="settings-baseline">
                Baseline model ID
              </label>
              <input
                id="settings-baseline"
                type="text"
                className="input-text"
                value={settings.baselineModelId}
                onChange={e => handleBaselineChange(e.target.value)}
              />
              {baselineError && <div className="field-error">{baselineError}</div>}
            </div>

            <div className="settings-field">
              <label className="field-label" htmlFor="settings-candidates">
                Candidate models (comma-separated, max 8)
              </label>
              <input
                id="settings-candidates"
                type="text"
                className="input-text"
                value={settings.candidateModelIds}
                onChange={e => handleCandidatesChange(e.target.value)}
              />
              {candidatesError && <div className="field-error">{candidatesError}</div>}
            </div>

            <div className="settings-field">
              <label className="field-label" htmlFor="settings-caseset">
                Case set ID
              </label>
              <input
                id="settings-caseset"
                type="text"
                className="input-text"
                value={settings.caseSetId}
                onChange={e => handleCaseSetChange(e.target.value)}
              />
              {caseSetError && <div className="field-error">{caseSetError}</div>}
            </div>

            <div className="settings-field">
              <label className="field-label" htmlFor="settings-profile">
                Evaluation profile ID
              </label>
              <input
                id="settings-profile"
                type="text"
                className="input-text"
                value={settings.evaluationProfileId}
                onChange={e => handleProfileChange(e.target.value)}
              />
              {profileError && <div className="field-error">{profileError}</div>}
            </div>
          </div>
        </section>

        <hr className="settings-divider" />

        {/* Group 3: Data source */}
        <section className="settings-group">
          <div className="settings-label-col">
            <h3 className="settings-group-title">Data source</h3>
            <p className="settings-group-desc">
              Choose live inference, recorded runs, or synthetic sample fixtures.
            </p>
          </div>

          <div className="settings-content-col">
            <div className="settings-radio-group">
              <label className={`settings-radio-option${!isLiveAvailable ? ' option-disabled' : ''}`}>
                <input
                  type="radio"
                  name="data_source"
                  value="live"
                  checked={settings.dataSource === 'live'}
                  onChange={() => handleDataSourceChange('live')}
                  disabled={!isLiveAvailable}
                />
                <div className="radio-text-wrap">
                  <span className="radio-main-label">Live</span>
                  <span className="radio-sub-label">
                    {isLiveAvailable
                      ? 'NVIDIA Nemotron via Nebius Token Factory loopback.'
                      : 'Unavailable: Local backend is not connected or inference credentials not configured.'}
                  </span>
                </div>
              </label>

              <label className={`settings-radio-option${!isRecordedAvailable ? ' option-disabled' : ''}`}>
                <input
                  type="radio"
                  name="data_source"
                  value="recorded"
                  checked={settings.dataSource === 'recorded'}
                  onChange={() => handleDataSourceChange('recorded')}
                  disabled={!isRecordedAvailable}
                />
                <div className="radio-text-wrap">
                  <span className="radio-main-label">Recorded</span>
                  <span className="radio-sub-label">
                    {isRecordedAvailable
                      ? 'Authenticated recorded benchmark dataset.'
                      : 'Unavailable: No recorded dataset found on local backend.'}
                  </span>
                </div>
              </label>

              <label className="settings-radio-option">
                <input
                  type="radio"
                  name="data_source"
                  value="sample"
                  checked={settings.dataSource === 'sample'}
                  onChange={() => handleDataSourceChange('sample')}
                />
                <div className="radio-text-wrap">
                  <span className="radio-main-label">Sample data</span>
                  <span className="radio-sub-label">
                    Synthetic test fixtures for customer support agent.
                  </span>
                </div>
              </label>
            </div>
          </div>
        </section>

        <hr className="settings-divider" />

        {/* Group 4: Appearance */}
        <section className="settings-group">
          <div className="settings-label-col">
            <h3 className="settings-group-title">Appearance</h3>
            <p className="settings-group-desc">
              Select your preferred color theme.
            </p>
          </div>

          <div className="settings-content-col">
            <div className="appearance-toggle-group">
              {(['light', 'dark', 'system'] as const).map(mode => (
                <button
                  key={mode}
                  type="button"
                  className={`btn-appearance${settings.appearance === mode ? ' active' : ''}`}
                  onClick={() => handleAppearanceChange(mode)}
                  aria-pressed={settings.appearance === mode}
                >
                  {mode === 'light' ? 'Light' : mode === 'dark' ? 'Dark' : 'System'}
                </button>
              ))}
            </div>
          </div>
        </section>

        <hr className="settings-divider" />

        {/* Group 5: About (read-only) */}
        <section className="settings-group">
          <div className="settings-label-col">
            <h3 className="settings-group-title">About</h3>
            <p className="settings-group-desc">
              Local environment and security guarantees.
            </p>
          </div>

          <div className="settings-content-col about-content">
            <div className="about-item">
              <span className="about-label">Backend address:</span>
              <code className="about-value">{backendBaseUrl || 'http://127.0.0.1:8000'}</code>
            </div>

            <div className="about-item">
              <span className="about-label">Version:</span>
              <span className="about-value">Version {APP_VERSION}</span>
            </div>

            <div className="about-notice">
              A .bak copy is saved before every patch. This cannot be turned off.
            </div>
          </div>
        </section>
      </div>

      <div className="settings-footer">
        <button
          type="button"
          className="btn-outline"
          onClick={onResetDefaults}
        >
          Reset to defaults
        </button>
      </div>
    </div>
  );
}

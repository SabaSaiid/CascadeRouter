import type { Health, Scan } from '../../services/contracts.ts';
import type { ApiFailure } from '../../services/transport.ts';
import { dataSourceLabel } from '../../services/display.ts';
import { sanitizeRepoFolderName } from '../../services/recentResults.ts';
import type { AppRoute } from '../../services/router.ts';
import { VIEW_HEADINGS } from '../../services/router.ts';

export interface HeaderProps {
  currentRoute: AppRoute;
  demo: boolean;
  onToggleDemo: (val: boolean) => void;
  health?: Health;
  healthError?: ApiFailure;
  healthLoading: boolean;
  onCheckHealth: () => void;
  analysis?: Scan;
  isOperating: boolean;
  operationStatusText?: string;
  onOpenMobileSidebar: () => void;
  onScanAgain?: () => void;
}

export function Header({
  currentRoute,
  demo,
  onToggleDemo,
  health,
  healthError,
  healthLoading,
  onCheckHealth,
  analysis,
  isOperating,
  operationStatusText,
  onOpenMobileSidebar,
  onScanAgain,
}: HeaderProps) {
  const viewTitle = VIEW_HEADINGS[currentRoute] ?? 'Workbench';

  // Repo folder chip on Workbench
  const repoPath = analysis?.repository_path;
  const repoFolderName = repoPath ? sanitizeRepoFolderName(repoPath) : null;

  // Provenance chip once data exists (not rendered when mock per provenance rules)
  const dataSource = demo ? 'mock' : analysis?.data_source;
  const dsLabel = dataSourceLabel(dataSource, health?.benchmark_provenance, analysis?.timestamp);
  const showProvenanceChip = Boolean(analysis && dataSource && dataSource !== 'mock');
  const provenanceText = dataSource === 'live'
    ? 'NVIDIA Nemotron on Nebius Token Factory'
    : dsLabel.text;

  return (
    <header className="app-topbar">
      {/* Left section: Menu button (mobile), View Title, Repo folder chip */}
      <div className="topbar-left">
        <button
          type="button"
          className="topbar-menu-btn"
          onClick={onOpenMobileSidebar}
          aria-label="Open navigation menu"
        >
          Menu
        </button>

        <h1 className="topbar-title">{viewTitle}</h1>

        {currentRoute === 'workbench' && repoFolderName && (
          <span
            className="topbar-repo-chip"
            title={repoPath}
            aria-label={`Repository folder: ${repoFolderName}`}
          >
            {repoFolderName}
          </span>
        )}
      </div>

      {/* Right section: Activity indicator, Provenance chip, Backend status, Sample data toggle, Scan again */}
      <div className="topbar-right">
        {/* Activity indicator while any operation is running */}
        {isOperating && (
          <div className="topbar-activity" role="status" aria-live="polite">
            <span className="activity-dot" aria-hidden="true" />
            <span className="activity-text">{operationStatusText || 'Working…'}</span>
          </div>
        )}

        {/* Provenance chip */}
        {showProvenanceChip && (
          <span
            className="chip chip-provenance"
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
            {provenanceText}
          </span>
        )}

        {/* Backend status with Check */}
        <div className="topbar-backend-status">
          {health ? (
            <>
              <span className="status-dot connected" aria-hidden="true" />
              <span className="status-text">Backend connected</span>
              <button
                type="button"
                className="btn-link"
                disabled={healthLoading}
                onClick={onCheckHealth}
              >
                {healthLoading ? 'Checking…' : 'Check'}
              </button>
            </>
          ) : healthError ? (
            <>
              <span className="status-dot error" aria-hidden="true" />
              <span className="status-text error">
                {healthError.kind === 'unavailable' ? 'Backend unavailable' : 'Connection failed'}
              </span>
              <button
                type="button"
                className="btn-link"
                disabled={healthLoading}
                onClick={onCheckHealth}
              >
                {healthLoading ? 'Checking…' : 'Check'}
              </button>
            </>
          ) : (
            <>
              <span className="status-dot unchecked" aria-hidden="true" />
              <span className="status-text">Backend not checked</span>
              <button
                type="button"
                className="btn-link"
                disabled={healthLoading}
                onClick={onCheckHealth}
              >
                {healthLoading ? 'Checking…' : 'Check'}
              </button>
            </>
          )}
        </div>

        {/* Sample data switch */}
        <label className="topbar-sample-switch">
          <input
            type="checkbox"
            checked={demo}
            onChange={e => onToggleDemo(e.target.checked)}
            aria-label="Toggle sample data"
          />
          <span className="sample-switch-label">Sample data</span>
        </label>

        {/* Scan again on Workbench */}
        {currentRoute === 'workbench' && onScanAgain && (
          <button
            type="button"
            className="btn-link topbar-scan-again"
            onClick={onScanAgain}
          >
            Scan again
          </button>
        )}
      </div>
    </header>
  );
}

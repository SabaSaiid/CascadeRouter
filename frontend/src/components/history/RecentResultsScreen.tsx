import { useState } from 'react';
import type { RecentResultEntry } from '../../services/recentResults.ts';

export interface RecentResultsScreenProps {
  entries: RecentResultEntry[];
  onOpenResult: (entry: RecentResultEntry) => void;
  onRemoveResult: (id: string) => void;
  onOpenByIds: (ids: {
    analysisId?: string;
    runId?: string;
    optimizationId?: string;
    patchId?: string;
  }) => void;
}

export function RecentResultsScreen({
  entries,
  onOpenResult,
  onRemoveResult,
  onOpenByIds,
}: RecentResultsScreenProps) {
  const [analysisId, setAnalysisId] = useState('');
  const [runId, setRunId] = useState('');
  const [optimizationId, setOptimizationId] = useState('');
  const [patchId, setPatchId] = useState('');

  const handleOpenByIdsSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!analysisId.trim() && !runId.trim() && !optimizationId.trim() && !patchId.trim()) return;
    onOpenByIds({
      analysisId: analysisId.trim() || undefined,
      runId: runId.trim() || undefined,
      optimizationId: optimizationId.trim() || undefined,
      patchId: patchId.trim() || undefined,
    });
  };

  return (
    <div className="recent-results-container">
      <div className="recent-results-header">
        <h2 className="recent-results-title">Recent results</h2>
        <p className="recent-results-desc">
          Past local optimization sessions saved on this device.
        </p>
      </div>

      {entries.length === 0 ? (
        <div className="recent-empty-state" role="status">
          Results you create appear here.
        </div>
      ) : (
        <div className="recent-results-list" role="list">
          {entries.map(entry => (
            <div
              key={entry.id}
              className="recent-result-row"
              role="listitem"
            >
              <div
                className="recent-result-main"
                onClick={() => onOpenResult(entry)}
                role="button"
                tabIndex={0}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpenResult(entry);
                  }
                }}
                aria-label={`Open result for ${entry.repo_folder}`}
              >
                <div className="recent-result-title-line">
                  <span className="recent-repo-name">{entry.repo_folder}</span>
                  <span className="recent-date">{entry.date}</span>
                </div>

                <div className="recent-summary-line">{entry.summary}</div>

                <div className="recent-status-chips">
                  {entry.statuses.map(st => (
                    <span key={st} className={`status-chip chip-${st.toLowerCase()}`}>
                      {st}
                    </span>
                  ))}
                </div>
              </div>

              <div className="recent-result-actions">
                <button
                  type="button"
                  className="btn-outline"
                  onClick={() => onOpenResult(entry)}
                  aria-label={`Open result for ${entry.repo_folder}`}
                >
                  Open
                </button>
                <button
                  type="button"
                  className="btn-link remove-btn"
                  onClick={() => onRemoveResult(entry.id)}
                  aria-label={`Remove result for ${entry.repo_folder}`}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Collapsible Open by ID section */}
      <details className="open-by-id-details">
        <summary className="open-by-id-summary">Open by ID</summary>
        <form onSubmit={handleOpenByIdsSubmit} className="open-by-id-form">
          <p className="open-by-id-help">
            Enter the identifier for a previously stored scan, benchmark run, optimization, or patch.
          </p>

          <div className="open-by-id-grid">
            <label className="open-by-id-field">
              <span className="field-label">Analysis ID</span>
              <input
                type="text"
                className="input-text"
                placeholder="scan_..."
                value={analysisId}
                onChange={e => setAnalysisId(e.target.value)}
              />
            </label>

            <label className="open-by-id-field">
              <span className="field-label">Benchmark Run ID</span>
              <input
                type="text"
                className="input-text"
                placeholder="run_..."
                value={runId}
                onChange={e => setRunId(e.target.value)}
              />
            </label>

            <label className="open-by-id-field">
              <span className="field-label">Optimization ID</span>
              <input
                type="text"
                className="input-text"
                placeholder="opt_..."
                value={optimizationId}
                onChange={e => setOptimizationId(e.target.value)}
              />
            </label>

            <label className="open-by-id-field">
              <span className="field-label">Patch ID</span>
              <input
                type="text"
                className="input-text"
                placeholder="patch_..."
                value={patchId}
                onChange={e => setPatchId(e.target.value)}
              />
            </label>
          </div>

          <div className="open-by-id-actions">
            <button
              type="submit"
              className="btn-outline"
              disabled={!analysisId && !runId && !optimizationId && !patchId}
            >
              Open by ID
            </button>
          </div>
        </form>
      </details>
    </div>
  );
}

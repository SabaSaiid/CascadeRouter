/* oxlint-disable */
import { useEffect, useRef, useState } from 'react';
import type { ApiClient } from '../../services/api.ts';
import type { Scan } from '../../services/contracts.ts';
import { useOperation } from '../../services/useOperation.ts';
import { demoScan } from '../../services/demo.ts';

export interface RepoBarProps {
  api?: ApiClient;
  demo: boolean;
  analysis?: Scan;
  onAnalysis: (scan?: Scan) => void;
  callSearch: string;
  onCallSearchChange: (search: string) => void;
  autoFocusPath?: boolean;
  onPathFocused?: () => void;
}

export function RepoBar({
  api,
  demo,
  analysis,
  onAnalysis,
  callSearch,
  onCallSearchChange,
  autoFocusPath,
  onPathFocused,
}: RepoBarProps) {
  const [path, setPath] = useState('');
  const [isEditing, setIsEditing] = useState(!analysis);
  const pathInputRef = useRef<HTMLInputElement>(null);
  const [state, operation] = useOperation<Scan>();

  const scan = demo ? demoScan : (analysis ?? state.data);
  const busy = state.status === 'loading';

  useEffect(() => {
    if (analysis) {
      setIsEditing(false);
      setPath(analysis.repository_path);
    } else {
      setIsEditing(true);
    }
  }, [analysis]);

  useEffect(() => {
    if (autoFocusPath) {
      setIsEditing(true);
      setTimeout(() => {
        pathInputRef.current?.focus();
        onPathFocused?.();
      }, 50);
    }
  }, [autoFocusPath, onPathFocused]);

  const submit = (pathValue?: string) => {
    const targetPath = (pathValue ?? path).trim();
    if (!targetPath) return;
    void operation.run(s => api!.scan(targetPath, s)).then(result => {
      if (result) {
        onAnalysis(result);
        setIsEditing(false);
      }
    });
  };

  const hasScanned = Boolean(scan);
  const callCount = scan?.nodes.length ?? 0;
  const showSearch = hasScanned && callCount > 8;

  return (
    <div className="repo-bar-container">
      {hasScanned && !isEditing ? (
        <div className="repo-bar-scanned">
          {/* Path in mono + metadata sentence */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <code className="repo-bar-path" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-xs)', color: 'var(--ink)' }}>
              {scan?.repository_path}
            </code>
            <span style={{ color: 'var(--rule)', userSelect: 'none' }}>•</span>
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
              {scan?.scanned_files_count} file{scan?.scanned_files_count !== 1 ? 's' : ''} scanned, {callCount} LLM call{callCount !== 1 ? 's' : ''} found, {scan?.detected_framework ?? 'OpenAI SDK'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* Search field: only visible if > 8 calls */}
            {showSearch && (
              <input
                type="search"
                placeholder="Search calls…"
                value={callSearch}
                onChange={e => onCallSearchChange(e.target.value)}
                className="field-input"
                style={{ width: 180, height: 28, fontSize: 'var(--fs-xs)', padding: '2px 8px' }}
                aria-label="Filter discovered calls"
              />
            )}

            {/* Scan again text button */}
            <button
              type="button"
              className="btn-link"
              onClick={() => setIsEditing(true)}
              style={{ fontSize: 'var(--fs-xs)', padding: '0 4px' }}
            >
              Scan again
            </button>
          </div>
        </div>
      ) : (
        /* Scan Input Form (clean, non-cluttered) */
        <form
          onSubmit={e => {
            e.preventDefault();
            submit();
          }}
          className="repo-bar-form"
          style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', flexWrap: 'wrap' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 260 }}>
            <label htmlFor="repo-bar-input" style={{ fontSize: 'var(--fs-xs)', fontWeight: 500, color: 'var(--ink)', whiteSpace: 'nowrap' }}>
              Repository:
            </label>
            <input
              ref={pathInputRef}
              id="repo-bar-input"
              className="field-input"
              value={path}
              onChange={e => setPath(e.target.value)}
              placeholder="e.g. . or /path/to/repo"
              autoComplete="off"
              disabled={busy}
              style={{ flex: 1, height: 32, fontSize: 'var(--fs-xs)' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              type="submit"
              className="btn-primary"
              disabled={busy || !path.trim() || !api}
              style={{ height: 32, fontSize: 'var(--fs-xs)', padding: '0 12px' }}
            >
              {busy ? 'Scanning…' : 'Scan repository'}
            </button>

            <button
              type="button"
              className="btn-outline"
              disabled={busy}
              onClick={() => {
                setPath('examples/customer_support_agent');
                submit('examples/customer_support_agent');
              }}
              style={{ height: 32, fontSize: 'var(--fs-xs)', padding: '0 10px' }}
            >
              Sample agent
            </button>

            <button
              type="button"
              className="btn-outline"
              disabled={busy}
              onClick={() => {
                setPath('.');
                submit('.');
              }}
              style={{ height: 32, fontSize: 'var(--fs-xs)', padding: '0 10px' }}
            >
              Current dir (.)
            </button>

            {hasScanned && (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setIsEditing(false)}
                style={{ height: 32, fontSize: 'var(--fs-xs)' }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

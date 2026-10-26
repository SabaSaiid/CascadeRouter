import { useState, type FC } from 'react';
import { ArrowRight, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import type { ScanResult } from '../../types';
import { shortModelName } from '../../utils/metrics';

interface RepositoryPaneProps {
  scanResult: ScanResult | null;
  onScan: (repoPath: string) => void;
  isScanning: boolean;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
  /** Per-node recommended model IDs from benchmark, keyed by node_id */
  recommendedModels?: Record<string, string>;
}

const SAMPLE_REPOS = [
  { label: 'sample_repo (bundled)', value: 'tests/fixtures/sample_repo' },
  { label: 'my_agent (demo)', value: 'tests/fixtures/sample_repo' },
];

export const RepositoryPane: FC<RepositoryPaneProps> = ({
  scanResult,
  onScan,
  isScanning,
  selectedNodeId,
  onSelectNode,
  recommendedModels = {},
}) => {
  const [repoPath, setRepoPath] = useState(
    scanResult?.repository_path || 'tests/fixtures/sample_repo'
  );
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});

  const toggleExpand = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  const nodes = scanResult?.nodes ?? [];

  // Summary line: e.g. "3 of 3 calls use Nemotron Ultra"
  const ultraCount = nodes.filter((n) =>
    /ultra/i.test(n.current_model)
  ).length;
  const summaryLine =
    nodes.length > 0
      ? `${ultraCount} of ${nodes.length} calls use Nemotron Ultra`
      : null;

  return (
    <div
      style={{ width: 'var(--cr-left-w)' }}
      className="flex flex-col h-full bg-[var(--cr-panel)] cr-border-r shrink-0 overflow-hidden"
    >
      {/* Pane header */}
      <div className="px-4 py-3 cr-border-b flex items-center justify-between">
        <h2 className="text-xs font-semibold text-[var(--cr-text)]">Repository</h2>
        {scanResult && (
          <span className="text-xs text-[var(--cr-subtle)] num">
            {scanResult.scanned_files_count} files scanned — {scanResult.detected_framework.split('/')[0].trim()}
          </span>
        )}
      </div>

      {/* Repository selector */}
      <div className="px-4 py-3 cr-border-b flex items-center gap-2">
        <select
          id="repo-select"
          value={repoPath}
          onChange={(e) => setRepoPath(e.target.value)}
          className="flex-1 bg-[var(--cr-raised)] cr-border rounded-[var(--cr-r-control)] px-2.5 py-1.5 text-xs text-[var(--cr-muted)] mono focus:outline-none cr-transition"
          style={{ minWidth: 0 }}
        >
          {SAMPLE_REPOS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onScan(repoPath)}
          disabled={isScanning}
          className="btn-outline text-xs shrink-0"
          title="Upload ZIP (not available in demo)"
        >
          {isScanning ? '…' : 'Scan'}
        </button>
      </div>

      {/* Summary line */}
      {summaryLine && (
        <div className="px-4 py-2 cr-border-b text-xs text-[var(--cr-subtle)]">
          {summaryLine}
        </div>
      )}

      {/* Node list */}
      <div className="flex-1 overflow-y-auto" role="list" aria-label="LLM call sites">
        {nodes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 px-4 text-center">
            <p className="text-xs text-[var(--cr-subtle)]">
              {isScanning ? 'Scanning…' : 'Scan a repository to see LLM call sites.'}
            </p>
          </div>
        ) : (
          nodes.map((node) => {
            const isSelected = selectedNodeId === node.node_id;
            const isExpanded = !!expandedNodes[node.node_id];
            const recModel = recommendedModels[node.node_id];
            const currentShort = shortModelName(node.current_model);
            const recShort = recModel ? shortModelName(recModel) : null;

            return (
              <div
                key={node.node_id}
                role="listitem"
                aria-selected={isSelected}
              >
                {/* Main row */}
                <div
                  className={`node-row cr-transition ${isSelected ? 'node-selected' : ''}`}
                  onClick={() => onSelectNode(node.node_id)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && onSelectNode(node.node_id)}
                  aria-label={`Call site: ${node.node_id}`}
                >
                  {/* Top line: node name + result chip */}
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-[var(--cr-text)] truncate">
                      {node.function_name ?? node.node_id}
                    </span>
                    {recShort ? (
                      <span className="chip chip-accent shrink-0">→ {recShort}</span>
                    ) : (
                      <span className="chip shrink-0 mono">{currentShort}</span>
                    )}
                  </div>

                  {/* Bottom line: file:line */}
                  <div className="flex items-center justify-between gap-1">
                    <span className="mono text-xs text-[var(--cr-subtle)] truncate">
                      {node.file_path}:{node.line_number}
                    </span>

                    {/* Expand toggle */}
                    {node.snippet && (
                      <button
                        type="button"
                        className="btn-ghost p-0 min-h-0 h-5 text-[var(--cr-subtle)]"
                        onClick={(e) => toggleExpand(node.node_id, e)}
                        aria-expanded={isExpanded}
                        aria-label={isExpanded ? 'Collapse call site' : 'Expand call site'}
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && node.snippet && (
                  <div className="px-3 pb-3 bg-[var(--cr-canvas)]">
                    <div className="flex items-center justify-between py-1.5">
                      {node.function_name && (
                        <span className="mono text-xs text-[var(--cr-muted)]">
                          {node.function_name}()
                        </span>
                      )}
                      <button
                        type="button"
                        className="btn-ghost p-0 min-h-0 text-xs text-[var(--cr-accent)] flex items-center gap-1"
                        aria-label="View call site source"
                      >
                        <ExternalLink className="w-3 h-3" />
                        View call site
                      </button>
                    </div>
                    <pre className="mono text-xs text-[var(--cr-muted)] bg-[var(--cr-raised)] rounded-[var(--cr-r-chip)] p-2.5 overflow-x-auto leading-relaxed cr-border">
                      {node.snippet}
                    </pre>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Dependency strip (only when edges exist) */}
      {scanResult && scanResult.graph_edges.length > 0 && (
        <div className="px-4 py-3 cr-border-t" aria-label="Call dependency chain">
          <div className="text-xs text-[var(--cr-subtle)] mb-2">Dependencies</div>
          <div className="flex flex-wrap items-center gap-1">
            {/* Render unique chain from edges */}
            {(() => {
              // Build ordered chain
              const edges = scanResult.graph_edges;
              const chain: string[] = [];
              if (edges.length > 0) {
                chain.push(edges[0][0]);
                for (const [, to] of edges) {
                  chain.push(to);
                }
              }
              return chain.map((id, i) => (
                <span key={id} className="flex items-center gap-1">
                  <span className="mono text-xs text-[var(--cr-muted)]">
                    {id.replace('node_', '')}
                  </span>
                  {i < chain.length - 1 && (
                    <ArrowRight className="w-3 h-3 text-[var(--cr-subtle)]" aria-hidden="true" />
                  )}
                </span>
              ));
            })()}
          </div>
        </div>
      )}
    </div>
  );
};

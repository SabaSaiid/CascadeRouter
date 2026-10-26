import { useState, type FC } from 'react';
import {
  FolderGit2,
  FileCode,
  Layers,
  ArrowRight,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import type { ScanResult } from '../../types';

interface RepositoryPaneProps {
  scanResult: ScanResult | null;
  onScan: (repoPath: string) => void;
  isScanning: boolean;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

export const RepositoryPane: FC<RepositoryPaneProps> = ({
  scanResult,
  onScan,
  isScanning,
  selectedNodeId,
  onSelectNode,
}) => {
  const [repoPath, setRepoPath] = useState(
    scanResult?.repository_path || 'tests/fixtures/sample_repo'
  );
  const [expandedSnippets, setExpandedSnippets] = useState<Record<string, boolean>>({});

  const toggleSnippet = (nodeId: string) => {
    setExpandedSnippets((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  return (
    <div className="flex flex-col h-full bg-[#0d121f] border-r border-slate-800/80 overflow-hidden select-none">
      {/* Pane Header */}
      <div className="p-3 border-b border-slate-800 bg-[#0f1627]/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FolderGit2 className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Repository & AST Analysis
          </span>
        </div>
        {scanResult && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
            {scanResult.nodes.length} Nodes Found
          </span>
        )}
      </div>

      {/* Target Repo Input */}
      <div className="p-3 border-b border-slate-800/70 bg-[#0b0f1a]">
        <label className="block text-[11px] text-slate-400 font-medium mb-1.5">
          Target Codebase Path
        </label>
        <div className="flex gap-2">
          <input
            id="input-repo-path"
            type="text"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="e.g. tests/fixtures/sample_repo"
            className="flex-1 bg-slate-900 border border-slate-700/80 rounded px-2.5 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-indigo-500 transition-colors"
          />
          <button
            onClick={() => onScan(repoPath)}
            disabled={isScanning}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-semibold transition-colors disabled:opacity-50"
          >
            {isScanning ? '...' : 'Scan'}
          </button>
        </div>
        {scanResult && (
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
            <span>Framework: <strong className="text-slate-300">{scanResult.detected_framework}</strong></span>
            <span>Files: <strong className="text-slate-300">{scanResult.scanned_files_count} scanned</strong></span>
          </div>
        )}
      </div>

      {/* Discovered Nodes List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {!scanResult || scanResult.nodes.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-center p-4 text-slate-500 border border-dashed border-slate-800 rounded-lg">
            <FileCode className="w-8 h-8 text-slate-600 mb-2" />
            <p className="text-xs font-medium text-slate-400">No AST scan loaded</p>
            <p className="text-[11px] text-slate-600 mt-1">
              Click &quot;Scan&quot; above to inspect Python LLM call sites safely without code execution.
            </p>
          </div>
        ) : (
          scanResult.nodes.map((node) => {
            const isSelected = selectedNodeId === node.node_id;
            const isExpanded = !!expandedSnippets[node.node_id];

            return (
              <div
                key={node.node_id}
                onClick={() => onSelectNode(node.node_id)}
                className={`p-3 rounded-lg border transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-950/40 border-indigo-500/60 shadow-md shadow-indigo-950/50'
                    : 'bg-[#111726] border-slate-800/90 hover:border-slate-700 hover:bg-[#141b2e]'
                }`}
              >
                {/* Node Title & Over-provisioned warning */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-indigo-400" />
                    <span className="font-mono text-xs font-semibold text-slate-200">
                      {node.node_id}
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                    <AlertTriangle className="w-3 h-3 text-amber-400" />
                    Over-provisioned
                  </span>
                </div>

                {/* Location */}
                <div className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-400 font-mono">
                  <FileCode className="w-3 h-3 text-slate-500 shrink-0" />
                  <span className="truncate">{node.file_path}:{node.line_number}</span>
                </div>

                {/* Model baseline call */}
                <div className="mt-2 text-[11px] bg-slate-900/90 rounded p-1.5 border border-slate-800/80">
                  <div className="text-slate-500 text-[10px]">Current Static Assignment:</div>
                  <div className="font-mono text-[11px] text-amber-300/90 truncate font-semibold">
                    {node.current_model.split('/').pop()}
                  </div>
                </div>

                {/* Schema & Function info */}
                {node.function_name && (
                  <div className="mt-2 text-[11px] text-slate-400">
                    <span className="text-slate-500">Function: </span>
                    <span className="text-slate-300 font-mono">{node.function_name}()</span>
                  </div>
                )}

                {/* Snippet expander */}
                {node.snippet && (
                  <div className="mt-2.5 pt-2 border-t border-slate-800/60">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSnippet(node.node_id);
                      }}
                      className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 font-medium"
                    >
                      {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                      <span>{isExpanded ? 'Hide AST Snippet' : 'View AST Call Site'}</span>
                    </button>
                    {isExpanded && (
                      <pre className="mt-1.5 p-2 bg-slate-950 rounded text-[10px] font-mono text-slate-300 overflow-x-auto border border-slate-800">
                        {node.snippet}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* Directed Agent Graph Preview */}
        {scanResult && scanResult.graph_edges.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-800">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2">
              <Layers className="w-3.5 h-3.5 text-purple-400" />
              <span>Static Workflow DAG</span>
            </div>
            <div className="p-2.5 bg-slate-950/70 border border-slate-800/80 rounded-lg">
              <div className="space-y-1.5">
                {scanResult.graph_edges.map(([from, to], idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between text-[11px] font-mono p-1 rounded bg-slate-900/60 border border-slate-800/50"
                  >
                    <span className="text-indigo-300 truncate max-w-[42%]">{from}</span>
                    <ArrowRight className="w-3 h-3 text-slate-600 shrink-0" />
                    <span className="text-emerald-300 truncate max-w-[42%]">{to}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

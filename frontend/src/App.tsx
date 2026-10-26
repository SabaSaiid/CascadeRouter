import { useState, useEffect } from 'react';
import type {
  BenchmarkRun,
  DataSourceMode,
  OptimizeResult,
  ScanResult,
} from './types';
import { api } from './services/api';
import { Header } from './components/layout/Header';
import { RepositoryPane } from './components/repository/RepositoryPane';
import { BenchmarkPane } from './components/benchmark/BenchmarkPane';
import { OptimizationPane } from './components/optimization/OptimizationPane';

export default function App() {
  const [dataSourceMode, setDataSourceMode] = useState<DataSourceMode>(api.getMode());
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [benchmarkRun, setBenchmarkRun] = useState<BenchmarkRun | null>(null);
  const [optimizeResult, setOptimizeResult] = useState<OptimizeResult | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const [isScanning, setIsScanning] = useState(false);
  const [isBenchmarking, setIsBenchmarking] = useState(false);
  const [isOptimizing, setIsOptimizing] = useState(false);

  // Initialize initial scan & benchmark so the workbench opens loaded and beautiful
  useEffect(() => {
    handleScan('tests/fixtures/sample_repo', true);
  }, []);

  const handleModeChange = (mode: DataSourceMode) => {
    setDataSourceMode(mode);
    api.setMode(mode);
  };

  const handleScan = async (repoPath: string, autoChain = false) => {
    setIsScanning(true);
    try {
      const res = await api.scanRepository(repoPath);
      setScanResult(res);
      if (res.nodes.length > 0) {
        setSelectedNodeId(res.nodes[0].node_id);
      }
      if (autoChain) {
        // Auto-load benchmark & optimize mock states for immediate demonstration
        const run = await api.pollBenchmarkRun('run_nebius_bench_7894', 100);
        setBenchmarkRun(run);
        const opt = await api.runOptimization('run_nebius_bench_7894', 0.92);
        setOptimizeResult(opt);
      }
    } catch (err) {
      console.error('Scan error:', err);
    } finally {
      setIsScanning(false);
    }
  };

  const handleBenchmark = async () => {
    if (!scanResult || scanResult.nodes.length === 0) return;
    setIsBenchmarking(true);
    try {
      const runId = await api.startBenchmark(scanResult.nodes.map((n) => n.node_id));
      // Simulate stepped progress
      const run = await api.pollBenchmarkRun(runId, 100);
      setBenchmarkRun(run);
    } catch (err) {
      console.error('Benchmark error:', err);
    } finally {
      setIsBenchmarking(false);
    }
  };

  const handleOptimize = async () => {
    if (!benchmarkRun) return;
    setIsOptimizing(true);
    try {
      const opt = await api.runOptimization(benchmarkRun.run_id, 0.92);
      setOptimizeResult(opt);
    } catch (err) {
      console.error('Optimization error:', err);
    } finally {
      setIsOptimizing(false);
    }
  };

  // Derive per-node recommended models for RepositoryPane chips
  const recommendedModels: Record<string, string> = {};
  if (benchmarkRun) {
    for (const nodeBench of benchmarkRun.nodes) {
      if (nodeBench.recommended_model_id) {
        recommendedModels[nodeBench.node_id] = nodeBench.recommended_model_id;
      }
    }
  }

  // Compute total spend from optimizeResult (data-driven, not hard-coded)
  const totalSpendUsd = optimizeResult?.total_baseline_cost_usd;

  return (
    <div className="flex flex-col h-screen w-screen bg-[var(--cr-canvas)] text-[var(--cr-text)] overflow-hidden">
      {/* Top IDE Header */}
      <Header
        dataSourceMode={dataSourceMode}
        onModeChange={handleModeChange}
        onScan={() => handleScan('tests/fixtures/sample_repo')}
        onBenchmark={handleBenchmark}
        onOptimize={handleOptimize}
        isScanning={isScanning}
        isBenchmarking={isBenchmarking}
        isOptimizing={isOptimizing}
        hasScanResults={!!scanResult && scanResult.nodes.length > 0}
        hasBenchmarkResults={!!benchmarkRun && benchmarkRun.nodes.length > 0}
        totalSpendUsd={totalSpendUsd}
      />

      {/* Main 3-pane workbench */}
      <main className="flex-1 flex overflow-hidden divide-x divide-[var(--cr-line)]">
        {/* Left pane */}
        <RepositoryPane
          scanResult={scanResult}
          onScan={(path) => handleScan(path)}
          isScanning={isScanning}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
          recommendedModels={recommendedModels}
        />

        {/* Centre pane */}
        <BenchmarkPane
          benchmarkRun={benchmarkRun}
          scanResult={scanResult}
          onRunBenchmark={handleBenchmark}
          isBenchmarking={isBenchmarking}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
        />

        {/* Right pane */}
        <OptimizationPane
          optimizeResult={optimizeResult}
          onOptimize={handleOptimize}
          isOptimizing={isOptimizing}
          selectedNodeId={selectedNodeId}
        />
      </main>
    </div>
  );
}

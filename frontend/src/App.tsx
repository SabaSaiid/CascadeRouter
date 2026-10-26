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

  return (
    <div className="flex flex-col h-screen w-screen bg-[#080c14] text-slate-100 overflow-hidden font-sans">
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
      />

      {/* Main 3-Pane Workbench Workspace */}
      <main className="flex-1 grid grid-cols-1 md:grid-cols-[340px_1fr_420px] overflow-hidden divide-x divide-slate-800">
        {/* Left Pane: Repository & AST Analysis */}
        <RepositoryPane
          scanResult={scanResult}
          onScan={(path) => handleScan(path)}
          isScanning={isScanning}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
        />

        {/* Center Pane: Nemotron Benchmark Matrix */}
        <BenchmarkPane
          benchmarkRun={benchmarkRun}
          scanResult={scanResult}
          onRunBenchmark={handleBenchmark}
          isBenchmarking={isBenchmarking}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
        />

        {/* Right Pane: FinOps Optimization & Diff */}
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

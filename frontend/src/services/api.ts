// ==============================================================================
// CascadeRouter IDE - Switchable API Client
// Connects to FastAPI backend or transparently falls back to mock fixtures
// ==============================================================================

import type { BenchmarkRun, DataSourceMode, OptimizeResult, ScanResult } from '../types';
import { MOCK_BENCHMARK_RUN, MOCK_OPTIMIZE_RESULT, MOCK_SCAN_RESULT } from './mockData';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const DEFAULT_MODE: DataSourceMode = (import.meta.env.VITE_DATA_SOURCE as DataSourceMode) || 'mock';

export class ApiClient {
  private mode: DataSourceMode = DEFAULT_MODE;

  public setMode(newMode: DataSourceMode) {
    this.mode = newMode;
  }

  public getMode(): DataSourceMode {
    return this.mode;
  }

  /**
   * Statically scans repository using AST parser
   */
  async scanRepository(repositoryPath: string): Promise<ScanResult> {
    if (this.mode === 'mock') {
      // Simulate brief analysis latency
      await new Promise((r) => setTimeout(r, 600));
      return {
        ...MOCK_SCAN_RESULT,
        repository_path: repositoryPath || MOCK_SCAN_RESULT.repository_path,
        timestamp: new Date().toISOString(),
        data_source: 'mock',
      };
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repository_path: repositoryPath }),
      });

      if (!response.ok) {
        throw new Error(`Scan request failed with HTTP ${response.status}`);
      }

      const data = await response.json();
      return { ...data, data_source: 'live' };
    } catch (err) {
      console.warn('Backend API unavailable. Falling back to mock fixture:', err);
      return { ...MOCK_SCAN_RESULT, data_source: 'mock' };
    }
  }

  /**
   * Launches concurrent benchmark across NVIDIA Nemotron tiers on Nebius Token Factory
   */
  async startBenchmark(nodeIds: string[]): Promise<string> {
    if (this.mode === 'mock') {
      await new Promise((r) => setTimeout(r, 400));
      return 'run_nebius_bench_7894';
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/benchmark`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_ids: nodeIds }),
      });

      if (!response.ok) {
        throw new Error(`Benchmark launch failed with HTTP ${response.status}`);
      }

      const data = await response.json();
      return data.run_id;
    } catch (err) {
      console.warn('Backend API unavailable. Returning mock run ID:', err);
      return 'run_nebius_bench_7894';
    }
  }

  /**
   * Polls running benchmark progress and returns telemetry matrix
   */
  async pollBenchmarkRun(runId: string, simulateStep = 100): Promise<BenchmarkRun> {
    if (this.mode === 'mock') {
      await new Promise((r) => setTimeout(r, 300));
      return {
        ...MOCK_BENCHMARK_RUN,
        run_id: runId,
        progress_pct: simulateStep,
        status: simulateStep >= 100 ? 'complete' : 'running',
        data_source: 'mock',
      };
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/runs/${runId}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch run status: HTTP ${response.status}`);
      }
      const data = await response.json();
      return { ...data, data_source: 'live' };
    } catch (err) {
      console.warn('Failed to poll live run. Using mock data:', err);
      return { ...MOCK_BENCHMARK_RUN, data_source: 'mock' };
    }
  }

  /**
   * Optimizes model assignments, calculates FinOps savings, synthesizes patches & runs regression
   */
  async runOptimization(runId: string, qualityThreshold = 0.92): Promise<OptimizeResult> {
    if (this.mode === 'mock') {
      await new Promise((r) => setTimeout(r, 800));
      return {
        ...MOCK_OPTIMIZE_RESULT,
        data_source: 'mock',
      };
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, quality_threshold: qualityThreshold }),
      });

      if (!response.ok) {
        throw new Error(`Optimization failed: HTTP ${response.status}`);
      }

      const data = await response.json();
      return { ...data, data_source: 'live' };
    } catch (err) {
      console.warn('Optimization API unavailable. Falling back to mock fixture:', err);
      return { ...MOCK_OPTIMIZE_RESULT, data_source: 'mock' };
    }
  }
}

export const api = new ApiClient();

import { useMemo, useState } from 'react';
import { ApiClient } from './services/api.ts';
import { LocalTransport, failure } from './services/transport.ts';
import { useOperation } from './services/useOperation.ts';
import type { Health, Scan, Job, Optimization } from './services/contracts.ts';
import { deriveStep } from './services/display.ts';
import { Header } from './components/layout/Header.tsx';
import { RepositoryPane } from './components/repository/RepositoryPane.tsx';
import { BenchmarkPane } from './components/benchmark/BenchmarkPane.tsx';
import { RightPane } from './components/optimization/RightPane.tsx';

export default function App() {
  const [demo, setDemo] = useState(false);
  const [analysis, setAnalysis] = useState<Scan>();
  const [job, setJob] = useState<Job>();
  const [optimization, setOptimization] = useState<Optimization>();
  const [selected, setSelected] = useState<string>();
  const [mobileTab, setMobileTab] = useState<'calls' | 'benchmark' | 'patch'>('benchmark');
  const [health, healthOperation] = useOperation<Health>();

  const connection = useMemo(() => {
    try { return { api: new ApiClient(new LocalTransport(import.meta.env?.VITE_API_BASE_URL)) }; }
    catch (error) { return { error: failure(error) }; }
  }, []);

  const step = deriveStep(analysis, job, optimization);

  // Determine data source for header chip
  const dataSource = demo ? 'mock' : analysis?.data_source;
  const isMock = dataSource === 'mock' || demo;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workbench">Skip to workbench</a>

      {/* Full-width amber strip for mock / emulated */}
      {isMock && (
        <div className="mock-strip" role="alert" aria-live="polite">
          <span aria-hidden="true">⚠</span>
          Design mockup with sample data. These are not real model results.
        </div>
      )}

      <Header
        demo={demo}
        health={health.data}
        healthLoading={health.status === 'loading'}
        analysis={analysis}
        onCheckHealth={() => healthOperation.run(s => connection.api!.health(s))}
        onOpenDemo={() => {
          healthOperation.reset();
          setAnalysis(undefined);
          setJob(undefined);
          setOptimization(undefined);
          setSelected(undefined);
          setDemo(!demo);
        }}
        step={step}
        onRetrieveAnalysis={id => {
          if (!connection.api) return;
          void connection.api.analysis(id).then(scan => {
            setAnalysis(scan);
            setJob(undefined);
            setOptimization(undefined);
            setSelected(scan.nodes[0]?.node_id);
          });
        }}
        onRetrieveRun={id => {
          if (!connection.api) return;
          void connection.api.run(id).then(j => {
            setJob(j);
            setOptimization(undefined);
          });
        }}
      />

      {/* Mobile tabs for <1024px */}
      <nav className="mobile-tab-bar" aria-label="Workbench sections" role="tablist">
        {(['calls', 'benchmark', 'patch'] as const).map(tabKey => {
          const label = tabKey === 'calls' ? 'Calls' : tabKey === 'benchmark' ? 'Benchmark' : 'Patch';
          return (
            <button
              key={tabKey}
              role="tab"
              aria-selected={mobileTab === tabKey}
              className={`tab-btn${mobileTab === tabKey ? ' active' : ''}`}
              onClick={() => setMobileTab(tabKey)}
              style={{ flex: 1, height: 40 }}
            >
              {label}
            </button>
          );
        })}
      </nav>

      <main id="workbench" className="workbench" data-mobile-tab={mobileTab} key={demo ? 'demo' : 'local'}>
        <RepositoryPane
          api={connection.api}
          demo={demo}
          onAnalysis={scan => {
            setAnalysis(scan);
            setJob(undefined);
            setOptimization(undefined);
            setSelected(scan?.nodes[0]?.node_id);
          }}
          selected={selected}
          onSelect={setSelected}
          step={step}
          optimization={optimization}
        />

        <div className="centre-pane">
          <BenchmarkPane
            key={analysis?.analysis_id ?? 'no-analysis'}
            api={connection.api}
            demo={demo}
            analysis={analysis}
            selected={selected}
            step={step}
            onJob={value => {
              if (value?.run_id !== job?.run_id || !value) setOptimization(undefined);
              setJob(value);
            }}
          />
        </div>

        <RightPane
          key={`${job?.run_id ?? 'no-run'}:${analysis?.analysis_id ?? 'no-analysis'}`}
          api={connection.api}
          demo={demo}
          analysis={analysis}
          job={job}
          step={step}
          onOptimization={setOptimization}
        />
      </main>
    </div>
  );
}

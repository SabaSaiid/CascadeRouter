import { useMemo, useState } from 'react';
import { ApiClient } from './services/api.ts';
import { LocalTransport, failure } from './services/transport.ts';
import { useOperation } from './services/useOperation.ts';
import type { Health, Scan, Job, Optimization } from './services/contracts.ts';
import { Header } from './components/layout/Header.tsx';
import { OperationStatus } from './components/OperationStatus.tsx';
import { RepositoryPane } from './components/repository/RepositoryPane.tsx';
import { BenchmarkPane } from './components/benchmark/BenchmarkPane.tsx';
import { OptimizationPane } from './components/optimization/OptimizationPane.tsx';
import { PatchPane } from './components/patches/PatchPane.tsx';

export default function App() {
  const [demo, setDemo] = useState(false);
  const [analysis, setAnalysis] = useState<Scan>();
  const [job, setJob] = useState<Job>();
  const [optimization, setOptimization] = useState<Optimization>();
  const [selected, setSelected] = useState<string>();
  const [health, healthOperation] = useOperation<Health>();
  const connection = useMemo(() => {
    try { return { api: new ApiClient(new LocalTransport(import.meta.env?.VITE_API_BASE_URL)) }; }
    catch (error) { return { error: failure(error) }; }
  }, []);

  const steps = [
    { href: '#connection-title', label: 'Backend', num: '1', done: !!health.data, active: !analysis },
    { href: '#scan-title', label: 'Scan', num: '2', done: !!analysis, active: !!analysis && !job },
    { href: '#benchmark-title', label: 'Benchmark', num: '3', done: !!job && job.status === 'complete', active: !!job && job.status !== 'complete' },
    { href: '#optimization-title', label: 'Optimize', num: '4', done: !!optimization, active: !!optimization && !optimization.result.decisions_complete },
    { href: '#patches-title', label: 'Proposals', num: '5', done: false, active: false },
  ];

  return (
    <>
      <a className="skip-link" href="#workbench">Skip to workbench</a>
      <Header
        demo={demo}
        onModeChange={() => {
          healthOperation.reset();
          setAnalysis(undefined);
          setJob(undefined);
          setOptimization(undefined);
          setSelected(undefined);
          setDemo(!demo);
        }}
      />

      <nav className="workflow-nav" aria-label="Workflow stages">
        {steps.map((st, i) => (
          <span key={st.href} style={{ display: 'inline-flex', alignItems: 'center' }}>
            <a
              href={st.href}
              className={`workflow-step ${st.done ? 'done' : ''} ${st.active ? 'active' : ''}`}
            >
              <span className="workflow-step-badge">
                {st.done ? '✓' : st.num}
              </span>
              <span>{st.label}</span>
            </a>
            {i < steps.length - 1 && <span className="workflow-divider" aria-hidden="true" />}
          </span>
        ))}
      </nav>

      <main id="workbench" className="workbench" key={demo ? 'demo' : 'local'}>
        <section aria-labelledby="connection-title">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
            <h2 id="connection-title">Backend connection</h2>
            {health.data && (
              <span style={{ fontSize: '12px', color: 'var(--cr-pass)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--cr-pass)' }} />
                Connected (Loopback)
              </span>
            )}
          </div>
          <p>Only an explicitly configured loopback HTTP service is contacted. Repository access remains controlled by the backend.</p>
          {connection.error && <p role="alert">{connection.error.message}</p>}
          <button
            disabled={demo || !connection.api || health.status === 'loading'}
            onClick={() => healthOperation.run(s => connection.api!.health(s))}
          >
            Check local service
          </button>
          <OperationStatus state={health} cancel={healthOperation.cancel} />
          {health.data && (
            <dl>
              <dt>Scan capability</dt>
              <dd>{health.data.scan_available ? 'available' : 'unavailable'}</dd>
              <dt>Configuration required</dt>
              <dd>{String(health.data.configuration_required)}</dd>
              <dt>Benchmark capability</dt>
              <dd>{health.data.benchmark_available ? 'available' : 'unavailable'} — {health.data.benchmark_provenance ?? 'no evidence configured'}</dd>
              <dt>Benchmark restriction</dt>
              <dd>{health.data.benchmark_unavailable_reason ?? 'none reported'}</dd>
            </dl>
          )}
        </section>

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
        />

        <BenchmarkPane
          key={analysis?.analysis_id ?? 'no-analysis'}
          api={connection.api}
          demo={demo}
          analysis={analysis}
          selected={selected}
          onJob={value => {
            if (value?.run_id !== job?.run_id || !value) setOptimization(undefined);
            setJob(value);
          }}
        />

        <OptimizationPane
          key={job?.run_id ?? 'no-run'}
          api={connection.api}
          demo={demo}
          analysis={analysis}
          job={job}
          onOptimization={setOptimization}
        />

        <PatchPane
          key={`${analysis?.analysis_id ?? 'independent'}:${optimization?.optimization_id ?? 'no-optimization'}`}
          api={connection.api}
          demo={demo}
          analysis={analysis}
          optimization={optimization}
        />
      </main>
    </>
  );
}

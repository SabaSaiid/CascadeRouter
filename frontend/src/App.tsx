import { useMemo, useState } from 'react';
import { ApiClient } from './services/api.ts';
import { LocalTransport, failure } from './services/transport.ts';
import { useOperation } from './services/useOperation.ts';
import type { Health } from './services/contracts.ts';
import { Header } from './components/layout/Header.tsx';
import { OperationStatus } from './components/OperationStatus.tsx';
import { demoScan } from './services/demo.ts';

export default function App() {
  const [demo, setDemo] = useState(false);
  const [health, healthOperation] = useOperation<Health>();
  const connection = useMemo(() => {
    try { return { api: new ApiClient(new LocalTransport(import.meta.env.VITE_API_BASE_URL)) }; }
    catch (error) { return { error: failure(error) }; }
  }, []);
  return <><a className="skip-link" href="#workbench">Skip to workbench</a>
    <Header demo={demo} onModeChange={() => { healthOperation.reset(); setDemo(!demo); }} />
    <main id="workbench" className="workbench" key={demo ? 'demo' : 'local'}>
      <section aria-labelledby="connection-title"><h2 id="connection-title">Backend connection</h2>
        <p>Only an explicitly configured loopback HTTP service is contacted. Repository access remains controlled by the backend.</p>
        {connection.error && <p role="alert">{connection.error.message}</p>}
        <button disabled={demo || !connection.api || health.status === 'loading'} onClick={() => healthOperation.run(s => connection.api!.health(s))}>Check local service</button>
        <OperationStatus state={health} cancel={healthOperation.cancel} />
        {health.data && <dl><dt>Scan capability</dt><dd>{health.data.scan_available ? 'available' : 'unavailable'}</dd><dt>Configuration required</dt><dd>{String(health.data.configuration_required)}</dd><dt>Benchmark capability</dt><dd>{health.data.benchmark_available ? 'available' : 'unavailable'} — {health.data.benchmark_provenance ?? 'no evidence configured'}</dd><dt>Benchmark restriction</dt><dd>{health.data.benchmark_unavailable_reason ?? 'none reported'}</dd></dl>}
      </section>
      <section><h2>Repository analysis</h2>{demo ? <p>DEMO / mock: {demoScan.nodes.length} synthetic finding. This fixture is illustrative and cannot authorize backend jobs or proposals.</p> : <p>No repository analyzed. Operations require an explicitly supplied repository authorized by your local backend.</p>}</section>
    </main>
  </>;
}

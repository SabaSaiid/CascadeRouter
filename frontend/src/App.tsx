import { useEffect, useMemo, useState } from 'react';
import { ApiClient } from './services/api.ts';
import { LocalTransport, failure } from './services/transport.ts';
import { useOperation } from './services/useOperation.ts';
import type { Health, Scan, Job, Optimization } from './services/contracts.ts';
import { deriveStep } from './services/display.ts';
import { demoScan } from './services/demo.ts';
import { Header } from './components/layout/Header.tsx';
import { Sidebar } from './components/layout/Sidebar.tsx';
import { HomeScreen } from './components/home/HomeScreen.tsx';
import { RepositoryPane } from './components/repository/RepositoryPane.tsx';
import { BenchmarkPane } from './components/benchmark/BenchmarkPane.tsx';
import { RightPane } from './components/optimization/RightPane.tsx';
import { AnalyticsScreen } from './components/analytics/AnalyticsScreen.tsx';
import { SettingsModal } from './components/modals/SettingsModal.tsx';
import { TermsModal } from './components/modals/TermsModal.tsx';
import { TourModal } from './components/home/TourModal.tsx';
import { getSavedTheme, applyTheme, toggleTheme, type ThemeMode } from './services/theme.ts';

export default function App() {
  const [view, setView] = useState<'home' | 'workbench' | 'analytics'>('home');
  const [demo, setDemo] = useState(false);
  const [analysis, setAnalysis] = useState<Scan>();
  const [job, setJob] = useState<Job>();
  const [optimization, setOptimization] = useState<Optimization>();
  const [selected, setSelected] = useState<string>();
  const [autoFocusPath, setAutoFocusPath] = useState(false);
  const [mobileTab, setMobileTab] = useState<'calls' | 'benchmark' | 'patch'>('benchmark');
  const [health, healthOperation] = useOperation<Health>();

  // Modals & Navigation state
  const [theme, setTheme] = useState<ThemeMode>(() => getSavedTheme());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [termsOpen, setTermsOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const handleToggleTheme = () => {
    const next = toggleTheme(theme);
    setTheme(next);
  };

  const connection = useMemo(() => {
    try { return { api: new ApiClient(new LocalTransport(import.meta.env?.VITE_API_BASE_URL)) }; }
    catch (error) { return { error: failure(error) }; }
  }, []);

  const step = deriveStep(analysis, job, optimization);

  // Determine data source for header chip
  const dataSource = demo ? 'mock' : analysis?.data_source;
  const isMock = dataSource === 'mock' || demo;

  // Show Home when on home view and no analysis loaded, unless in demo
  const showHome = view === 'home' && !analysis && !job && !demo;

  const handleTrySampleAgent = () => {
    if (connection.api) {
      connection.api.scan('examples/customer_support_agent')
        .then(scan => {
          setAnalysis(scan);
          setSelected(scan.nodes[0]?.node_id);
          setJob(undefined);
          setOptimization(undefined);
          setView('workbench');
        })
        .catch(() => {
          // Fallback to mock mode if backend is unavailable
          setDemo(true);
          setAnalysis(demoScan);
          setSelected(demoScan.nodes[0]?.node_id);
          setJob(undefined);
          setOptimization(undefined);
          setView('workbench');
        });
    } else {
      setDemo(true);
      setAnalysis(demoScan);
      setSelected(demoScan.nodes[0]?.node_id);
      setJob(undefined);
      setOptimization(undefined);
      setView('workbench');
    }
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workbench">Skip to workbench</a>

      {/* Full-width amber strip for mock / emulated */}
      {isMock && (
        <div className="mock-strip" role="alert" aria-live="polite">
          <span aria-hidden="true">⚠ </span>
          Mock data, not real model results
        </div>
      )}

      <Header
        demo={demo}
        health={health.data}
        healthError={health.error}
        healthLoading={health.status === 'loading'}
        analysis={analysis}
        job={job}
        optimization={optimization}
        onCheckHealth={() => healthOperation.run(s => connection.api!.health(s))}
        onOpenDemo={() => {
          healthOperation.reset();
          if (!demo) {
            setAnalysis(demoScan);
            setSelected(demoScan.nodes[0]?.node_id);
            setJob(undefined);
            setOptimization(undefined);
            setDemo(true);
            setView('workbench');
          } else {
            setAnalysis(undefined);
            setSelected(undefined);
            setJob(undefined);
            setOptimization(undefined);
            setDemo(false);
            setView('home');
          }
        }}
        onGoHome={() => setView('home')}
        step={step}
        theme={theme}
        onToggleTheme={handleToggleTheme}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenTour={() => setTourOpen(true)}
        onRetrieveAnalysis={id => {
          if (!connection.api) return;
          void connection.api.analysis(id).then(scan => {
            setAnalysis(scan);
            setJob(undefined);
            setOptimization(undefined);
            setSelected(scan.nodes[0]?.node_id);
            setView('workbench');
          });
        }}
        onRetrieveRun={id => {
          if (!connection.api) return;
          void connection.api.run(id).then(j => {
            setJob(j);
            setOptimization(undefined);
            setView('workbench');
          });
        }}
      />

      <div className="app-body-container">
        <Sidebar
          currentView={view}
          onSelectView={v => setView(v)}
          onOpenTour={() => setTourOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenTerms={() => setTermsOpen(true)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          callCount={analysis?.nodes.length}
        />

        <div className="app-main-viewport">
          {view === 'analytics' ? (
            <main id="workbench" className="app-main-viewport">
              <AnalyticsScreen onGoToWorkbench={() => setView('workbench')} />
            </main>
          ) : showHome ? (
            <main id="workbench" className="home-screen-wrapper">
              <span className="sr-only">No analysis result loaded.</span>
              <HomeScreen
                onTrySampleAgent={handleTrySampleAgent}
                onScanOwnRepo={() => {
                  setAutoFocusPath(true);
                  setView('workbench');
                }}
                healthError={health.error}
                onRetryHealth={() => healthOperation.run(s => connection.api!.health(s))}
                recordedRunDate={null}
              />
            </main>
          ) : (
            <>
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
                  autoFocusPath={autoFocusPath}
                  onPathFocused={() => setAutoFocusPath(false)}
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
            </>
          )}
        </div>
      </div>

      {/* Settings Modal */}
      {settingsOpen && (
        <SettingsModal
          onClose={() => setSettingsOpen(false)}
          currentTheme={theme}
          onThemeChange={newTheme => {
            applyTheme(newTheme);
            setTheme(newTheme);
          }}
          isLiveNebius={analysis?.data_source === 'live'}
        />
      )}

      {/* Security & Terms Modal */}
      {termsOpen && (
        <TermsModal
          onClose={() => setTermsOpen(false)}
        />
      )}

      {/* Guided Tour Modal */}
      {tourOpen && (
        <TourModal
          onClose={() => setTourOpen(false)}
          onLaunchDemo={handleTrySampleAgent}
        />
      )}
    </div>
  );
}

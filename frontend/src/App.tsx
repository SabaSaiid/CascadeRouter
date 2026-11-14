import { useEffect, useMemo, useState } from 'react';
import { ApiClient } from './services/api.ts';
import { LocalTransport, failure } from './services/transport.ts';
import { useOperation } from './services/useOperation.ts';
import type { Health, Scan, Job, Optimization, JobAccepted } from './services/contracts.ts';
import { deriveStep, callName } from './services/display.ts';
import { demoScan } from './services/demo.ts';
import { Header } from './components/layout/Header.tsx';
import { RepoBar } from './components/repository/RepoBar.tsx';
import { HomeScreen } from './components/home/HomeScreen.tsx';
import { TierBoard } from './components/board/TierBoard.tsx';
import { DetailTable } from './components/detail/DetailTable.tsx';
import { DecisionPanel } from './components/decision/DecisionPanel.tsx';
import {
  SettingsDrawer,
  HowItWorksDrawer,
  SecurityTermsDrawer,
  RecentSessionsDrawer,
} from './components/modals/Drawers.tsx';

export default function App() {
  const [view, setView] = useState<'home' | 'workbench'>('home');
  const [demo, setDemo] = useState(false);
  const [analysis, setAnalysis] = useState<Scan>();
  const [job, setJob] = useState<Job>();
  const [optimization, setOptimization] = useState<Optimization>();
  const [selected, setSelected] = useState<string>();
  const [autoFocusPath, setAutoFocusPath] = useState(false);
  const [callSearch, setCallSearch] = useState('');
  const [health, healthOperation] = useOperation<Health>();

  // Settings: ONE control: "Only recommend a model if it passes every check" (default true)
  const [strictAllChecks, setStrictAllChecks] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('cascaderouter_strict_checks');
      return saved !== null ? saved === 'true' : true;
    } catch {
      return true;
    }
  });

  const handleStrictChecksChange = (enabled: boolean) => {
    setStrictAllChecks(enabled);
    try {
      localStorage.setItem('cascaderouter_strict_checks', String(enabled));
    } catch {
      // ignore
    }
  };

  // Drawers state
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  const [termsOpen, setTermsOpen] = useState(false);
  const [earlierResultOpen, setEarlierResultOpen] = useState(false);

  // Benchmarking in-flight state
  const [benchmarkingNodeId, setBenchmarkingNodeId] = useState<string>();
  const [progressUnits, setProgressUnits] = useState<{ completed: number; total: number }>();
  const [_benchOpState, benchOperation] = useOperation<JobAccepted>();
  const [_retrievalState, _retrievalOperation] = useOperation<Job>();

  // Ensure document uses clean light theme
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }, []);

  const connection = useMemo(() => {
    try {
      const fetcher: typeof fetch = (input, init) => fetch(input, init);
      return { api: new ApiClient(new LocalTransport(import.meta.env?.VITE_API_BASE_URL, fetcher)) };
    } catch (error) {
      return { error: failure(error) };
    }
  }, []);

  const step = deriveStep(analysis, job, optimization);
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

  const handleBenchmarkCall = (nodeId: string) => {
    if (!analysis || !connection.api) return;
    const node = analysis.nodes.find(n => n.node_id === nodeId);
    const baseline = node?.current_model || 'meta-llama/Meta-Llama-3.1-70B-Instruct';
    const candidates = [
      'nvidia/Llama-3.1-Nemotron-70B-Instruct',
      'meta-llama/Meta-Llama-3.1-8B-Instruct',
    ];

    setBenchmarkingNodeId(nodeId);
    setSelected(nodeId);
    setProgressUnits({ completed: 0, total: 6 });

    console.log('Running benchmark for node:', nodeId, 'analysis_id:', analysis.analysis_id);
    void benchOperation.run(async s => {
      try {
        const res = await connection.api!.benchmark({
          analysis_id: analysis.analysis_id,
          node_ids: [nodeId],
          baseline_model_id: baseline,
          candidate_model_ids: candidates,
          benchmark_case_set_id: 'nebius_standard_cases',
          evaluation_profile_id: 'json_eval_profile',
        }, s);
        console.log('Benchmark response:', res);
        return res;
      } catch (err) {
        console.error('Benchmark API call failed:', err);
        throw err;
      }
    }).then(async accepted => {
      if (accepted) {
        setProgressUnits({ completed: 3, total: 6 });

        // Poll for run completion
        let completedJob: Job | undefined;
        for (let attempt = 0; attempt < 30; attempt++) {
          try {
            const j = await connection.api!.run(accepted.run_id);
            if (j.status === 'complete' || j.status === 'error' || j.status === 'cancelled') {
              completedJob = j;
              break;
            }
          } catch {
            // retry
          }
          await new Promise(r => setTimeout(r, 100));
        }

        if (completedJob) {
          setJob(completedJob);
          setProgressUnits({ completed: 6, total: 6 });
          setBenchmarkingNodeId(undefined);

          // Automatically trigger optimization evaluation
          try {
            const opt = await connection.api!.optimize({
              analysis_id: analysis.analysis_id,
              run_id: completedJob.run_id,
              case_set: completedJob.plan.case_set,
              evaluation_profile: completedJob.plan.evaluation_profile,
            });
            if (opt) setOptimization(opt);
          } catch {
            // ignore
          }
        } else {
          setBenchmarkingNodeId(undefined);
        }
      } else {
        setBenchmarkingNodeId(undefined);
      }
    }).catch(() => {
      setBenchmarkingNodeId(undefined);
    });
  };

  // Filter calls by search query if > 8 calls
  const filteredCalls = useMemo(() => {
    if (!analysis) return [];
    if (!callSearch.trim() || analysis.nodes.length <= 8) {
      return analysis.nodes;
    }
    const q = callSearch.toLowerCase();
    return analysis.nodes.filter(node => {
      const name = callName(node).toLowerCase();
      const file = node.file_path.toLowerCase();
      const fn = (node.function_name ?? '').toLowerCase();
      const model = (node.current_model ?? '').toLowerCase();
      return name.includes(q) || file.includes(q) || fn.includes(q) || model.includes(q);
    });
  }, [analysis, callSearch]);

  const selectedNode = selected && analysis ? analysis.nodes.find(n => n.node_id === selected) : analysis?.nodes[0];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workbench">Skip to workbench</a>

      {/* Amber alert strip for mock / demo data */}
      {isMock && (
        <div className="mock-strip" role="alert" aria-live="polite">
          <span aria-hidden="true">⚠ </span>
          Mock data, not real model results
        </div>
      )}

      {/* Top Header (56px) */}
      <Header
        demo={demo}
        health={health.data}
        healthError={health.error}
        healthLoading={health.status === 'loading'}
        analysis={analysis}
        job={job}
        optimization={optimization}
        onCheckHealth={() => healthOperation.run(s => connection.api!.health(s))}
        onGoHome={() => {
          setView('home');
          setAnalysis(undefined);
          setJob(undefined);
          setOptimization(undefined);
          setDemo(false);
        }}
        step={step}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenHowItWorks={() => setHowItWorksOpen(true)}
        onOpenSecurityTerms={() => setTermsOpen(true)}
        onOpenEarlierResult={() => setEarlierResultOpen(true)}
      />

      {/* Main Viewport */}
      {showHome ? (
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
        <main id="workbench" className="workbench-container" key={demo ? 'demo' : 'local'}>
          {/* Repository bar under the header */}
          <RepoBar
            api={connection.api}
            demo={demo}
            analysis={analysis}
            onAnalysis={scan => {
              setAnalysis(scan);
              setJob(undefined);
              setOptimization(undefined);
              setSelected(scan?.nodes[0]?.node_id);
            }}
            callSearch={callSearch}
            onCallSearchChange={setCallSearch}
            autoFocusPath={autoFocusPath}
            onPathFocused={() => setAutoFocusPath(false)}
          />

          {/* Route Board (full width signature component) */}
          <div className="workbench-board-section">
            <TierBoard
              calls={filteredCalls}
              selectedId={selected ?? selectedNode?.node_id}
              onSelectCall={id => setSelected(id)}
              job={job}
              optimization={optimization}
              onBenchmarkCall={handleBenchmarkCall}
              benchmarkingNodeId={benchmarkingNodeId}
              progressUnits={progressUnits}
            />
          </div>

          {/* Bottom Split: Detail Table on Left, Decision Panel on Right */}
          <div className="workbench-bottom-split">
            <div className="workbench-detail-col">
              <DetailTable
                selectedNode={selectedNode}
                job={job}
                optimization={optimization}
                onBenchmark={selectedNode ? () => handleBenchmarkCall(selectedNode.node_id) : undefined}
                isBenchmarking={Boolean(selectedNode && benchmarkingNodeId === selectedNode.node_id)}
              />
            </div>

            <div className="workbench-decision-col">
              <DecisionPanel
                api={connection.api}
                demo={demo}
                analysis={analysis}
                job={job}
                optimization={optimization}
                selectedNode={selectedNode}
                step={step}
                strictAllChecks={strictAllChecks}
                onOptimization={setOptimization}
                onApplySuccess={() => {}}
              />
            </div>
          </div>
        </main>
      )}

      {/* Drawers */}
      {settingsOpen && (
        <SettingsDrawer
          onClose={() => setSettingsOpen(false)}
          strictAllChecks={strictAllChecks}
          onStrictAllChecksChange={handleStrictChecksChange}
        />
      )}

      {howItWorksOpen && (
        <HowItWorksDrawer
          onClose={() => setHowItWorksOpen(false)}
        />
      )}

      {termsOpen && (
        <SecurityTermsDrawer
          onClose={() => setTermsOpen(false)}
        />
      )}

      {earlierResultOpen && (
        <RecentSessionsDrawer
          onClose={() => setEarlierResultOpen(false)}
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
      )}
    </div>
  );
}

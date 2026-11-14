import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { ApiClient } from './services/api.ts';
import { LocalTransport, failure } from './services/transport.ts';
import { useOperation } from './services/useOperation.ts';
import type {
  Health,
  Scan,
  Job,
  Optimization,
  JobAccepted,
  Backend_RoutingDecision,
  Backend_OptimizationCandidate,
} from './services/contracts.ts';
import { deriveStep, callName, shortModelName, savingPercentage } from './services/display.ts';
import { demoScan, demoJob, demoOptimization } from './services/demo.ts';
import { derivePipelineSteps } from './services/pipeline.ts';
import {
  getRecentResults,
  saveRecentResult,
  removeRecentResult,
  sanitizeRepoFolderName,
  type RecentResultEntry,
} from './services/recentResults.ts';
import {
  loadSettings,
  saveSettings,
  parseCandidateModelIds,
  DEFAULT_SETTINGS,
  type AppSettings,
} from './services/settings.ts';
import {
  globalNoticeQueue,
  type NoticeItem,
} from './services/notices.ts';
import {
  parseRoute,
  navigateTo,
  updateDocumentTitle,
  type AppRoute,
} from './services/router.ts';

import { Sidebar } from './components/layout/Sidebar.tsx';
import { Header } from './components/layout/Header.tsx';
import { RepoBar } from './components/repository/RepoBar.tsx';
import { HomeScreen } from './components/home/HomeScreen.tsx';
import { TierBoard } from './components/board/TierBoard.tsx';
import { DetailTable } from './components/detail/DetailTable.tsx';
import { DecisionPanel } from './components/decision/DecisionPanel.tsx';
import { RecentResultsScreen } from './components/history/RecentResultsScreen.tsx';
import { SettingsScreen } from './components/settings/SettingsScreen.tsx';
import { HowItWorksScreen } from './components/guide/HowItWorksScreen.tsx';
import { SecurityTermsScreen } from './components/security/SecurityTermsScreen.tsx';
import { CompletionNotices } from './components/notices/CompletionNotices.tsx';

export default function App() {
  // Hash routing
  const [currentRoute, setCurrentRoute] = useState<AppRoute>(() => {
    if (typeof window !== 'undefined') {
      return parseRoute(window.location.hash);
    }
    return 'home';
  });

  // Mobile drawer open state (< 1280px)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Settings
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());

  // Demo / Sample data state (synced with settings.dataSource === 'sample')
  const [demo, setDemo] = useState<boolean>(() => loadSettings().dataSource === 'sample');

  // Core application state
  const [analysis, setAnalysis] = useState<Scan>();
  const [job, setJob] = useState<Job>();
  const [optimization, setOptimization] = useState<Optimization>();
  const [patchApplied, setPatchApplied] = useState(false);
  const [selected, setSelected] = useState<string>();
  const [autoFocusPath, setAutoFocusPath] = useState(false);
  const [callSearch, setCallSearch] = useState('');

  // Operations
  const [health, healthOperation] = useOperation<Health>();
  const [benchmarkingNodeId, setBenchmarkingNodeId] = useState<string>();
  const [progressUnits, setProgressUnits] = useState<{ completed: number; total: number }>();
  const [_benchOpState, benchOperation] = useOperation<JobAccepted>();

  // Activity status text
  const [operationStatusText, setOperationStatusText] = useState<string>();

  // Completion notices
  const [notices, setNotices] = useState<NoticeItem[]>([]);

  // Recent results list
  const [recentEntries, setRecentEntries] = useState<RecentResultEntry[]>(() => getRecentResults());

  // Section focus ref for Workbench
  const repoBarRef = useRef<HTMLDivElement>(null);
  const boardSectionRef = useRef<HTMLDivElement>(null);
  const decisionSectionRef = useRef<HTMLDivElement>(null);

  // Connection
  const connection = useMemo(() => {
    try {
      const fetcher: typeof fetch = (input, init) => fetch(input, init);
      return { api: new ApiClient(new LocalTransport(import.meta.env?.VITE_API_BASE_URL, fetcher)) };
    } catch (error) {
      return { error: failure(error) };
    }
  }, []);

  // Listen for hashchange events
  useEffect(() => {
    const handleHashChange = () => {
      const newRoute = parseRoute(window.location.hash);
      setCurrentRoute(newRoute);
      updateDocumentTitle(newRoute);
    };
    window.addEventListener('hashchange', handleHashChange);
    updateDocumentTitle(currentRoute);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [currentRoute]);

  // Subscribe to completion notice queue
  useEffect(() => {
    const unsub = globalNoticeQueue.subscribe(setNotices);
    return unsub;
  }, []);

  // Sync theme with settings
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const mode = settings.appearance;
    if (mode === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else if (mode === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      // System mode
      const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    }
  }, [settings.appearance]);

  // Re-check backend health helper (used manually and automatically on request failure)
  const triggerHealthCheck = useCallback(() => {
    if (!connection.api) return;
    void healthOperation.run(s => connection.api!.health(s));
  }, [connection.api, healthOperation]);

  // Auto re-check health on request failures
  const handleRequestFailure = useCallback((err?: unknown) => {
    console.warn('API operation failed; automatically re-checking backend health:', err);
    triggerHealthCheck();
  }, [triggerHealthCheck]);

  // Handle route change
  const handleNavigate = (route: AppRoute) => {
    navigateTo(route);
    setCurrentRoute(route);
    setMobileSidebarOpen(false);
  };

  // Pipeline step click opens Workbench and focuses the relevant part
  const handleSelectPipelineStep = (stepKey: 'scan' | 'benchmark' | 'recommend' | 'patch') => {
    handleNavigate('workbench');
    setTimeout(() => {
      if (stepKey === 'scan') {
        repoBarRef.current?.scrollIntoView({ behavior: 'smooth' });
        setAutoFocusPath(true);
      } else if (stepKey === 'benchmark') {
        boardSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
      } else if (stepKey === 'recommend' || stepKey === 'patch') {
        decisionSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    }, 50);
  };

  // Update settings handler
  const handleUpdateSettings = (newSettings: AppSettings) => {
    setSettings(newSettings);
    saveSettings(newSettings);
    if (newSettings.dataSource === 'sample' && !demo) {
      setDemo(true);
    } else if (newSettings.dataSource !== 'sample' && demo) {
      setDemo(false);
    }
  };

  const handleResetSettingsDefaults = () => {
    setSettings(DEFAULT_SETTINGS);
    saveSettings(DEFAULT_SETTINGS);
    setDemo(false);
  };

  // Toggle sample data
  const handleToggleSampleData = (enabled: boolean) => {
    setDemo(enabled);
    const updated: AppSettings = {
      ...settings,
      dataSource: enabled ? 'sample' : 'live',
    };
    setSettings(updated);
    saveSettings(updated);

    if (enabled && !analysis) {
      setAnalysis(demoScan);
      setSelected(demoScan.nodes[0]?.node_id);
    }
  };

  // Record a successful session in recent results
  const recordRecentSession = useCallback((
    scanData?: Scan,
    jobData?: Job,
    optData?: Optimization,
    patchId?: string,
    applied = false
  ) => {
    if (!scanData) return;
    const cleanFolder = sanitizeRepoFolderName(scanData.repository_path);
    const callsFound = scanData.nodes.length;
    let callsCanMove = 0;
    let savingPct = '—';

    if (optData) {
      callsCanMove = optData.result.decisions.filter(
        d => d.status === 'recommended' &&
             d.selected_model_id &&
             d.selected_model_id !== d.baseline_model_id
      ).length;
      if (optData.result.decisions[0]) {
        const d = optData.result.decisions[0];
        const base = d.candidates.find(c => c.model.identifier === d.baseline_model_id);
        const sel = d.candidates.find(c => c.model.identifier === d.selected_model_id);
        savingPct = savingPercentage(base?.cost_total_usd, sel?.cost_total_usd);
      }
    }

    const statuses: ('Scanned' | 'Benchmarked' | 'Patched')[] = ['Scanned'];
    if (jobData && jobData.status === 'complete') statuses.push('Benchmarked');
    if (applied || patchId) statuses.push('Patched');

    const dateStr = new Date().toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

    const summaryText = callsCanMove > 0
      ? `${callsFound} calls found, ${callsCanMove} can move (${savingPct} less)`
      : `${callsFound} calls found`;

    saveRecentResult({
      analysis_id: scanData.analysis_id,
      run_id: jobData?.run_id,
      optimization_id: optData?.optimization_id || undefined,
      patch_id: patchId,
      repo_folder: cleanFolder,
      date: dateStr,
      calls_found: callsFound,
      calls_can_move: callsCanMove,
      saving_percentage: savingPct,
      statuses,
      summary: summaryText,
    });

    setRecentEntries(getRecentResults());
  }, []);

  // Try the sample agent from Home
  const handleTrySampleAgent = () => {
    setOperationStatusText('Scanning sample repository…');
    if (connection.api) {
      connection.api.scan('examples/customer_support_agent')
        .then(scan => {
          setAnalysis(scan);
          setSelected(scan.nodes[0]?.node_id);
          setJob(undefined);
          setOptimization(undefined);
          setPatchApplied(false);
          setOperationStatusText(undefined);
          recordRecentSession(scan);
          handleNavigate('workbench');
        })
        .catch(err => {
          handleRequestFailure(err);
          setDemo(true);
          setAnalysis(demoScan);
          setSelected(demoScan.nodes[0]?.node_id);
          setJob(undefined);
          setOptimization(undefined);
          setPatchApplied(false);
          setOperationStatusText(undefined);
          recordRecentSession(demoScan);
          handleNavigate('workbench');
        });
    } else {
      setDemo(true);
      setAnalysis(demoScan);
      setSelected(demoScan.nodes[0]?.node_id);
      setJob(undefined);
      setOptimization(undefined);
      setPatchApplied(false);
      setOperationStatusText(undefined);
      recordRecentSession(demoScan);
      handleNavigate('workbench');
    }
  };

  // Benchmark a call
  const handleBenchmarkCall = (nodeId: string) => {
    if (!analysis) return;
    const node = analysis.nodes.find(n => n.node_id === nodeId);
    const baseline = node?.current_model || settings.baselineModelId || 'meta-llama/Meta-Llama-3.1-70B-Instruct';

    const parsedCandidates = parseCandidateModelIds(settings.candidateModelIds);
    const candidates = parsedCandidates.valid.length > 0
      ? parsedCandidates.valid
      : ['nvidia/Llama-3.1-Nemotron-70B-Instruct', 'meta-llama/Meta-Llama-3.1-8B-Instruct'];

    const totalCalls = analysis.nodes.length;
    setBenchmarkingNodeId(nodeId);
    setSelected(nodeId);
    setProgressUnits({ completed: 1, total: totalCalls });
    setOperationStatusText(`Benchmarking, 2 of ${totalCalls} calls`);

    // In demo mode, load demo benchmark and optimization
    if (demo || !connection.api) {
      setTimeout(() => {
        setProgressUnits({ completed: 2, total: totalCalls });
        setTimeout(() => {
          setJob(demoJob);
          setOptimization(demoOptimization);
          setBenchmarkingNodeId(undefined);
          setOperationStatusText(undefined);

          // Add completion notice
          const callLabel = node ? callName(node) : 'Call';
          const recDecision = demoOptimization.result.decisions.find((d: Backend_RoutingDecision) => d.node_id === nodeId) ?? demoOptimization.result.decisions[0];
          if (recDecision && recDecision.selected_model_id && recDecision.selected_model_id !== recDecision.baseline_model_id) {
            const tierShort = shortModelName(recDecision.selected_model_id);
            const baseC = recDecision.candidates.find((c: Backend_OptimizationCandidate) => c.model.identifier === recDecision.baseline_model_id);
            const selC = recDecision.candidates.find((c: Backend_OptimizationCandidate) => c.model.identifier === recDecision.selected_model_id);
            const pct = savingPercentage(baseC?.cost_total_usd, selC?.cost_total_usd);
            globalNoticeQueue.addNotice(`${callLabel} finished. It can move to ${tierShort} and save ${pct}.`);
          }

          recordRecentSession(analysis, demoJob, demoOptimization);
        }, 300);
      }, 300);
      return;
    }

    void benchOperation.run(async s => {
      try {
        const res = await connection.api!.benchmark({
          analysis_id: analysis.analysis_id,
          node_ids: [nodeId],
          baseline_model_id: baseline,
          candidate_model_ids: candidates,
          benchmark_case_set_id: settings.caseSetId || 'nebius_standard_cases',
          evaluation_profile_id: settings.evaluationProfileId || 'json_eval_profile',
        }, s);
        return res;
      } catch (err) {
        handleRequestFailure(err);
        throw err;
      }
    }).then(async accepted => {
      if (accepted) {
        setProgressUnits({ completed: 2, total: totalCalls });
        setOperationStatusText(`Benchmarking, 2 of ${totalCalls} calls`);

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
          await new Promise(r => setTimeout(r, 120));
        }

        if (completedJob) {
          // Allow in-flight benchmarking progress (k of N tested, stations fill) to be visible
          await new Promise(r => setTimeout(r, 800));
          setJob(completedJob);
          setProgressUnits({ completed: totalCalls, total: totalCalls });
          setBenchmarkingNodeId(undefined);

          // Automatically trigger optimization evaluation
          try {
            const opt = await connection.api!.optimize({
              analysis_id: analysis.analysis_id,
              run_id: completedJob.run_id,
              case_set: completedJob.plan.case_set,
              evaluation_profile: completedJob.plan.evaluation_profile,
            });

            if (opt) {
              setOptimization(opt);

              // Surface completion notice
              const callLabel = node ? callName(node) : 'Call';
              const recDecision = opt.result.decisions.find((d: Backend_RoutingDecision) => d.node_id === nodeId) ?? opt.result.decisions[0];
              if (recDecision && recDecision.selected_model_id && recDecision.selected_model_id !== recDecision.baseline_model_id) {
                const tierShort = shortModelName(recDecision.selected_model_id);
                const baseC = recDecision.candidates.find((c: Backend_OptimizationCandidate) => c.model.identifier === recDecision.baseline_model_id);
                const selC = recDecision.candidates.find((c: Backend_OptimizationCandidate) => c.model.identifier === recDecision.selected_model_id);
                const pct = savingPercentage(baseC?.cost_total_usd, selC?.cost_total_usd);
                globalNoticeQueue.addNotice(`${callLabel} finished. It can move to ${tierShort} and save ${pct}.`);
              }

              recordRecentSession(analysis, completedJob, opt);
            }
          } catch (err) {
            handleRequestFailure(err);
          }
        } else {
          setBenchmarkingNodeId(undefined);
        }
      } else {
        setBenchmarkingNodeId(undefined);
      }
      setOperationStatusText(undefined);
    }).catch(err => {
      setBenchmarkingNodeId(undefined);
      setOperationStatusText(undefined);
      handleRequestFailure(err);
    });
  };

  // Re-open a saved recent result
  const handleOpenRecentResult = (entry: RecentResultEntry) => {
    if (entry.analysis_id && connection.api) {
      setOperationStatusText('Restoring session…');
      connection.api.analysis(entry.analysis_id)
        .then(scan => {
          setAnalysis(scan);
          setSelected(scan.nodes[0]?.node_id);
          if (entry.run_id) {
            return connection.api!.run(entry.run_id).then(j => {
              setJob(j);
              if (entry.optimization_id) {
                // If optimization id present, optimize
                return connection.api!.optimize({
                  analysis_id: scan.analysis_id,
                  run_id: j.run_id,
                  case_set: j.plan.case_set,
                  evaluation_profile: j.plan.evaluation_profile,
                }).then(opt => setOptimization(opt)).catch(() => {});
              }
            });
          }
        })
        .catch(err => {
          handleRequestFailure(err);
        })
        .finally(() => {
          setOperationStatusText(undefined);
          handleNavigate('workbench');
        });
    } else {
      // Fallback
      handleNavigate('workbench');
    }
  };

  // Open by IDs
  const handleOpenByIds = ({
    analysisId,
    runId,
  }: {
    analysisId?: string;
    runId?: string;
    optimizationId?: string;
    patchId?: string;
  }) => {
    if (!connection.api) return;
    if (analysisId) {
      setOperationStatusText('Retrieving analysis…');
      connection.api.analysis(analysisId)
        .then(scan => {
          setAnalysis(scan);
          setSelected(scan.nodes[0]?.node_id);
          if (runId) {
            return connection.api!.run(runId).then(j => setJob(j));
          }
        })
        .catch(err => handleRequestFailure(err))
        .finally(() => {
          setOperationStatusText(undefined);
          handleNavigate('workbench');
        });
    }
  };

  const handleRemoveRecentResult = (id: string) => {
    removeRecentResult(id);
    setRecentEntries(getRecentResults());
  };

  // Step and pipeline derivations
  const step = deriveStep(analysis, job, optimization);
  const pipelineSteps = derivePipelineSteps({
    analysis,
    job,
    optimization,
    isBenchmarking: Boolean(benchmarkingNodeId),
    benchmarkingUnits: progressUnits,
    patchApplied,
  });

  const dataSource = demo ? 'mock' : analysis?.data_source;
  const isMock = dataSource === 'mock' || demo;

  // Filtered calls
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

  const selectedNode = selected && analysis
    ? analysis.nodes.find(n => n.node_id === selected)
    : analysis?.nodes[0];

  return (
    <div className="app-shell-root">
      <a className="skip-link" href="#workbench">Skip to workbench</a>

      {/* Amber alert banner for mock / sample data */}
      {isMock && (
        <div className="mock-strip" role="alert" aria-live="polite">
          <span aria-hidden="true">⚠ </span>
          Mock data, not real model results
        </div>
      )}

      <div className="app-shell-layout">
        {/* Left Sidebar (232px on desktop >= 1280px; drawer below 1280px) */}
        <Sidebar
          currentRoute={currentRoute}
          onNavigate={handleNavigate}
          pipelineSteps={pipelineSteps}
          onSelectPipelineStep={handleSelectPipelineStep}
          recentResultsCount={recentEntries.length}
          isOpenOnMobile={mobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
        />

        {/* Main Viewport */}
        <div className="app-main-viewport">
          {/* Top Bar (56px) */}
          <Header
            currentRoute={currentRoute}
            demo={demo}
            onToggleDemo={handleToggleSampleData}
            health={health.data}
            healthError={health.error}
            healthLoading={health.status === 'loading'}
            onCheckHealth={triggerHealthCheck}
            analysis={analysis}
            isOperating={Boolean(benchmarkingNodeId || operationStatusText)}
            operationStatusText={operationStatusText}
            onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
            onScanAgain={() => {
              handleNavigate('workbench');
              setAutoFocusPath(true);
            }}
          />

          {/* Completion Notices (below top bar on the right, max 2) */}
          <CompletionNotices
            notices={notices}
            onDismiss={id => globalNoticeQueue.dismiss(id)}
          />

          {/* View Content */}
          <main id="workbench" className="app-view-content">
            {currentRoute === 'home' && (
              <div className="home-screen-wrapper">
                <span className="sr-only">No analysis result loaded.</span>
                <HomeScreen
                  onTrySampleAgent={handleTrySampleAgent}
                  onScanOwnRepo={() => {
                    setAutoFocusPath(true);
                    handleNavigate('workbench');
                  }}
                  healthError={health.error}
                  onRetryHealth={triggerHealthCheck}
                  recordedRunDate={null}
                />
              </div>
            )}

            {currentRoute === 'workbench' && (
              <div className="workbench-container" key={demo ? 'demo' : 'local'}>
                {/* Repository bar */}
                <div ref={repoBarRef}>
                  <RepoBar
                    api={connection.api}
                    demo={demo}
                    analysis={analysis}
                    onAnalysis={scan => {
                      setAnalysis(scan);
                      setJob(undefined);
                      setOptimization(undefined);
                      setPatchApplied(false);
                      setSelected(scan?.nodes[0]?.node_id);
                      recordRecentSession(scan);
                    }}
                    callSearch={callSearch}
                    onCallSearchChange={setCallSearch}
                    autoFocusPath={autoFocusPath}
                    onPathFocused={() => setAutoFocusPath(false)}
                  />
                </div>

                {/* Route Board */}
                <div ref={boardSectionRef} className="workbench-board-section">
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
                <div ref={decisionSectionRef} className="workbench-bottom-split">
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
                      strictAllChecks={settings.strictAllChecks}
                      onOptimization={setOptimization}
                      onApplySuccess={() => {
                        setPatchApplied(true);
                        recordRecentSession(analysis, job, optimization, undefined, true);
                      }}
                    />
                  </div>
                </div>
              </div>
            )}

            {currentRoute === 'history' && (
              <RecentResultsScreen
                entries={recentEntries}
                onOpenResult={handleOpenRecentResult}
                onRemoveResult={handleRemoveRecentResult}
                onOpenByIds={handleOpenByIds}
              />
            )}

            {currentRoute === 'settings' && (
              <SettingsScreen
                settings={settings}
                onUpdateSettings={handleUpdateSettings}
                health={health.data}
                backendBaseUrl={import.meta.env?.VITE_API_BASE_URL}
                onResetDefaults={handleResetSettingsDefaults}
              />
            )}

            {currentRoute === 'guide' && <HowItWorksScreen />}

            {currentRoute === 'security' && <SecurityTermsScreen />}
          </main>
        </div>
      </div>
    </div>
  );
}

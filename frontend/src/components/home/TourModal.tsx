import { useEffect, useState } from 'react';

export interface TourModalProps {
  onClose: () => void;
  onLaunchDemo?: () => void;
}

export function TourModal({ onClose, onLaunchDemo }: TourModalProps) {
  const [currentStep, setCurrentStep] = useState(0);

  const steps = [
    {
      stepNumber: '01',
      badge: 'The FinOps Crisis',
      title: 'Why Developers Burn 80% of Their AI Budget',
      description: 'In modern multi-agent systems, developers frequently hardcode expensive frontier models (like GPT-4o or monolithic 70B models) across every agent step. Even routine tasks like user intent triage, routing, and JSON extraction are executed on expensive models, needlessly burning capital and introducing high latency.',
      diagram: (
        <div style={{ background: 'var(--paper)', padding: 14, borderRadius: 'var(--r-ctrl)', border: '1px solid var(--rule)', fontFamily: 'var(--font-mono)', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ color: 'var(--loss)' }}>❌ Monolithic Hardcoded Flow:</div>
          <div>[User Message] ──► [Intent Triage: GPT-4o ($5.00/1M)] ──► [JSON Parse: GPT-4o ($5.00/1M)] ──► [Reply: GPT-4o]</div>
          <div style={{ color: 'var(--muted)', fontSize: '10px' }}>Total Cost: ~\$15.00 / 1M tokens • Average TTFT: ~520ms</div>
        </div>
      ),
      tip: 'Routine intent routing can be done with an 8B model for 91% less cost in under 80 milliseconds.',
    },
    {
      stepNumber: '02',
      badge: 'Zero-Execution AST Scanner',
      title: 'Safe Static Analysis of Your AI Codebase',
      description: 'CascadeRouter parses Python codebases using static Abstract Syntax Tree (AST) scanning. It discovers all call sites (OpenAI, AsyncOpenAI, LiteLLM) and maps variable data-dependencies into a live visual Directed Acyclic Graph (DAG) without ever running or importing untrusted code.',
      diagram: (
        <div style={{ background: 'var(--paper)', padding: 14, borderRadius: 'var(--r-ctrl)', border: '1px solid var(--rule)', fontFamily: 'var(--font-mono)', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ color: 'var(--navy)' }}>🔍 Static AST Discovery:</div>
          <div>Parsed `pipeline.py`: 3 LLM calls identified</div>
          <div>• Node 1: `triage_intent()` ──► outputs `category` variable</div>
          <div>• Node 2: `extract_order()` ──► consumes `category`, outputs `order_json`</div>
          <div>• Node 3: `draft_reply()`   ──► consumes `order_json`, outputs final customer message</div>
        </div>
      ),
      tip: 'Your proprietary source code stays 100% local. Zero execution means zero security risk.',
    },
    {
      stepNumber: '03',
      badge: 'Nebius Token Factory & NVIDIA Hardware',
      title: 'Empirical Latency & Cost Benchmarking',
      description: 'No synthetic guesswork. CascadeRouter executes actual test cases against candidate models hosted on Nebius Token Factory powered by NVIDIA H100 GPUs. It measures Time-To-First-Token (TTFT), token generation rates, and exact dollar costs with sub-millisecond precision.',
      diagram: (
        <div style={{ background: 'var(--paper)', padding: 14, borderRadius: 'var(--r-ctrl)', border: '1px solid var(--rule)', fontFamily: 'var(--font-mono)', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ color: 'var(--gain)' }}>⚡ Benchmarked on Nebius Token Factory (NVIDIA H100):</div>
          <div>• `Meta-Llama-3.1-8B-Instruct`:     ~78ms TTFT | \$0.03 input / \$0.09 output | 100% Pass</div>
          <div>• `nvidia/Llama-3.1-Nemotron-70B`: ~245ms TTFT | \$0.35 input / \$0.40 output | 100% Pass (Strict JSON)</div>
          <div>• `Meta-Llama-3.1-70B-Instruct`:    ~295ms TTFT | \$0.35 input / \$0.40 output | Baseline</div>
        </div>
      ),
      tip: 'Nebius Token Factory provides industry-leading throughput and ultra-low pricing on NVIDIA GPUs.',
    },
    {
      stepNumber: '04',
      badge: 'Atomic 1-Click Code Patching',
      title: 'Zero Hallucinations, Guaranteed Safety',
      description: 'CascadeRouter compares test pass rates. If a cheaper model passes 100% of validation assertions, it generates an atomic byte-span code diff. Before applying the change to your repository, it automatically saves a `.bak` copy for instant rollback.',
      diagram: (
        <div style={{ background: 'var(--paper)', padding: 14, borderRadius: 'var(--r-ctrl)', border: '1px solid var(--rule)', fontFamily: 'var(--font-mono)', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ color: 'var(--gain)' }}>✨ Verified Atomic Diff:</div>
          <div style={{ color: 'var(--loss)' }}>- model=&quot;gpt-4o&quot;</div>
          <div style={{ color: 'var(--gain)' }}>+ model=&quot;meta-llama/Meta-Llama-3.1-8B-Instruct&quot;</div>
          <div style={{ color: 'var(--muted)', fontSize: '10px' }}>Backed up: pipeline.py.bak | Verified 100% AST integrity</div>
        </div>
      ),
      tip: 'One click updates your production codebase safely with proven 85%+ inference cost reduction.',
    },
  ];

  const current = steps[currentStep];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight' && currentStep < steps.length - 1) setCurrentStep(s => s + 1);
      else if (e.key === 'ArrowLeft' && currentStep > 0) setCurrentStep(s => s - 1);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStep, onClose, steps.length]);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-dialog-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal-dialog modal-dialog-large">
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="pane-step-badge">Tour {current.stepNumber} of 04</span>
            <h2 id="tour-dialog-title" className="modal-title">
              How CascadeRouter Works
            </h2>
          </div>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close tour dialog" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div>
            <div style={{ display: 'inline-block', fontSize: '11px', fontWeight: 600, color: 'var(--navy)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              {current.badge}
            </div>
            <h3 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 700, color: 'var(--ink)' }}>
              {current.title}
            </h3>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted)', lineHeight: 1.6 }}>
              {current.description}
            </p>
          </div>

          {current.diagram}

          <div style={{ padding: '10px 14px', background: 'color-mix(in srgb, var(--gain) 8%, var(--sheet))', borderRadius: 'var(--r-ctrl)', border: '1px solid color-mix(in srgb, var(--gain) 20%, transparent)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--gain)', fontWeight: 700, fontSize: '14px' }}>💡</span>
            <span style={{ fontSize: '12px', color: 'var(--ink)' }}>{current.tip}</span>
          </div>

          {/* Stepper dots */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 4 }}>
            {steps.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setCurrentStep(i)}
                aria-label={`Jump to step ${i + 1}`}
                style={{
                  width: i === currentStep ? 24 : 8,
                  height: 8,
                  borderRadius: 4,
                  border: 'none',
                  background: i === currentStep ? 'var(--navy)' : 'var(--rule)',
                  cursor: 'pointer',
                  transition: 'all 140ms ease',
                }}
              />
            ))}
          </div>
        </div>

        <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
          <div>
            {currentStep > 0 && (
              <button type="button" className="btn-outline" onClick={() => setCurrentStep(s => s - 1)}>
                ← Previous
              </button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {currentStep < steps.length - 1 ? (
              <button type="button" className="btn-primary" onClick={() => setCurrentStep(s => s + 1)} style={{ minWidth: 100 }}>
                Next Step →
              </button>
            ) : (
              <>
                <button type="button" className="btn-outline" onClick={onClose}>
                  Done
                </button>
                {onLaunchDemo && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => {
                      onClose();
                      onLaunchDemo();
                    }}
                    style={{ minWidth: 140 }}
                  >
                    ⚡ Try 1-Click Demo
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


import { useEffect } from 'react';

export interface TermsModalProps {
  onClose: () => void;
}

export function TermsModal({ onClose }: TermsModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="terms-dialog-title"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal-dialog modal-dialog-large">
        <div className="modal-header">
          <h2 id="terms-dialog-title" className="modal-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
            Security Policy & Terms of Service
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close terms dialog" style={{ padding: '4px 8px' }}>
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ maxHeight: '65vh' }}>
          <div style={{ marginBottom: 18 }}>
            <h3 style={{ fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              1. Zero Code Execution Guarantee
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '13px' }}>
              CascadeRouter inspects your Python files strictly through static <strong>Abstract Syntax Tree (AST) parsing</strong>. Untrusted repository code is <strong>never imported, evaluated, or executed</strong>. No environment side-effects, arbitrary dependencies, or untrusted runtime behaviors can ever run on your host.
            </p>
          </div>

          <div style={{ marginBottom: 18, borderTop: '1px solid var(--rule)', paddingTop: 14 }}>
            <h3 style={{ fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              2. Data Sovereignty & Sovereign Inference
            </h3>
            <p style={{ margin: '0 0 8px', color: 'var(--muted)', fontSize: '13px' }}>
              Your codebase and intellectual property remain 100% local on your workstation. CascadeRouter never transmits repository files, git histories, or architecture diagrams to any external cloud service.
            </p>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '13px' }}>
              During benchmarking, only prompt strings and test assertions explicitly declared in local test case fixtures are submitted to the configured Nebius AI Studio inference endpoint (<code>api.studio.nebius.ai/v1</code>) for latency and token measurements.
            </p>
          </div>

          <div style={{ marginBottom: 18, borderTop: '1px solid var(--rule)', paddingTop: 14 }}>
            <h3 style={{ fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              3. Non-Destructive Atomic Patching & Rollback
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '13px' }}>
              Proposed patches are generated via deterministic byte-span replacement of model string literals only (e.g. replacing <code>&quot;gpt-4o&quot;</code> with <code>&quot;meta-llama/Meta-Llama-3.1-8B-Instruct&quot;</code>). Before writing any modification to disk, the original target file is backed up with a <code>.bak</code> extension, guaranteeing instant, risk-free rollback.
            </p>
          </div>

          <div style={{ borderTop: '1px solid var(--rule)', paddingTop: 14 }}>
            <h3 style={{ fontSize: 'var(--fs-base)', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              4. Open Source License & Attribution
            </h3>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '13px' }}>
              CascadeRouter is released under the <strong>MIT License</strong>. Built for the <strong>Nebius × NVIDIA Hackathon 2026</strong> to demonstrate autonomous FinOps optimization and latency minimization using Nebius Token Factory and NVIDIA H100 inference infrastructure.
            </p>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-primary" onClick={onClose} style={{ minWidth: 100 }}>
            I Understand & Agree
          </button>
        </div>
      </div>
    </div>
  );
}


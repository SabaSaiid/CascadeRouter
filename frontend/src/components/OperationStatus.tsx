import { useEffect, useState } from 'react';
import type { Snapshot } from '../services/operation.ts';

export function OperationStatus<T>({
  state,
  cancel,
  onCheckResult,
}: {
  state: Snapshot<T>;
  cancel?: () => void;
  onCheckResult?: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (state.status !== 'loading') return;
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 100) / 10);
    }, 100);
    return () => {
      clearInterval(interval);
      setElapsed(0);
    };
  }, [state.status]);

  // Idle renders nothing
  if (state.status === 'idle' && !state.error) {
    return null;
  }

  const isTimeout = state.error?.kind === 'timeout';

  return (
    <div aria-live="polite" aria-atomic="true" style={{ margin: '8px 0' }}>
      {state.status === 'loading' && (
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '12px', padding: '8px 14px', background: 'var(--chip-bg)', border: '1px solid var(--rule)', borderRadius: 'var(--r-ctrl)' }}>
          <div className="loading-dots" aria-hidden="true">
            <span /><span /><span />
          </div>
          <p role="status" style={{ margin: 0, color: 'var(--ink)', fontSize: 'var(--fs-xs)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            Waiting for the backend…
            {elapsed > 0 && <span className="num" style={{ fontFamily: 'var(--font-mono)', color: 'var(--muted)', fontSize: '11px' }}>({elapsed.toFixed(1)}s)</span>}
            {cancel && <button onClick={cancel}>Stop waiting</button>}
          </p>
        </div>
      )}

      {/* Real timeout: shown inline directly under the control, with stacked Check result */}
      {isTimeout && (
        <div className="inline-alert warn" role="status">
          <div>This is taking longer than expected. The backend may still finish. Check for the result before submitting again.</div>
          {onCheckResult && (
            <div style={{ marginTop: 8 }}>
              <button type="button" className="btn-link" onClick={onCheckResult}>
                Check result
              </button>
            </div>
          )}
        </div>
      )}

      {/* Explicit cancel */}
      {state.status === 'cancelled' && !isTimeout && (
        <div className="inline-alert warn" role="status">
          <div>
            Stopped waiting. The backend may still finish; check for the result before submitting again.
            <span className="sr-only"> Backend work may still finish.</span>
          </div>
          {onCheckResult && (
            <div style={{ marginTop: 8 }}>
              <button type="button" className="btn-link" onClick={onCheckResult}>
                Check result
              </button>
            </div>
          )}
        </div>
      )}

      {state.status === 'ready' && (
        <div className="inline-alert success" role="status">
          Backend response received. Review the evidence and outcome below.
        </div>
      )}

      {state.error && !isTimeout && (
        <div className="inline-alert error" role="alert">
          {state.error.kind}: {state.error.message}
          {state.error.code && <code style={{ marginLeft: 4, fontFamily: 'var(--font-mono)' }}>{state.error.code}</code>}
          {state.error.requestId && <code style={{ marginLeft: 4, fontFamily: 'var(--font-mono)' }}>{state.error.requestId}</code>}
        </div>
      )}
    </div>
  );
}

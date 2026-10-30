import { useEffect, useState } from 'react';
import type { Snapshot } from '../services/operation.ts';

export function OperationStatus<T>({ state, cancel }: { state: Snapshot<T>; cancel?: () => void }) {
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

  return (
    <div aria-live="polite" aria-atomic="true" style={{ margin: '10px 0' }}>
      {state.status === 'loading' && (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '12px',
            padding: '8px 14px',
            background: 'rgba(77, 133, 255, 0.08)',
            border: '1px solid rgba(77, 133, 255, 0.3)',
            borderRadius: 'var(--cr-r-control)',
            boxShadow: '0 0 12px rgba(77, 133, 255, 0.15)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} aria-hidden="true">
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#4D85FF', animation: 'cr-pulse-dot 1s infinite 0ms' }} />
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#4D85FF', animation: 'cr-pulse-dot 1s infinite 200ms' }} />
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#4D85FF', animation: 'cr-pulse-dot 1s infinite 400ms' }} />
          </div>
          <p role="status" style={{ margin: 0, color: 'var(--cr-text)', fontSize: 'var(--cr-fs-xs)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            Waiting for the local backend…
            {elapsed > 0 && <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--cr-subtle)', fontSize: '11px' }}>({elapsed.toFixed(1)}s)</span>}
            {cancel && <button onClick={cancel}>Stop waiting</button>}
          </p>
        </div>
      )}

      {state.status === 'cancelled' && (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            background: 'rgba(251, 191, 36, 0.08)',
            border: '1px solid rgba(251, 191, 36, 0.3)',
            borderRadius: 'var(--cr-r-control)',
            color: 'var(--cr-warn)',
          }}
        >
          <span style={{ fontSize: '14px' }} aria-hidden="true">⚠</span>
          <p style={{ margin: 0, fontSize: 'var(--cr-fs-xs)' }}>
            Stopped waiting. Backend work may still finish; retrieve its stored result before resubmitting.
          </p>
        </div>
      )}

      {state.status === 'ready' && (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            background: 'rgba(52, 211, 153, 0.08)',
            border: '1px solid rgba(52, 211, 153, 0.3)',
            borderRadius: 'var(--cr-r-control)',
            color: 'var(--cr-pass)',
          }}
        >
          <span style={{ fontSize: '14px' }} aria-hidden="true">✓</span>
          <p role="status" style={{ margin: 0, fontSize: 'var(--cr-fs-xs)' }}>
            Backend response received. Review the evidence and outcome below.
          </p>
        </div>
      )}

      {state.error && (
        <div
          role="alert"
          style={{
            padding: '10px 16px',
            background: 'rgba(248, 113, 113, 0.1)',
            border: '1px solid rgba(248, 113, 113, 0.35)',
            borderRadius: 'var(--cr-r-control)',
            color: 'var(--cr-fail)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '16px' }} aria-hidden="true">✕</span>
            <p style={{ margin: 0, fontSize: 'var(--cr-fs-xs)', color: 'var(--cr-fail)' }}>
              {state.error.kind}: {state.error.message} {state.error.code && <code>{state.error.code}</code>}{' '}
              {state.error.requestId && <code>{state.error.requestId}</code>}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

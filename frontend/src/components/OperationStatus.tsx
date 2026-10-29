import type { Snapshot } from '../services/operation.ts';
export function OperationStatus<T>({ state, cancel }: { state: Snapshot<T>; cancel?: () => void }) {
  return <div aria-live="polite" aria-atomic="true">
    {state.status === 'loading' && <p role="status">Waiting for the local backend… {cancel && <button onClick={cancel}>Stop waiting</button>}</p>}
    {state.status === 'cancelled' && <p>Stopped waiting. Backend work may still finish; retrieve its stored result before resubmitting.</p>}
    {state.error && <p role="alert">{state.error.kind}: {state.error.message} {state.error.code && <code>{state.error.code}</code>} {state.error.requestId && <code>{state.error.requestId}</code>}</p>}
  </div>;
}

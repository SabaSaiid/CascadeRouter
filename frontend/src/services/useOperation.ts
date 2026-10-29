import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { Operation } from './operation.ts';
export function useOperation<T>() {
  const operation = useMemo(() => new Operation<T>(), []);
  const state = useSyncExternalStore(operation.subscribe, operation.snapshot, operation.snapshot);
  useEffect(() => () => operation.cancel(), [operation]);
  return [state, operation] as const;
}

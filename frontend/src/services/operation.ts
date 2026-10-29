import { failure } from './transport.ts';
import type { ApiFailure } from './transport.ts';
export interface Snapshot<T> { status: 'idle' | 'loading' | 'ready' | 'error' | 'cancelled'; data?: T; error?: ApiFailure }
// Generations prevent late responses publishing after replacement or unmount.
export class Operation<T> {
  private state: Snapshot<T> = { status: 'idle' };
  private listeners = new Set<() => void>();
  private controller?: AbortController;
  private generation = 0;
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(state: Snapshot<T>) { this.state = state; for (const listener of this.listeners) listener(); }
  cancel = () => { this.generation++; this.controller?.abort(); this.controller = undefined; this.publish({ ...this.state, status: 'cancelled', error: undefined }); };
  reset = () => { this.cancel(); this.publish({ status: 'idle' }); };
  async run(task: (signal: AbortSignal) => Promise<T>, replace = false, retain = false): Promise<T | undefined> {
    if (this.state.status === 'loading' && !replace) return;
    this.controller?.abort(); const controller = new AbortController(); this.controller = controller;
    const generation = ++this.generation;
    this.publish({ status: 'loading', data: retain ? this.state.data : undefined });
    try {
      const data = await task(controller.signal);
      if (generation !== this.generation || controller.signal.aborted) return;
      this.publish({ status: 'ready', data }); return data;
    } catch (error) {
      if (generation === this.generation) { const safe = failure(error); this.publish({ status: safe.kind === 'cancelled' ? 'cancelled' : 'error', data: retain ? this.state.data : undefined, error: safe }); }
    } finally { if (generation === this.generation) this.controller = undefined; }
  }
}

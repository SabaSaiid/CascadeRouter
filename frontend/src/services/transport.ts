import { errorMessages } from './contracts.ts';
import type { ContractTypes } from './contracts.ts';
import { parseContract } from './contractCheck.ts';

export type FailureKind = 'configuration' | 'unavailable' | 'timeout' | 'cancelled' | 'authorization' | 'validation' | 'rate_limit' | 'conflict' | 'not_found' | 'server' | 'malformed';
const messages: Record<FailureKind, string> = {
  configuration: 'Configure an explicit local HTTP backend address.', unavailable: 'The local backend is unavailable. Check its configuration and retry.',
  timeout: 'The local request timed out. Its backend operation may still finish.', cancelled: 'Stopped waiting. This does not terminate backend work.',
  authorization: 'The backend denied access under its current repository policy.', validation: 'The backend rejected the request. Check the supplied identifiers and configuration.',
  rate_limit: 'The backend is at its request or work capacity. Wait before retrying.', conflict: 'Stored evidence or source no longer matches. Refresh or rescan before continuing.',
  not_found: 'The requested stored record was not found.', server: 'The backend failed to complete the request. Check local service health.',
  malformed: 'The backend returned an invalid or unsupported response. No result was substituted.',
};
export class ApiFailure extends Error {
  readonly kind: FailureKind;
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;
  constructor(kind: FailureKind, status?: number, code?: string, requestId?: string) {
    super(messages[kind]); this.name = 'ApiFailure'; this.kind = kind; this.status = status;
    this.code = code && Object.hasOwn(errorMessages, code) ? code : undefined;
    this.requestId = requestId && /^req_[0-9a-f]{32}$/.test(requestId) ? requestId : undefined;
  }
}
export const failure = (error: unknown) => error instanceof ApiFailure ? error : new ApiFailure('unavailable');

export function localBase(value = 'http://127.0.0.1:8000'): string {
  try {
    const url = new URL(value);
    if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
      || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error();
    return url.origin;
  } catch { throw new ApiFailure('configuration'); }
}

export class LocalTransport {
  readonly base: string;
  readonly fetcher: typeof fetch;
  readonly timeoutMs: number;
  readonly maxBytes: number;
  constructor(base?: string, fetcher: typeof fetch = globalThis.fetch, timeoutMs = 45_000, maxBytes = 16 * 1024 * 1024) {
    this.base = localBase(base); this.fetcher = fetcher; this.timeoutMs = timeoutMs; this.maxBytes = maxBytes;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 120_000 || !Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > 64 * 1024 * 1024) throw new ApiFailure('configuration');
  }
  async request<K extends keyof ContractTypes>(path: string, model: K, options: { method?: 'GET' | 'POST'; body?: unknown; signal?: AbortSignal } = {}): Promise<ContractTypes[K]> {
    if (!/^\/api\/[A-Za-z0-9_/-]+$/.test(path) || path.includes('//') || path.includes('..')) throw new ApiFailure('validation');
    const controller = new AbortController(); let timedOut = false;
    const cancel = () => controller.abort();
    if (options.signal?.aborted) throw new ApiFailure('cancelled');
    options.signal?.addEventListener('abort', cancel, { once: true });
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    try {
      const response = await this.fetcher(this.base + path, { method: options.method ?? 'GET', body: options.body === undefined ? undefined : JSON.stringify(options.body),
        headers: options.body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
        signal: controller.signal, credentials: 'omit', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer' });
      const reader = response.body?.getReader(); const chunks: Uint8Array[] = []; let size = 0;
      if (reader) {
        try {
          for (;;) { const part = await reader.read(); if (part.done) break; size += part.value.byteLength;
            if (size > this.maxBytes) { await reader.cancel(); throw new ApiFailure('malformed'); } chunks.push(part.value); }
        } finally { reader.releaseLock(); }
      }
      const bytes = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      let data: unknown;
      try { data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
      catch { if (response.ok) throw new ApiFailure('malformed'); }
      if (!response.ok) {
        const kind: FailureKind = [401, 403].includes(response.status) ? 'authorization' : response.status === 404 ? 'not_found' : response.status === 429 ? 'rate_limit'
          : response.status === 409 ? 'conflict' : response.status === 503 ? 'unavailable' : response.status >= 500 ? 'server' : 'validation';
        const obj = data !== null && typeof data === 'object' ? data as Record<string, unknown> : {};
        throw new ApiFailure(kind, response.status, typeof obj.code === 'string' ? obj.code : undefined, typeof obj.request_id === 'string' ? obj.request_id : undefined);
      }
      if (controller.signal.aborted) throw new ApiFailure(timedOut ? 'timeout' : 'cancelled');
      if (!response.headers.get('content-type')?.toLowerCase().startsWith('application/json')) throw new ApiFailure('malformed');
      try { return parseContract(model, data); } catch { throw new ApiFailure('malformed'); }
    } catch (error) {
      if (controller.signal.aborted) throw new ApiFailure(timedOut ? 'timeout' : 'cancelled');
      throw error instanceof ApiFailure ? error : new ApiFailure('unavailable');
    } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', cancel); }
  }
}

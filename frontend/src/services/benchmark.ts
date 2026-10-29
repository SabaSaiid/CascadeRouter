import type { BenchmarkRequest, Job, Backend_MetricPopulation as Population } from './contracts.ts';
export const terminal = (status: Job['status']) => ['complete', 'cancelled', 'error', 'interrupted'].includes(status);
export class SubmissionKeys {
  private keys = new Map<string, string>();
  forRequest(request: BenchmarkRequest, makeKey = () => 'ui_' + crypto.randomUUID().replaceAll('-', '')) {
    const identity = JSON.stringify(request); let key = this.keys.get(identity);
    if (!key) { key = makeKey(); this.keys.set(identity, key); } return key;
  }
}
export function population(value?: Population | null): string {
  if (!value || value.availability !== 'available') return `Unavailable${value?.reason ? ` (${value.reason})` : ''}`;
  if (value.unit === 'USD') return value.total_usd == null ? 'Unavailable' : `${value.total_usd} USD (${value.sample_count} samples)`;
  if (value.unit === 'tokens') return value.total_tokens == null ? 'Unavailable' : `${value.total_tokens} tokens (${value.sample_count} samples)`;
  return value.mean == null ? 'Unavailable' : `${value.mean} ms mean; ${value.minimum}–${value.maximum} ms (${value.sample_count} samples)`;
}
export const measured = (value?: { availability: string; value?: number | null } | null) => value?.availability === 'available' && value.value != null ? String(value.value) : 'Unavailable';

import { LocalTransport, ApiFailure } from './transport.ts';
import { parseContract } from './contractCheck.ts';
import type { BenchmarkRequest, OptimizationRequest, PatchRequest } from './contracts.ts';

const id = (value: string, prefix: string, length: number) => {
  if (!new RegExp(`^${prefix}_[0-9a-f]{${length}}$`).test(value)) throw new ApiFailure('validation');
  return value;
};
function body<K extends 'ScanRequest' | 'BenchmarkRequest' | 'OptimizationRequest' | 'PatchRequest'>(model: K, value: unknown) {
  try { return parseContract(model, value); } catch { throw new ApiFailure('validation'); }
}
export class ApiClient {
  readonly transport: LocalTransport;
  constructor(transport = new LocalTransport()) { this.transport = transport; }
  health(signal?: AbortSignal) { return this.transport.request('/api/health', 'Health', { signal }); }
  async scan(repository_path: string, signal?: AbortSignal) { return this.transport.request('/api/scan', 'Scan', { method: 'POST', body: body('ScanRequest', { repository_path }), signal }); }
  async analysis(value: string, signal?: AbortSignal) {
    const result = await this.transport.request(`/api/analyses/${id(value, 'analysis', 32)}`, 'Scan', { signal });
    if (result.analysis_id !== value) throw new ApiFailure('malformed'); return result;
  }
  async benchmark(value: BenchmarkRequest, signal?: AbortSignal) { return this.transport.request('/api/benchmark', 'JobAccepted', { method: 'POST', body: body('BenchmarkRequest', value), signal }); }
  async run(value: string, signal?: AbortSignal, cancel = false) {
    const result = await this.transport.request(`/api/runs/${id(value, 'run', 32)}${cancel ? '/cancel' : ''}`, 'Job', { method: cancel ? 'POST' : 'GET', signal });
    if (result.run_id !== value) throw new ApiFailure('malformed'); return result;
  }
  async optimize(value: OptimizationRequest, signal?: AbortSignal) {
    const result = await this.transport.request('/api/optimize', 'Optimization', { method: 'POST', body: body('OptimizationRequest', value), signal });
    if (result.result.run_id !== value.run_id || result.result.plan.analysis_id !== value.analysis_id) throw new ApiFailure('malformed'); return result;
  }
  async createPatch(value: PatchRequest, signal?: AbortSignal) { return this.transport.request('/api/patches', 'PatchAccepted', { method: 'POST', body: body('PatchRequest', value), signal }); }
  async patch(value: string, signal?: AbortSignal) {
    const result = await this.transport.request(`/api/patches/${id(value, 'patch', 64)}`, 'Patch', { signal });
    if (result.manifest.patch_id !== value) throw new ApiFailure('malformed'); return result;
  }
  async validate(value: string, signal?: AbortSignal) {
    const result = await this.transport.request(`/api/patches/${id(value, 'patch', 64)}/validate`, 'Validation', { method: 'POST', signal });
    if (result.result.patch_id !== value) throw new ApiFailure('malformed'); return result;
  }
  async validation(value: string, signal?: AbortSignal) {
    const result = await this.transport.request(`/api/patch-validations/${id(value, 'validation', 64)}`, 'Validation', { signal });
    if (result.validation_id !== value) throw new ApiFailure('malformed'); return result;
  }
}

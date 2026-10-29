import { schemas, modelNames } from './contracts.ts';
import type { ContractTypes } from './contracts.ts';

type Obj = Record<string, any>;
const object = (value: unknown): value is Obj => value !== null && typeof value === 'object' && !Array.isArray(value);
const unique = (values: readonly unknown[]) => new Set(values).size === values.length;
const relative = (value: string) => !value.startsWith('/') && !value.includes('\\') && !value.includes(':') && !value.split('/').some(v => v === '..' || v === '.' || !v);

// This interprets only first-party generated schema data, never executable validators.
function shape(value: unknown, schema: Obj, budget: { left: number }, depth = 0): boolean {
  if (--budget.left < 0 || depth > 64) return false;
  if (schema.$ref) return shape(value, schemas[schema.$ref.split('/').pop()] as Obj, budget, depth + 1);
  if (schema.anyOf || schema.oneOf) return (schema.anyOf ?? schema.oneOf).some((s: Obj) => shape(value, s, budget, depth + 1));
  if (schema.allOf && !schema.allOf.every((s: Obj) => shape(value, s, budget, depth + 1))) return false;
  if ('const' in schema && value !== schema.const) return false;
  if (schema.enum && !schema.enum.includes(value)) return false;
  if (schema.type === 'null') return value === null;
  if (schema.type === 'boolean') return typeof value === 'boolean';
  if (schema.type === 'string') {
    if (typeof value !== 'string') return false;
    const length = [...value].length;
    if (length < (schema.minLength ?? 0) || length > (schema.maxLength ?? Infinity)) return false;
    if (schema.pattern) { const match = new RegExp(schema.pattern).exec(value); if (!match || match[0] !== value) return false; }
    if (schema.format === 'date-time' && (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value)))) return false;
  }
  if (schema.type === 'number' || schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isFinite(value) || (schema.type === 'integer' && !Number.isSafeInteger(value))) return false;
    if (value < (schema.minimum ?? -Infinity) || value > (schema.maximum ?? Infinity)) return false;
    if (schema.exclusiveMinimum != null && value <= schema.exclusiveMinimum) return false;
    if (schema.exclusiveMaximum != null && value >= schema.exclusiveMaximum) return false;
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value) || value.length < (schema.minItems ?? 0) || value.length > (schema.maxItems ?? Infinity)) return false;
    if (!value.every((v, i) => shape(v, schema.prefixItems?.[i] ?? schema.items ?? {}, budget, depth + 1))) return false;
  }
  if (schema.type === 'object') {
    if (!object(value) || (schema.required ?? []).some((key: string) => !Object.hasOwn(value, key))) return false;
    for (const [key, v] of Object.entries(value)) {
      const rule = schema.properties?.[key] ?? schema.additionalProperties;
      if (rule === false || rule === undefined) return false;
      if (rule !== true && !shape(v, rule, budget, depth + 1)) return false;
    }
  }
  return true;
}

function evidence(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(evidence);
  if (!object(value)) return true;
  if ('file_path' in value && !relative(value.file_path)) return false;
  if ('availability' in value && 'value' in value && (value.availability === 'available') !== (value.value != null)) return false;
  if ('availability' in value && ('amount_usd' in value || 'pricing_digest' in value) && (value.availability === 'available') !== (value.amount_usd != null)) return false;
  if ('sample_count' in value && 'unit' in value) {
    if (value.availability === 'available' && (value.sample_count === 0 || value.reason != null)) return false;
    if (value.availability === 'unavailable' && [value.mean, value.minimum, value.maximum, value.total_tokens, value.total_usd].some(v => v != null)) return false;
    if (value.availability === 'available' && (value.unit === 'ms' ? [value.mean, value.minimum, value.maximum].some(v => v == null) : value[value.unit === 'USD' ? 'total_usd' : 'total_tokens'] == null)) return false;
  }
  return Object.values(value).every(evidence);
}

function semantics(name: keyof ContractTypes, v: Obj): boolean {
  if (!evidence(v)) return false;
  if (name === 'Scan') {
    const ids = v.nodes.map((n: Obj) => n.node_id);
    if (!unique(ids) || v.complete !== (v.scan_complete && v.graph_complete) || v.scanned_files_count > v.discovered_files_count) return false;
    if (!v.graph_edges.every(([a, b]: string[]) => a !== b && ids.includes(a) && ids.includes(b))) return false;
    if (!unique(v.graph_edges.map((e: string[]) => e.join(':')))) return false;
  }
  if (name === 'Job') {
    if (v.progress.completed_units !== v.measurements.length || v.progress.completed_units > v.progress.total_units) return false;
    if (v.status === 'complete' && (v.result == null || v.progress.completed_units !== v.progress.total_units)) return false;
    if (!v.measurements.every((m: Obj) => m.provenance === v.plan.provenance && v.plan.node_ids.includes(m.node_id))) return false;
    if (v.result?.metrics && (v.result.metrics.processed_units !== v.measurements.length || v.result.metrics.processing_complete !== (v.progress.completed_units === v.progress.total_units))) return false;
  }
  if (name === 'Optimization') {
    if (v.result.provenance !== v.result.plan.provenance) return false;
    for (const d of v.result.decisions) {
      const selected = ['recommended', 'baseline_retained'].includes(d.status);
      if (selected !== (d.selected_model_id != null) || (!selected && d.recorded_savings_usd != null)) return false;
    }
    if (v.policy.status === 'unavailable' && (v.policy.yaml_content != null || v.policy.route_count !== 0)) return false;
  }
  if (name === 'Patch') {
    if (v.manifest.patch_format !== 'literal-spans.v1' || (v.manifest.files.length > 0) !== v.review_diff.startsWith('literal-spans.v1\n')) return false;
  }
  if (name === 'Validation') {
    const r = v.result;
    const states: Obj = {
      statically_validated: ['validated', 'valid', 'available', 'verified', true],
      partial_proposal: ['partial', 'valid', 'available', 'verified', false],
      no_editable_files: ['unavailable', 'valid', 'available', 'verified', false],
      proposal_mismatch: ['invalid', 'invalid', 'available', 'verified', false],
      file_validation_failed: ['invalid', 'valid', 'available', 'verified', false],
      file_validation_unavailable: ['unavailable', 'valid', 'available', 'verified', false],
      source_changed: ['stale', 'valid', 'available', 'stale', false],
      source_evidence_unavailable: ['unavailable', 'valid', 'unavailable', 'not_verified', false],
      resource_limit: ['unavailable', 'valid', 'available', 'not_verified', false],
    };
    if (JSON.stringify([r.status, r.structure, r.source_evidence, r.source_identity, r.complete]) !== JSON.stringify(states[r.reason])) return false;
    if (r.omitted_nodes !== (r.omissions ?? []).length) return false;
    if (['validated', 'partial'].includes(r.status) && (!(r.files.length > 0) || r.files.some((f: Obj) => f.reason !== 'checked') || (r.omitted_nodes === 0) !== r.complete)) return false;
    const files: Obj = { checked: ['valid', 'constructed', 'passed', 'verified'], invalid_spans: ['invalid', 'not_checked', 'not_checked', 'not_checked'],
      candidate_failed: ['valid', 'failed', 'not_checked', 'not_checked'], candidate_digest_mismatch: ['valid', 'constructed', 'not_checked', 'not_checked'],
      syntax_error: ['valid', 'constructed', 'failed', 'not_checked'], ast_mismatch: ['valid', 'constructed', 'passed', 'failed'],
      resource_limit: ['not_checked', 'not_checked', 'not_checked', 'not_checked'], unsupported_encoding: Array(4).fill('not_applicable') };
    if (!r.files.every((f: Obj) => JSON.stringify([f.spans, f.candidate, f.syntax, f.ast_preservation]) === JSON.stringify(files[f.reason])
      && (f.candidate_digest != null) === (f.candidate === 'constructed') && (f.diagnostic != null) === (f.reason === 'syntax_error'))) return false;
  }
  return true;
}

export function parseContract<K extends keyof ContractTypes>(name: K, value: unknown): ContractTypes[K] {
  if (!shape(value, schemas[modelNames[name]] as Obj, { left: 2_000_000 }) || !object(value) || !semantics(name, value)) throw new Error('invalid_contract');
  return value as ContractTypes[K];
}

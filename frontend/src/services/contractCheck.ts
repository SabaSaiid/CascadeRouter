import { schemas, modelNames } from './contracts.ts';
import type { ContractTypes } from './contracts.ts';
import { acyclic } from './graph.ts';

type Obj = Record<string, any>;
const object = (value: unknown): value is Obj => value !== null && typeof value === 'object' && !Array.isArray(value);
const unique = (values: readonly unknown[]) => new Set(values).size === values.length;
const relative = (value: string) => !value.startsWith('/') && !value.includes('\\') && !value.includes(':') && !value.split('/').some(v => v === '..' || v === '.' || !v);
const money = (value: unknown) => typeof value === 'string' && /^(?:0|[1-9][0-9]{0,23})(?:\.[0-9]{1,18})?$/.test(value);
const rate = (value: unknown) => typeof value === 'string' && /^(?:0(?:\.[0-9]{1,18})?|1(?:\.0{1,18})?)$/.test(value);

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
      const rule = schema.properties && Object.hasOwn(schema.properties, key) ? schema.properties[key] : schema.additionalProperties;
      if (rule === false || rule === undefined) return false;
      if (rule !== true && !shape(v, rule, budget, depth + 1)) return false;
    }
  }
  if (schema.type === 'object' && schema.properties?.availability && schema.properties?.value
    && ((value as Obj).availability === 'available') !== ((value as Obj).value != null)) return false;
  if (schema.type === 'object' && schema.properties?.amount_usd) {
    const cost = value as Obj;
    if (cost.availability === 'available' ? cost.amount_usd == null || cost.pricing_reference == null || cost.pricing_digest == null || cost.reason != null
      : cost.amount_usd != null || cost.pricing_reference != null || cost.pricing_digest != null || cost.reason == null) return false;
  }
  return true;
}

function evidence(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(evidence);
  if (!object(value)) return true;
  for (const key of ['amount_usd', 'total_usd', 'cost_total_usd', 'recorded_savings_usd']) if (value[key] != null && !money(value[key])) return false;
  for (const key of ['quality_threshold', 'quality_pass_rate']) if (value[key] != null && !rate(value[key])) return false;
  if ('file_path' in value && !relative(value.file_path)) return false;
  if ('availability' in value && 'value' in value && (value.availability === 'available') !== (value.value != null)) return false;
  if ('availability' in value && ('amount_usd' in value || 'pricing_digest' in value) && (value.availability === 'available') !== (value.amount_usd != null)) return false;
  if ('sample_count' in value && 'unit' in value) {
    if (value.availability === 'available' && (value.sample_count === 0 || value.reason != null)) return false;
    if (value.availability === 'unavailable' && [value.mean, value.minimum, value.maximum, value.total_tokens, value.total_usd].some(v => v != null)) return false;
    if (value.availability === 'available' && (value.unit === 'ms' ? [value.mean, value.minimum, value.maximum].some(v => v == null) : value[value.unit === 'USD' ? 'total_usd' : 'total_tokens'] == null)) return false;
    if (value.availability === 'unavailable' && (value.reason == null || (value.reason === 'empty_population') !== (value.sample_count === 0))) return false;
  }
  if ('planned_units' in value && 'evaluated_units' in value) {
    if (value.processed_units > value.planned_units || value.valid_recorded_outputs > value.processed_units || value.evaluated_units > value.processed_units
      || value.passed + value.failed + value.skipped + value.inconclusive + value.not_run !== value.processed_units
      || value.processing_complete !== (value.processed_units === value.planned_units) || value.evaluation_complete !== (value.passed + value.failed === value.planned_units)) return false;
    for (const [key, unit] of [['latency_ms', 'ms'], ['ttft_ms', 'ms'], ['input_tokens', 'tokens'], ['output_tokens', 'tokens'], ['cost_usd', 'USD']]) {
      if (value[key].unit !== unit || value[key].sample_count > value.processed_units) return false;
    }
  }
  if ('evaluation_status' in value && 'quality_score' in value && ['unavailable', 'not_run', 'skipped'].includes(value.evaluation_status) && value.quality_score != null) return false;
  return Object.values(value).every(evidence);
}

function semantics(name: keyof ContractTypes, v: Obj): boolean {
  if (!evidence(v)) return false;
  if (name === 'Scan') {
    const ids = v.nodes.map((n: Obj) => n.node_id);
    if (!unique(ids) || v.complete !== (v.scan_complete && v.graph_complete) || v.scanned_files_count > v.discovered_files_count) return false;
    if (!v.graph_edges.every(([a, b]: string[]) => a !== b && ids.includes(a) && ids.includes(b))) return false;
    if (!unique(v.graph_edges.map((e: string[]) => e.join(':')))) return false;
    if (!acyclic(ids, v.graph_edges)) return false;
  }
  if (name === 'Job') {
    if (v.progress.completed_units !== v.measurements.length || v.progress.completed_units > v.progress.total_units) return false;
    if (v.status === 'complete' && (v.result == null || v.progress.completed_units !== v.progress.total_units)) return false;
    if (!v.measurements.every((m: Obj) => m.provenance === v.plan.provenance && v.plan.node_ids.includes(m.node_id))) return false;
    const keys = v.measurements.map((m: Obj) => JSON.stringify([m.node_id, m.model_id, m.case_id]));
    if (!unique(keys) || v.progress.total_units !== v.plan.node_ids.length * v.plan.models.length * v.plan.case_ids.length
      || !v.measurements.every((m: Obj) => v.plan.models.some((model: Obj) => model.identifier === m.model_id) && v.plan.case_ids.includes(m.case_id))) return false;
    if (['complete', 'cancelled', 'error', 'interrupted'].includes(v.status) !== (v.finished_at != null) || (v.status === 'complete') !== (v.result != null)) return false;
    if (v.result && v.result.provenance !== v.plan.provenance) return false;
    if (v.result?.metrics && (v.result.metrics.processed_units !== v.measurements.length || v.result.metrics.processing_complete !== (v.progress.completed_units === v.progress.total_units))) return false;
    if (Date.parse(v.updated_at) < Date.parse(v.created_at) || Date.parse(v.deadline_at) <= Date.parse(v.created_at)) return false;
    if (['error', 'interrupted'].includes(v.status) !== (v.error != null) || (v.status === 'queued' && v.measurements.length !== 0)) return false;
    if (v.measurements.some((m: Obj) => m.evaluation != null && m.evaluation.status !== m.evaluation_status)) return false;
    if (v.result) {
      const statuses = new Set(v.measurements.map((m: Obj) => m.evaluation_status));
      const expected = statuses.has('failed') ? 'failed' : statuses.size === 1 && statuses.has('passed') ? 'passed' : 'inconclusive';
      if (v.result.evaluation_status !== expected) return false;
      const metrics = v.result.metrics;
      if (metrics) {
        if (metrics.provenance !== v.plan.provenance || metrics.planned_units !== v.progress.total_units || metrics.planned_cases !== v.plan.case_ids.length
          || metrics.valid_recorded_outputs !== v.measurements.filter((m: Obj) => m.output_available === true).length
          || metrics.evaluated_units !== v.measurements.filter((m: Obj) => (m.evaluation?.checks_ran?.length ?? 0) > 0).length) return false;
        for (const state of ['passed', 'failed', 'skipped', 'inconclusive', 'not_run']) {
          if (metrics[state] !== v.measurements.filter((m: Obj) => (m.evaluation_status === 'unavailable' ? 'not_run' : m.evaluation_status) === state).length) return false;
        }
      }
    }
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

import { fixture } from './fixtures.mjs';
// Mutated test-only observations exercise UI outcomes, never backend authorization.
export function reportFor(status) {
  const report = fixture('validation'); const r = report.result;
  if (status === 'validated') return report;
  r.status = status; r.complete = false;
  if (status === 'partial') { r.reason = 'partial_proposal'; r.omitted_nodes = 1; r.omissions = [{node_id:'llm_'+'a'.repeat(24), reason:'model_unresolved'}]; }
  if (status === 'stale') { r.reason = 'source_changed'; r.source_identity = 'stale'; r.files = []; }
  if (status === 'unavailable') { r.reason = 'source_evidence_unavailable'; r.source_evidence = 'unavailable'; r.source_identity = 'not_verified'; r.files = []; }
  if (status === 'invalid') { r.reason = 'file_validation_failed'; r.files[0].syntax = 'failed'; r.files[0].ast_preservation = 'not_checked'; r.files[0].reason = 'syntax_error'; r.files[0].diagnostic = {code:'candidate_syntax_error',line_number:3,column_number:4}; }
  return report;
}

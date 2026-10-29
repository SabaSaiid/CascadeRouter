import type { Optimization, Scan, Validation } from './contracts.ts';
export const canPropose = (analysis?: Scan, value?: Optimization) => !!analysis && !!value?.optimization_id
  && value.result.provenance === 'recorded' && value.result.plan.analysis_id === analysis.analysis_id
  && !!value.result.approval_manifest_digest && !!value.result.recording_dataset_digest && value.policy.route_count > 0;
const outcome = {
  validated: 'All included files passed static checks; no requested nodes were omitted.',
  partial: 'Included files passed static checks; requested nodes were omitted. This is not a complete proposal.',
  invalid: 'A proposal, span, candidate, syntax or AST check failed.',
  stale: 'Source did not match the retained source manifest at the observation time. Rescan before creating a new proposal.',
  unavailable: 'The required evidence, supported edits or validation resources were unavailable.',
};
export function validationView(report: Validation, historical: boolean) {
  return { outcome: outcome[report.result.status],
    freshness: historical ? 'Historical observation — this retrieval does not check current source freshness. Validate the proposal again for a new observation.'
      : 'Point-in-time observation — source may change after this check. Validation does not lock the repository.',
    limitation: 'Static syntax and AST checks do not prove behavior, model compatibility, runtime safety or benchmark quality. No application tests ran and no patch was applied.' };
}

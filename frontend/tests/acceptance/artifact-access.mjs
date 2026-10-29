import assert from 'node:assert/strict';
import { acceptance } from './client.mjs';
await acceptance(async ({ api, input, status, mark }) => {
  const denied = async (label, action) => { mark(label); await assert.rejects(action, error => error.kind === input.kind && error.status === input.status); status(input.status); };
  const proposal = { analysis_id: input.analysis_id, optimization_id: input.optimization_id };
  if (input.kind === 'authorization') {
    await denied('scan scope', () => api.scan(input.repository));
    await denied('analysis scope', () => api.analysis(input.analysis_id));
    await denied('run scope', () => api.run(input.run_id));
    await denied('cancellation scope', () => api.run(input.run_id, undefined, true));
    await denied('optimizer scope', () => api.optimize({ analysis_id: input.analysis_id, run_id: input.run_id, case_set: input.case_set, evaluation_profile: input.evaluation_profile }));
  }
  await denied('proposal creation authority', () => api.createPatch(proposal));
  await denied('proposal review authority', () => api.patch(input.patch_id));
  await denied('static validation authority', () => api.validate(input.patch_id));
  await denied('historical observation authority', () => api.validation(input.validation_id));
  return { denied: input.kind === 'authorization' ? 9 : 4 };
});

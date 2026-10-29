// Invoked by pytest against its real, explicitly configured loopback backend.
import assert from 'node:assert/strict';
import { ApiClient } from '../src/services/api.ts';
import { LocalTransport } from '../src/services/transport.ts';
const [base, repository] = process.argv.slice(2);
const api = new ApiClient(new LocalTransport(base));
let stage = 'health';
try {
assert.equal((await api.health()).scan_available, true);
stage = 'scan';
const scan = await api.scan(repository);
assert.equal(scan.data_source, 'live'); assert.equal(scan.complete, true); assert.equal(scan.nodes.length, 1);
stage = 'retrieval'; assert.deepEqual(await api.analysis(scan.analysis_id), scan);
stage = 'missing analysis';
await assert.rejects(api.analysis('analysis_'+'f'.repeat(32)), e=>e.kind==='not_found');
stage = 'benchmark unavailable'; await assert.rejects(api.benchmark({analysis_id:scan.analysis_id,node_ids:[scan.nodes[0].node_id],baseline_model_id:'local/baseline',candidate_model_ids:['local/candidate'],benchmark_case_set_id:'operator_cases',evaluation_profile_id:'operator_profile'}), e=>e.kind==='unavailable');
stage = 'missing proposal';
await assert.rejects(api.validate('patch_'+'f'.repeat(32)), e=>e.kind==='not_found');
stage = 'missing historical report';
await assert.rejects(api.validation('validation_'+'f'.repeat(64)), e=>e.kind==='not_found');
process.stdout.write('Real local backend: health, scan, retrieval, not-found and unavailable gates verified.\n');
} catch (error) { process.stderr.write(`Local contract stage: ${stage}; ${error.kind || error.code || error.name}\n`); process.exitCode = 1; }

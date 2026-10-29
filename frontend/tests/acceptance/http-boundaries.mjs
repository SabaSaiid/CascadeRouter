import assert from 'node:assert/strict';
import { acceptance } from './client.mjs';
import { parseContract } from '../../src/services/contractCheck.ts';
await acceptance(async ({ base, input, api, mark }) => {
  const check = async (path, options, expected, code) => {
    const response = await fetch(base + path, { ...options, redirect: 'error', credentials: 'omit' });
    assert.equal(response.status, expected); const raw = await response.text(); const value = parseContract('ApiErrorResponse', JSON.parse(raw));
    assert.equal(value.code, code); assert.ok(!raw.includes('PRIVATE_ACCEPTANCE') && !raw.includes(input.repository));
    return value;
  };
  if (input.rate) {
    mark('peer rate accounting');
    for (let i=0; i<4; i++) await check('/api/analyses/analysis_'+'f'.repeat(32), { headers: { 'X-Forwarded-For': `198.51.100.${i+1}`, 'X-Real-IP': `198.51.100.${i+1}` } }, i<3 ? 404 : 429, i<3 ? 'not_found' : 'capacity_exceeded');
  } else {
    mark('origin policy'); await check('/api/scan', { method:'POST', headers:{ Origin:'https://attacker.invalid' }, body:'PRIVATE_ACCEPTANCE' }, 422, 'invalid_request');
    mark('malformed body'); await check('/api/scan', { method:'POST', body:'{"PRIVATE_ACCEPTANCE":', headers:{'Content-Type':'application/json'} }, 422, 'invalid_request');
    mark('actual chunked body bound');
    const stream=new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('x'.repeat(200))); c.enqueue(new TextEncoder().encode('y'.repeat(200))); c.close(); } });
    await check('/api/scan', { method:'POST', body:stream, duplex:'half', headers:{'Content-Type':'application/json'} }, 413, 'request_too_large');
    mark('repository escape'); await assert.rejects(api.scan(input.outside), e=>e.kind==='authorization' && e.status===403);
  }
  mark('health remains truthful'); assert.equal((await api.health()).scan_available, true);
  return { checked:true };
});

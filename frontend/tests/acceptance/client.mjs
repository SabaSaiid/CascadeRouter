import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ApiClient } from '../../src/services/api.ts';
import { LocalTransport } from '../../src/services/transport.ts';
export async function acceptance(work) {
  let stage = 'setup';
  try {
    const base = process.argv[2]; const input = JSON.parse(readFileSync(0, 'utf8')); const calls = [];
    const api = new ApiClient(new LocalTransport(base, async (url, init) => {
      const response = await fetch(url, init); calls.push({ path: new URL(url).pathname, method: init.method, status: response.status }); return response;
    }));
    const status = code => assert.equal(calls.at(-1)?.status, code);
    process.stdout.write(JSON.stringify(await work({ api, base, input, calls, status, mark: label => { stage = label; } })));
  } catch (error) {
    // Assertions/transport exceptions must never print request bodies or source.
    process.stderr.write(`Acceptance failure at ${stage}: ${error.kind || error.code || error.name}\n`); process.exitCode = 1;
  }
}

// Offline npm cache inventory, not an installer or production build verifier.
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

export async function inventory(packages, read) {
  const artifacts = [];
  for (const [name, entry] of Object.entries(packages)) {
    if (!name) continue;
    let state = 'invalid_lock';
    if (typeof entry.resolved === 'string' && /^sha512-[A-Za-z0-9+/]+={0,2}$/.test(entry.integrity ?? '')) {
      try {
        const bytes = await read('make-fetch-happen:request-cache:' + entry.resolved);
        state = bytes.byteLength > 64 * 1024 * 1024 ? 'unavailable' : 'sha512-' + createHash('sha512').update(bytes).digest('base64') === entry.integrity ? 'verified' : 'integrity_mismatch';
      } catch (error) { state = error.code === 'ENOENT' ? 'missing' : error.code === 'EINTEGRITY' ? 'integrity_mismatch' : 'unavailable'; }
    }
    artifacts.push({ package: name, version: entry.version, state, platform_optional: entry.optional === true, os: entry.os ?? null, cpu: entry.cpu ?? null });
  }
  const count = state => artifacts.filter(item => item.state === state).length;
  return { locked: artifacts.length, verified: count('verified'), missing: count('missing'), integrity_mismatch: count('integrity_mismatch'),
    unavailable: count('unavailable'), invalid_lock: count('invalid_lock'), all_artifacts_verified: artifacts.length > 0 && artifacts.every(item => item.state === 'verified'),
    production_build_verified: false, installation_verified: false, artifacts };
}

async function main() {
  try {
    // npm supplies its own installed CLI location; no additional module is added.
    const npm = process.env.npm_execpath;
    if (!npm) throw new Error('npm_context_required');
    const require = createRequire(npm); const cache = require('cacache');
    const cacheRoot = execFileSync(process.execPath, [npm, '--offline', 'config', 'get', 'cache'], { encoding: 'utf8', timeout: 10000, stdio: ['ignore', 'pipe', 'pipe'] }).trim();
    const directory = join(cacheRoot, '_cacache');
    const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
    const result = await inventory(lock.packages, async key => (await cache.get(directory, key)).data);
    process.stdout.write(JSON.stringify(result) + '\n'); process.exitCode = result.all_artifacts_verified ? 0 : 1;
  } catch {
    process.stdout.write(JSON.stringify({ error: 'cache_inventory_unavailable', all_artifacts_verified: false, production_build_verified: false, installation_verified: false }) + '\n');
    process.exitCode = 1;
  }
}
if (process.argv[1] === fileURLToPath(import.meta.url)) await main();

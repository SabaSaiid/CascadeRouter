import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
test('render process removes only its owned temporary build on exit',()=>{
  const helper = new URL('./render.mjs', import.meta.url).href;
  const child = spawnSync(process.execPath, ['--input-type=module','-e',`const helper=await import(${JSON.stringify(helper)}); process.stdout.write(helper.buildDirectory);`], {encoding:'utf8'});
  assert.equal(child.status,0); assert.ok(child.stdout.includes('cascade-render-')); assert.equal(existsSync(child.stdout),false);
  assert.equal(child.stderr,'');
});

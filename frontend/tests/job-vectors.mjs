import { readFileSync } from 'node:fs';
import { fixture } from './fixtures.mjs';
const definitions=JSON.parse(readFileSync(new URL('./fixtures/invalid-job-patches.json',import.meta.url),'utf8'));
// Intentionally invalid copies, never displayable data or production evidence.
export const invalidJobs=definitions.map(({name,edits})=>{
  const value=fixture('job');
  for(const [path,replacement] of edits) { let parent=value; for(const key of path.slice(0,-1)) parent=parent[key]; parent[path.at(-1)]=replacement; }
  return {name,value};
});

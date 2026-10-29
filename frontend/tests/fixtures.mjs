import { readFileSync } from 'node:fs';
export const fixture = name => JSON.parse(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), 'utf8'));

// Checks that the production build contains no part of the mock API (D-783): MSW, its worker, the
// mock backend or its fixtures. Part of `npm run build`.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = new URL('../dist/', import.meta.url);
const MARKERS = [
  'mockServiceWorker',
  'setupWorker',
  '__sfacMock',
  'MockBackend',
  'T15a planted pilot',
  'failure injected by the mock',
  'msw',
];

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

const all = files(fileURLToPath(dist));
const hits = [];
for (const f of all) {
  if (!/\.(js|html|css|map)$/.test(f) && !f.endsWith('mockServiceWorker.js')) continue;
  if (f.endsWith('mockServiceWorker.js')) hits.push(`${f}: worker script present`);
  const text = readFileSync(f, 'utf-8');
  for (const m of MARKERS) {
    if (m === 'msw' ? /\bmsw\b/.test(text) : text.includes(m)) hits.push(`${f}: contains "${m}"`);
  }
}
if (all.length === 0) {
  console.error('dist/ is empty: run `npm run build` first');
  process.exit(1);
}
if (hits.length > 0) {
  console.error(`The production build contains the mock:\n${hits.join('\n')}`);
  process.exit(1);
}
console.log(`check-bundle: ${all.length} files in dist/, no mock code.`);

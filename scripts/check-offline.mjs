// Offline check: lists every http(s):// URL in app/src, app/index.html and app/dist.
// Allowed: localhost / 127.0.0.1, and W3C XML namespace identifiers inside the built
// vendor bundle (e.g. http://www.w3.org/2000/svg — required to create SVG elements,
// never fetched). Anything else fails.   Usage: npm run check:offline
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const targets = ['app/src', 'app/index.html', 'app/dist'].map((p) => join(root, p));
const URL_RE = /https?:\/\/[^\s"'`)<>]+/g;
const LOCAL = /^https?:\/\/(localhost|127\.0\.0\.1)([:/]|$)/;
const W3C_NS = /^http:\/\/www\.w3\.org\/(2000\/svg|1999\/xhtml|1999\/xlink|XML\/1998\/namespace|1998\/Math\/MathML|2000\/xmlns\/?)$/;
const TEXT = /\.(ts|tsx|js|mjs|css|html|json|md|svg|txt)$/;

function* walk(p) {
  if (!existsSync(p)) return;
  if (statSync(p).isDirectory()) for (const f of readdirSync(p)) yield* walk(join(p, f));
  else if (TEXT.test(p)) yield p;
}

let bad = 0;
let allowedNs = 0;
for (const t of targets) {
  for (const file of walk(t)) {
    const rel = relative(root, file).replace(/\\/g, '/');
    for (const url of readFileSync(file, 'utf8').match(URL_RE) ?? []) {
      if (LOCAL.test(url)) continue;
      if (rel.startsWith('app/dist/') && W3C_NS.test(url)) {
        allowedNs++;
        continue;
      }
      bad++;
      console.log(`  ✗ ${rel}: ${url}`);
    }
  }
}
if (!existsSync(join(root, 'app/dist'))) console.log('(i) app/dist not built yet: run npm run build first for a full check.');
console.log(`Offline check: ${bad} remote URL(s) found; ${allowedNs} W3C namespace identifier(s) allowed in the bundle.`);
process.exit(bad ? 1 : 0);

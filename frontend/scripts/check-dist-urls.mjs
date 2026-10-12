// Air-gap check (TRD.md §15 item 1): fail if the built bundle contains a URL outside the allow-list.
// Allowed: localhost/127.0.0.1, XML namespace identifiers, and inert error-message links inside libraries
// (React, Redux/Zustand internals, React Router, a polyfill note). None of these are ever fetched.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = fileURLToPath(new URL('../dist', import.meta.url));
const ALLOW = [
  /^https?:\/\/(localhost|127\.0\.0\.1)\b/,
  /^http:\/\/www\.w3\.org\//,
  /^https:\/\/react\.dev\/errors\//,
  /^https:\/\/redux(-toolkit)?\.js\.org\/Errors/,
  /^https:\/\/reactrouter\.com\/en\/main\//,
  /^https:\/\/github\.com\/ungap\/url-search-params/,
  /^https:\/\/bit\.ly\/3cXEKWf/,
];
const bad = new Set();
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(js|css|html)$/.test(name)) {
      for (const [url] of readFileSync(p, 'utf8').matchAll(/https?:\/\/[A-Za-z0-9._:/-]+/g)) {
        if (!ALLOW.some((rx) => rx.test(url))) bad.add(`${name}: ${url}`);
      }
    }
  }
}
walk(dist);
if (bad.size) {
  console.error(`URLs outside the air-gap allow-list:\n${[...bad].join('\n')}`);
  process.exit(1);
}

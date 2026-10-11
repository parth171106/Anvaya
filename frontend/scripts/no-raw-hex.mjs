// Fails the build if a colour literal appears in src/ outside styles/tokens.css (UI_UX_BRIEF.md §2.9),
// or if a console.log remains in src/ (TRD.md §17).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

const root = new URL('../src', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const HEX = /#[0-9a-fA-F]{3,8}\b/;
const LOG = /\bconsole\.log\s*\(/;
const problems = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(tsx?|css|html)$/.test(name)) check(p);
  }
}

function check(file) {
  const rel = relative(root, file).split(sep).join('/');
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    if (rel !== 'styles/tokens.css' && HEX.test(line)) problems.push(`${rel}:${i + 1}: raw hex colour (use a token)`);
    if (LOG.test(line)) problems.push(`${rel}:${i + 1}: console.log left in src/`);
  });
}

walk(root);
if (problems.length) {
  console.error(problems.join('\n'));
  process.exit(1);
}

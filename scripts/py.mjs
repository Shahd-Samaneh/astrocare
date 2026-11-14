// Runs the project's virtualenv Python (.venv at the project root) with the given args, on any OS.
// Usage: node scripts/py.mjs -m uvicorn server.main:app --port 8000
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const venv = join(root, '.venv');
const py = process.platform === 'win32' ? join(venv, 'Scripts', 'python.exe') : join(venv, 'bin', 'python');

if (!existsSync(py)) {
  console.error(`[astrocare] No virtualenv at ${venv}. Run "npm run setup" first.`);
  process.exit(1);
}
const child = spawn(py, process.argv.slice(2), { cwd: root, stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 1));
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig));

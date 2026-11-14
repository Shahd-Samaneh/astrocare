// Cross-platform one-command setup used by `npm run setup`.
// Mirrors scripts/setup.sh (macOS/Linux) and scripts/setup.ps1 (Windows). Safe to re-run.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const run = (cmd, args, opts = {}) => {
  console.log(`\n> ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, { cwd: root, stdio: 'inherit', shell: isWin, ...opts });
  return r.status === 0;
};
const has = (cmd, args = ['--version']) =>
  spawnSync(cmd, args, { stdio: 'ignore', shell: isWin }).status === 0;

// 1. Frontend (root dev runner + app)
const [major] = process.versions.node.split('.').map(Number);
if (major < 20) console.warn(`! Node ${process.versions.node} found; Node >= 20 is required.`);
if (!run('npm', ['install'])) process.exit(1);
if (!run('npm', ['install'], { cwd: join(root, 'app') })) process.exit(1);

// 2. Backend virtualenv
const candidates = isWin ? [['py', ['-3']], ['python', []]] : [['python3', []], ['python', []]];
const pyVersionOk = (cmd, pre) => {
  const r = spawnSync(cmd, [...pre, '--version'], { encoding: 'utf8', shell: isWin });
  const m = /Python (\d+)\.(\d+)/.exec(`${r.stdout}${r.stderr}`);
  return r.status === 0 && m && (Number(m[1]) > 3 || (Number(m[1]) === 3 && Number(m[2]) >= 11));
};
const found = candidates.find(([c, pre]) => pyVersionOk(c, pre));
if (!found) {
  console.error('! Python 3.11+ not found. Install it, then re-run `npm run setup`.');
  console.error('  Fallback: bash scripts/setup.sh  |  powershell -File scripts\\setup.ps1');
  process.exit(1);
}
const [pyCmd, pre] = found;
const venv = join(root, '.venv');
if (!existsSync(venv) && !run(pyCmd, [...pre, '-m', 'venv', venv])) process.exit(1);
const vpy = isWin ? join(venv, 'Scripts', 'python.exe') : join(venv, 'bin', 'python');
run(vpy, ['-m', 'pip', 'install', '--upgrade', 'pip'], { shell: false });
if (!run(vpy, ['-m', 'pip', 'install', '-r', join('server', 'requirements.txt')], { shell: false })) {
  process.exit(1);
}

// 3. Ollama models (optional, needed only for the Assistant)
// Windows installs Ollama per-user and the PATH may not be refreshed yet.
const winOllama = isWin && process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, 'Programs', 'Ollama', 'ollama.exe') : '';
const ollama = has('ollama') ? 'ollama' : winOllama && existsSync(winOllama) ? winOllama : null;
if (ollama) {
  run(ollama, ['pull', 'llama3.2:3b'], { shell: false });
  run(ollama, ['pull', 'nomic-embed-text'], { shell: false });
} else {
  console.log('\n(i) Ollama not found. Install from https://ollama.com/download then run:');
  console.log('    ollama pull llama3.2:3b');
  console.log('    ollama pull nomic-embed-text');
}
console.log('\nSetup complete. Next: npm run dev   (demo mode: npm run build && npm run start)');

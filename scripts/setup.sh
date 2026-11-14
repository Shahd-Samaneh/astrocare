#!/usr/bin/env bash
# AstroCare one-command setup for macOS / Linux.  Usage: bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v node >/dev/null || { echo "Node.js >= 20 is required: https://nodejs.org"; exit 1; }
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
[ "$NODE_MAJOR" -ge 20 ] || echo "WARNING: Node $NODE_MAJOR found, >= 20 required."

PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "Python >= 3.11 is required: https://www.python.org/downloads/"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' || { echo "Python >= 3.11 is required."; exit 1; }

echo "==> Installing root + frontend packages"
npm install
npm --prefix app install

echo "==> Creating .venv and installing backend packages"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r server/requirements.txt

if command -v ollama >/dev/null; then
  echo "==> Pulling local models"
  ollama pull llama3.2:3b
  ollama pull nomic-embed-text
else
  echo "(i) Ollama not found. Install: https://ollama.com/download"
  echo "    then: ollama pull llama3.2:3b && ollama pull nomic-embed-text"
fi
echo "Done. Run: npm run dev"

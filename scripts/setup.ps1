# AstroCare one-command setup for Windows (PowerShell 5.1+).
# Usage (from the project root):  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js >= 20 is required: https://nodejs.org' }
$nodeMajor = [int](node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 20) { Write-Warning "Node $nodeMajor found, >= 20 required." }

$pyExe = $null; $pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $pyExe = 'py'; $pyArgs = @('-3') }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyExe = 'python' }
else { throw 'Python >= 3.11 is required: https://www.python.org/downloads/' }

Write-Host '==> Installing root + frontend packages'
npm install
if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
npm --prefix app install
if ($LASTEXITCODE -ne 0) { throw 'npm install (app) failed' }

Write-Host '==> Creating .venv and installing backend packages'
if (-not (Test-Path '.venv')) { & $pyExe @pyArgs -m venv .venv }
& .venv\Scripts\python.exe -m pip install --upgrade pip
& .venv\Scripts\python.exe -m pip install -r server\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

$ollama = $null
if (Get-Command ollama -ErrorAction SilentlyContinue) { $ollama = 'ollama' }
elseif (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe") { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
if ($ollama) {
  Write-Host '==> Pulling local models'
  & $ollama pull llama3.2:3b
  & $ollama pull nomic-embed-text
} else {
  Write-Host '(i) Ollama not found. Install: https://ollama.com/download'
  Write-Host '    then: ollama pull llama3.2:3b; ollama pull nomic-embed-text'
}
Write-Host 'Done. Run: npm run dev'

# DirectorX setup (Windows / PowerShell)

param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> Creating venv .venv"
& $Python -m venv .venv
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"
$Py = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "==> Upgrading pip"
& $Py -m pip install --upgrade pip

Write-Host "==> Installing requirements"
& $Pip install -r requirements.txt

Write-Host "==> Done. Activate with:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "Then dry-run: python main.py --dry-run"
Write-Host ""
Write-Host "Optional best voice (heavy):"
Write-Host "    pip install TTS"
Write-Host "Put assets\voices\default.wav then set VOICE_BACKEND=xtts in config if desired."

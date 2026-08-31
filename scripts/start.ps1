# SentinelIQ production launcher (Windows / PowerShell).
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$Root\.env")) {
    Write-Host "[start] .env not found - copy .env.example to .env and configure it." -ForegroundColor Yellow
}

if (-not (Test-Path "$Root\venv")) {
    Write-Host "[start] creating virtualenv..." -ForegroundColor Cyan
    python -m venv "$Root\venv"
    & "$Root\venv\Scripts\python.exe" -m pip install -U pip
    & "$Root\venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt"
}

Write-Host "[start] launching SentinelIQ (single worker)..." -ForegroundColor Cyan
Push-Location $Root
try {
    & "$Root\venv\Scripts\python.exe" run.py
} finally {
    Pop-Location
}
# SentinelIQ quick-tunnel launcher (Windows / PowerShell).
# Exposes the locally-running server (default http://localhost:8000) to the
# public internet via a Cloudflare TryCloudflare tunnel, so the Vercel-hosted
# dashboard can reach the live CV feed + API from anywhere.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start-tunnel.ps1
#
# IMPORTANT: a quick tunnel's URL is RANDOM and changes every restart. After
# starting one, copy the printed trycloudflare.com URL into the /api rewrite in
# frontend/vercel.json (destination) and redeploy Vercel.
#
# This script downloads cloudflared.exe (a single ~55MB binary) on first run.
param(
    [string]$Target = "http://localhost:8000",
    [switch]$SkipVercel
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root "cloudflared.exe"
$OutLog = Join-Path $Root "tunnel.out"
$ErrLog = Join-Path $Root "tunnel.err"
$PidFile = Join-Path $Root "tunnel.pid"
$UrlFile = Join-Path $Root "trycloudflare-url.txt"

if (-not (Test-Path $Exe)) {
    Write-Host "[tunnel] downloading cloudflared.exe..." -ForegroundColor Cyan
    $Url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $Url -OutFile $Exe -UseBasicParsing
}

if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile
    $OldProc = Get-Process -Id $OldPid -ErrorAction SilentlyContinue
    if ($OldProc) {
        Write-Host "[tunnel] stopping existing tunnel (PID $OldPid)..." -ForegroundColor Yellow
        Stop-Process -Id $OldPid -Force
        Start-Sleep -Seconds 2
    }
}

Remove-Item $OutLog, $ErrLog -Force -ErrorAction SilentlyContinue

Write-Host "[tunnel] exposing $Target ..." -ForegroundColor Cyan
$p = Start-Process -FilePath $Exe -ArgumentList "tunnel --url $Target" `
    -WorkingDirectory $Root -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog `
    -WindowStyle Hidden -PassThru
$p.Id | Set-Content $PidFile
Write-Host "[tunnel] started PID $($p.Id), waiting for URL..." -ForegroundColor Cyan

$Deadline = (Get-Date).AddSeconds(30)
$Url = $null
while ((Get-Date) -lt $Deadline) {
    Start-Sleep -Seconds 1
    $match = Select-String -Path $ErrLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($match) {
        $Url = ($match.Matches[0].Value -split " ")[0]
        break
    }
}

if (-not $Url) {
    Write-Host "[tunnel] FAILED to get a tunnel URL. Check tunnel.err" -ForegroundColor Red
    if (Test-Path $ErrLog) { Get-Content $ErrLog -Tail 20 }
    exit 1
}

$Url | Set-Content $UrlFile
Write-Host ""
Write-Host "[tunnel] TUNNEL READY: $Url" -ForegroundColor Green
Write-Host "[tunnel] URL saved to trycloudflare-url.txt" -ForegroundColor Cyan

# Verify end-to-end health through the tunnel.
try {
    $r = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 30
    Write-Host "[tunnel] health via tunnel: $($r.Content)" -ForegroundColor Green
}
catch {
    Write-Host "[tunnel] health check failed - is the server running on $Target ?" -ForegroundColor Red
}

# Auto-wire Vercel to the new (random) URL and redeploy, unless -SkipVercel.
if (-not $SkipVercel) {
    if (Get-Command vercel -ErrorAction SilentlyContinue) {
        Write-Host ""
        Write-Host "[tunnel] updating Vercel to this URL..." -ForegroundColor Cyan
        & (Join-Path $Root "scripts\update-vercel.ps1")
    }
    else {
        Write-Host ""
        Write-Host "[tunnel] 'vercel' CLI not found - install with: npm i -g vercel" -ForegroundColor Yellow
        Write-Host "[tunnel] then paste $Url into frontend/vercel.json (/api destination) and run: vercel --prod" -ForegroundColor Yellow
    }
}

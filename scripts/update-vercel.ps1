# SentinelIQ - Point Vercel's /api rewrite at the current tunnel URL and redeploy.
#
# After starting the Cloudflare tunnel, run this so the Vercel-hosted dashboard
# calls the live engine on this machine:
#   powershell -ExecutionPolicy Bypass -File scripts\update-vercel.ps1
# It reads the tunnel URL from trycloudflare-url.txt, patches frontend/vercel.json,
# commits + pushes, then deploys the frontend/ directory to Vercel with the Vercel CLI.
#
# Requires: vercel CLI installed + logged in (`npm i -g vercel` then `vercel login`).
param(
    [string]$ProjectDir = "",              # optional explicit path to frontend/
    [switch]$SkipPush                      # skip git push (deploy directly)
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$UrlFile = Join-Path $Root "trycloudflare-url.txt"
$FrontendDir = if ($ProjectDir) { $ProjectDir } else { Join-Path $Root "frontend" }
$VercelJson = Join-Path $FrontendDir "vercel.json"

if (-not (Test-Path $UrlFile)) {
    Write-Host "[update-vercel] no tunnel URL found ($UrlFile). Start the tunnel first: scripts\start-tunnel.ps1" -ForegroundColor Red
    exit 1
}
$TunnelUrl = (Get-Content $UrlFile | Select-Object -First 1).Trim()
$TunnelUrl = $TunnelUrl.TrimEnd('/')
if ($TunnelUrl -notmatch "^https://.*trycloudflare\.com$") {
    Write-Host "[update-vercel] unexpected tunnel URL format: '$TunnelUrl'" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $VercelJson)) {
    Write-Host "[update-vercel] vercel.json not found at $VercelJson" -ForegroundColor Red
    exit 1
}

# Read, patch the /api rewrite destination, preserve JSON ordering/format.
$Json = Get-Content $VercelJson -Raw
if ($Json -match '(\s*"destination"\s*:\s*")[^"]*trycloudflare\.com/api[^"]*(")') {
    $Json = $Json -replace '(\s*"destination"\s*:\s*")[^"]*trycloudflare\.com/api[^"]*(")', ("`${1}" + $TunnelUrl + "/api/:path*`${2}")
    $Json | Set-Content $VercelJson -NoNewline
    Write-Host "[update-vercel] patched /api rewrite -> $TunnelUrl" -ForegroundColor Green
} else {
    Write-Host "[update-vercel] could not find a trycloudflare /api destination to patch in vercel.json" -ForegroundColor Red
    exit 1
}

# Sanity-check the JSON still parses.
try { $Json = Get-Content $VercelJson -Raw | ConvertFrom-Json -ErrorAction Stop; Write-Host "[update-vercel] vercel.json valid" -ForegroundColor Green }
catch { Write-Host "[update-vercel] ERROR: patched vercel.json is invalid JSON: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }

# Commit + push so Vercel (Git-based) and the repo stay in sync.
Push-Location $Root
try {
    git add frontend/vercel.json
    if (-not $SkipPush) {
        $diff = git diff --cached --quiet; if ($LASTEXITCODE -ne 0) {
            git commit -m "Auto: point Vercel /api rewrite at tunnel $TunnelUrl"
            git push origin main
            Write-Host "[update-vercel] committed + pushed" -ForegroundColor Green
        } else {
            Write-Host "[update-vercel] vercel.json unchanged (same URL) - skipping commit/push" -ForegroundColor Yellow
        }
    }
} finally {
    Pop-Location
}

# Deploy the static frontend to Vercel (non-interactive).
Write-Host "[update-vercel] deploying frontend to Vercel..." -ForegroundColor Cyan
Push-Location $FrontendDir
try {
    & vercel deploy --prod --yes 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Host "[update-vercel] VERCEL DEPLOY WARNING (exit $LASTEXITCODE) - see output above" -ForegroundColor Yellow }
} finally {
    Pop-Location
}
Write-Host ""
Write-Host "[update-vercel] DONE. The dashboard now routes /api/* to $TunnelUrl" -ForegroundColor Green

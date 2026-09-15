# SentinelIQ - run a local RTSP server (MediaMTX) publishing theft.mp4 as a
# looping live stream at rtsp://127.0.0.1:8554/test (and /cam).
#
# Use this as a reliable infinite test source for the engine - it never expires
# and accepts unlimited connections (public RTSP test streams are one-shot/dead).
#
# Prerequisites: ffmpeg on PATH or set -FfPath; mediamtx downloaded (first run
# downloads it from GitHub releases).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start-local-rtsp.ps1
param(
    [string]$Video = "C:\Users\Rohith M S\OneDrive\Desktop\projects\Hackathon\theft.mp4",
    [string]$FfPath = "",
    [int]$Port = 8554
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$MtxExe = Join-Path $Root "mediamtx\mediamtx.exe"
$MtxZip = Join-Path $Root "mediamtx.zip"
$MtxPid = Join-Path $Root "mediamtx.pid"
$PubPid = Join-Path $Root "publisher.pid"

if (-not (Test-Path $MtxExe)) {
    Write-Host "[rtsp] downloading MediaMTX..." -ForegroundColor Cyan
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/bluenviron/mediamtx/releases/latest" -Headers @{ "User-Agent" = "opencode" }
    $asset = $rel.assets | Where-Object { $_.name -like "*windows_amd64.zip" } | Select-Object -First 1
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $MtxZip -UseBasicParsing
    Expand-Archive -Path $MtxZip -DestinationPath (Join-Path $Root "mediamtx") -Force
}

if (-not (Test-Path $Video)) { Write-Host "[rtsp] video not found: $Video" -ForegroundColor Red; exit 1 }

# Stop old instances
foreach ($pf in @($MtxPid, $PubPid)) {
    if (Test-Path $pf) {
        $old = Get-Content $pf
        Stop-Process -Id $old -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

# Start MediaMTX
Write-Host "[rtsp] starting MediaMTX on :$Port ..." -ForegroundColor Cyan
$mtx = Start-Process -FilePath $MtxExe -WorkingDirectory (Join-Path $Root "mediamtx") -WindowStyle Hidden -PassThru
$mtx.Id | Set-Content $MtxPid
Start-Sleep -Seconds 3

# Locate ffmpeg
$ff = $FfPath
if (-not $ff) { $ff = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source }
if (-not $ff) {
    $cand = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cand) { $ff = $cand.FullName }
}
if (-not $ff) { Write-Host "[rtsp] ffmpeg not found - install it or pass -FfPath" -ForegroundColor Red; exit 1 }

# Publish video as looping RTSP
$quoted = '"' + $Video + '"'
$argStr = "-re -stream_loop -1 -i $quoted -c copy -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:$Port/test"
Write-Host "[rtsp] publishing $Video -> rtsp://127.0.0.1:$Port/test" -ForegroundColor Cyan
$pub = Start-Process -FilePath $ff -ArgumentList $argStr -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardError (Join-Path $Root "publisher.err.log") -PassThru
$pub.Id | Set-Content $PubPid

Start-Sleep -Seconds 4
if ($pub.HasExited) {
    Write-Host "[rtsp] FAILED - publisher exited:" -ForegroundColor Red
    Get-Content (Join-Path $Root "publisher.err.log") -Tail 15
    exit 1
}

Write-Host ""
Write-Host "[rtsp] READY: rtsp://127.0.0.1:$Port/test" -ForegroundColor Green
Write-Host "[rtsp] point SentinelIQ at it in Settings -> STREAM -> CCTV/RTSP" -ForegroundColor Yellow
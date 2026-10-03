[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$NoBrowser,
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       UniversalDownloader -- Windows Launcher          " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Check Python
Write-Host "[1/4] Checking Python environment..." -ForegroundColor Yellow
try {
    $pyVersion = & python --version 2>&1
    Write-Host "  -> Python OK: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  [!] ERROR: Python is not found in PATH." -ForegroundColor Red
    Write-Host "      Please install Python 3.11+ and ensure 'Add python.exe to PATH' is checked." -ForegroundColor Yellow
    exit 1
}

# 2. Check yt-dlp Python package (AppLocker-safe invocation via python -m yt_dlp)
Write-Host "[2/4] Checking yt-dlp module..." -ForegroundColor Yellow
try {
    $ytdlpVersion = & python -m yt_dlp --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  -> yt-dlp OK: version $ytdlpVersion" -ForegroundColor Green
    } else {
        throw "yt-dlp returned exit code $LASTEXITCODE"
    }
} catch {
    Write-Host "  [!] ERROR: Python module 'yt_dlp' is not installed or failed to execute." -ForegroundColor Red
    Write-Host "      Install it via: python -m pip install yt-dlp" -ForegroundColor Yellow
    exit 1
}

# 3. Check FFmpeg
Write-Host "[3/4] Checking FFmpeg..." -ForegroundColor Yellow
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegCmd) {
    Write-Host "  -> FFmpeg OK: found in PATH ($($ffmpegCmd.Source))" -ForegroundColor Green
} else {
    Write-Host "  [!] WARNING: FFmpeg was not found in PATH." -ForegroundColor Yellow
    Write-Host "      Audio extraction and subtitle embedding will fail without FFmpeg." -ForegroundColor Yellow
}

# 4. Check Frontend build
$FrontendDist = Join-Path $ScriptDir "frontend\dist\index.html"
if ($Dev) {
    Write-Host "[4/4] Mode: Development (Concurrent Flask + Vite HMR)" -ForegroundColor Cyan
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCmd) {
        Write-Host "  [!] ERROR: npm is required for development mode." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[4/4] Mode: Production (Single-Server SPA via Flask)" -ForegroundColor Cyan
    if (-not (Test-Path $FrontendDist)) {
        Write-Host "  -> Production build not found. Building frontend now..." -ForegroundColor Yellow
        $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
        if ($npmCmd) {
            Push-Location "frontend"
            try {
                & npm run build
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "  [!] Frontend build failed." -ForegroundColor Red
                    Pop-Location
                    exit 1
                }
            } finally {
                Pop-Location
            }
            Write-Host "  -> Frontend build complete." -ForegroundColor Green
        } else {
            Write-Host "  [!] WARNING: frontend/dist not found and npm is not installed." -ForegroundColor Yellow
            Write-Host "      The API will run, but web UI will not be served." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  -> Production build verified (frontend/dist ready)." -ForegroundColor Green
    }
}

$TargetUrl = if ($Dev) { "http://localhost:5173" } else { "http://127.0.0.1:$Port" }

# Background browser launcher once server is healthy
if (-not $NoBrowser) {
    $healthCheckUrl = "http://127.0.0.1:$Port/health"
    $browserScript = {
        param($HealthUrl, $OpenUrl)
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 500
            try {
                $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 1 -ErrorAction SilentlyContinue
                if ($r -and $r.StatusCode -eq 200) {
                    Start-Sleep -Milliseconds 300
                    Start-Process $OpenUrl
                    break
                }
            } catch {}
        }
    }
    Start-Job -ScriptBlock $browserScript -ArgumentList $healthCheckUrl, $TargetUrl | Out-Null
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  UniversalDownloader is starting!" -ForegroundColor Green
Write-Host "  Application URL: $TargetUrl" -ForegroundColor Green
Write-Host "  Press Ctrl+C in this window to stop the server." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

if ($Dev) {
    $backendProc = Start-Process python -ArgumentList "backend/app.py" -PassThru -NoNewWindow
    try {
        Push-Location "frontend"
        & npm run dev
    } finally {
        Pop-Location
        if ($backendProc -and -not $backendProc.HasExited) {
            Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    & python backend/app.py
}

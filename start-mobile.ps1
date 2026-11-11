$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendOut = Join-Path $Root "frontend\out\index.html"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$CloudflaredExe = (Get-Command cloudflared -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
if (-not $CloudflaredExe) {
    $Candidate = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if (Test-Path $Candidate) { $CloudflaredExe = $Candidate }
    $Candidate64 = "C:\Program Files\cloudflared\cloudflared.exe"
    if (Test-Path $Candidate64) { $CloudflaredExe = $Candidate64 }
}

if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual muhit topilmadi: $PythonExe"
}
if (-not (Test-Path $FrontendOut)) {
    Write-Error "frontend/out/index.html topilmadi. Avval `cd frontend; npm.cmd run build` bajaring."
}
if (-not $CloudflaredExe) {
    Write-Error "cloudflared topilmadi. `winget install --id Cloudflare.cloudflared` orqali o'rnating."
}

Write-Host "1. Yagona FastAPI serveri ishga tushmoqda: http://127.0.0.1:8000" -ForegroundColor Cyan
$backendProc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $BackendDir `
    -PassThru

try {
    Start-Sleep -Seconds 2
    Write-Host "2. Telefon uchun HTTPS tunnel ochilmoqda (chiqadigan https://...trycloudflare.com manzilini telefondan oching)..." -ForegroundColor Green
    & $CloudflaredExe tunnel --url http://127.0.0.1:8000
} finally {
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force
    }
}

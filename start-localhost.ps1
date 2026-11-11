$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$FrontendOut = Join-Path $FrontendDir "out\index.html"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$NpmCmd = "C:\Program Files\nodejs\npm.cmd"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual muhit topilmadi: $PythonExe"
}

if (-not (Test-Path $FrontendOut) -and (Test-Path $NpmCmd)) {
    $env:PATH = "C:\Program Files\nodejs;$env:PATH"
    Write-Host "Frontend eksport qilinmoqda..." -ForegroundColor Yellow
    Set-Location $FrontendDir
    & $NpmCmd run build
}

Write-Host "Aqua Voice Uzbek (yagona URL) ishga tushmoqda: http://127.0.0.1:8000/" -ForegroundColor Cyan
Set-Location $BackendDir
& $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

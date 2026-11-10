$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$NpmCmd = "C:\Program Files\nodejs\npm.cmd"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual muhit topilmadi: $PythonExe"
}

Write-Host "1. FastAPI Backend ishga tushmoqda: http://127.0.0.1:8000" -ForegroundColor Cyan
$backendProc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $BackendDir `
    -PassThru

try {
    if (Test-Path $NpmCmd) {
        $env:PATH = "C:\Program Files\nodejs;$env:PATH"
        Write-Host "2. Next.js + Tiptap Frontend ishga tushmoqda: http://localhost:3000" -ForegroundColor Green
        Set-Location $FrontendDir
        & $NpmCmd run dev
    } else {
        Write-Host "Node.js topilmadi; Python Demo UI ochiq: http://127.0.0.1:8000/" -ForegroundColor Yellow
        Wait-Process -Id $backendProc.Id
    }
} finally {
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force
    }
}

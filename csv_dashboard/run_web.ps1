$ErrorActionPreference = "Stop"

$Dashboard = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $Dashboard
$Frontend = Join-Path $Dashboard "frontend"

Write-Host "Installing backend dependencies..."
Set-Location $RepoRoot
poetry install --no-root

Write-Host "Installing frontend dependencies..."
Set-Location $Frontend
npm install

Write-Host "Starting backend..."
$backendCommand = "Set-Location '$RepoRoot'; `$env:PYTHONIOENCODING='utf-8'; poetry run uvicorn csv_dashboard.backend.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $backendCommand)

Write-Host "Starting frontend..."
$frontendCommand = "Set-Location '$Frontend'; npm run dev -- --host 127.0.0.1"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $frontendCommand)

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host ""

Start-Process "http://127.0.0.1:5173"

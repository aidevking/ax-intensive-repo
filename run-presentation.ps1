$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$ApiUrl = "http://localhost:8000"

Set-Location $Root
Set-Content -Path (Join-Path $Frontend ".env.local") -Value "NEXT_PUBLIC_API_BASE_URL=$ApiUrl"

if (!(Test-Path $Python)) {
  py -m venv .venv
}

& $Python -m pip install --upgrade pip
& $Pip install --use-deprecated=legacy-resolver -r requirements.txt

Set-Location $Frontend
if (!(Test-Path (Join-Path $Frontend "node_modules"))) {
  npm install
}
Set-Location $Root

$BackendCmd = "cd `"$Root`"; .\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
$FrontendCmd = "cd `"$Frontend`"; npm run dev -- --hostname 127.0.0.1 --port 3000"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCmd
Write-Host "Waiting for the API to start..."
$ApiReady = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    Invoke-RestMethod -Uri "$ApiUrl/health" | Out-Null
    $ApiReady = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}

if ($ApiReady) {
  Invoke-RestMethod -Method Post -Uri "$ApiUrl/reviews/seed-sample" | Out-Null
  Write-Host "Sample data loaded."
} else {
  Write-Host "The API is still starting. Once it is ready, run:"
  Write-Host "Invoke-RestMethod -Method Post -Uri $ApiUrl/reviews/seed-sample"
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendCmd
Start-Sleep -Seconds 8
Start-Process "http://localhost:3000/dashboard"

Write-Host ""
Write-Host "App Review Analyzer is starting."
Write-Host "Dashboard: http://localhost:3000/dashboard"
Write-Host "Reviews:   http://localhost:3000/reviews"
Write-Host "Compare:   http://localhost:3000/compare"
Write-Host "API:       http://localhost:8000/health"

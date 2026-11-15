<#
Start SARAURA for testers: the API (port 8000), the website (port 3000) and a public link.

  .\scripts\start.ps1                                        # start whatever is not running
  .\scripts\start.ps1 -Build                                 # rebuild the website first (after changing frontend code)
  .\scripts\start.ps1 -NgrokDomain your-name.ngrok-free.app  # once: use ngrok and its free fixed address from now on

With ngrok's fixed address the link never changes. Otherwise a Cloudflare quick link is used: it stays the same
while its tunnel runs, and changes if the tunnel is stopped (.\scripts\stop.ps1 -Tunnel) or the computer restarts.
Logs are in .run\ .
#>
param([switch]$Build, [string]$NgrokDomain)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$run = Join-Path $root ".run"
New-Item -ItemType Directory -Force $run | Out-Null
$env:PATH = "C:\Program Files\nodejs;$env:APPDATA\npm;$env:PATH"
$cloudflared = "$env:USERPROFILE\cloudflared\cloudflared.exe"
$ngrok = (Get-Command ngrok -ErrorAction SilentlyContinue).Source  # e.g. the Microsoft Store install
if (-not $ngrok) { $ngrok = "$env:USERPROFILE\ngrok\ngrok.exe" }

function Listening($port) { [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
function WaitFor($port, $what) {
    for ($i = 0; $i -lt 90 -and -not (Listening $port); $i++) { Start-Sleep 1 }
    if (Listening $port) { Write-Host "  $what is up on port $port" } else { Write-Host "  $what did not start: see .run\" -ForegroundColor Red }
}

Write-Host "SARAURA"
# 1. API
if (Listening 8000) { Write-Host "  API already running (port 8000)" }
else {
    Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "api.main:app", "--port", "8000" `
        -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$run\api.log" -RedirectStandardError "$run\api.err.log"
    WaitFor 8000 "API"
}

# 2. Website (production build; /api is forwarded to the API, so one public link serves both)
if ($Build -or -not (Test-Path "$root\frontend\.next\BUILD_ID")) {
    if (Listening 3000) { Write-Host "  Stop the website first (.\scripts\stop.ps1) to rebuild it" -ForegroundColor Yellow }
    else {
        Write-Host "  building the website (about a minute)..."
        # through cmd: the build prints progress on stderr, which PowerShell would otherwise treat as an error
        cmd /c "pnpm --dir `"$root\frontend`" build > `"$run\build.log`" 2>&1"
        if ($LASTEXITCODE -ne 0) { Write-Host "  build failed: see .run\build.log" -ForegroundColor Red; exit 1 }
    }
}
if (Listening 3000) { Write-Host "  website already running (port 3000)" }
else {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "pnpm --dir frontend start -p 3000" -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput "$run\web.log" -RedirectStandardError "$run\web.err.log"
    WaitFor 3000 "website"
}

# 3. Public link.
# With ngrok and its free fixed address (.\scripts\start.ps1 -NgrokDomain your-name.ngrok-free.app, remembered in
# .run\ngrok-domain.txt) the link never changes. Without it, a Cloudflare quick link, reused while the tunnel runs.
if ($NgrokDomain) { Set-Content "$run\ngrok-domain.txt" ($NgrokDomain -replace '^https?://', '' -replace '/.*$', '') }
$domain = if (Test-Path "$run\ngrok-domain.txt") { (Get-Content "$run\ngrok-domain.txt" -Raw).Trim() } else { "" }
if ($domain) {
    $url = "https://$domain"
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false  # one tunnel at a time
    if (Get-Process ngrok -ErrorAction SilentlyContinue) { Write-Host "  ngrok already running" }
    else {
        if (-not (Test-Path $ngrok)) { Write-Host "  ngrok not found at $ngrok" -ForegroundColor Red; exit 1 }
        Start-Process -FilePath $ngrok -ArgumentList "http", "--url=$url", "3000", "--log", "stdout" `
            -WindowStyle Hidden -RedirectStandardOutput "$run\ngrok.log" -RedirectStandardError "$run\ngrok.err.log"
        Start-Sleep 4
        if (-not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
            Write-Host "  ngrok stopped: see .run\ngrok.log (is the authtoken added? ngrok config add-authtoken <token>)" -ForegroundColor Red; exit 1
        }
    }
    Set-Content "$run\public-url.txt" $url
    Write-Host ""
    Write-Host "  Public link (fixed): $url" -ForegroundColor Green
    exit 0
}
if (Get-Process cloudflared -ErrorAction SilentlyContinue) { Write-Host "  tunnel already running (same link as before)" }
else {
    if (-not (Test-Path $cloudflared)) { Write-Host "  cloudflared not found at $cloudflared" -ForegroundColor Red; exit 1 }
    Remove-Item "$run\tunnel.log" -ErrorAction SilentlyContinue
    Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://localhost:3000" `
        -WindowStyle Hidden -RedirectStandardOutput "$run\tunnel.out.log" -RedirectStandardError "$run\tunnel.log"
    Write-Host "  starting the tunnel (a new link)..."
}
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    if (Test-Path "$run\tunnel.log") {
        $m = Select-String -Path "$run\tunnel.log" -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
    if (-not $url) { Start-Sleep 1 }
}
if ($url) {
    Set-Content "$run\public-url.txt" $url
    Write-Host ""
    Write-Host "  Public link: $url" -ForegroundColor Green
} else {
    Write-Host "  The tunnel did not report a link yet: see .run\tunnel.log" -ForegroundColor Yellow
}

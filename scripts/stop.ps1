<#
Stop SARAURA.

  .\scripts\stop.ps1             # stop the API and the website; the tunnel keeps running
  .\scripts\stop.ps1 -Tunnel     # also stop the tunnel (ngrok keeps its fixed address; a Cloudflare quick link changes)

While the API and website are stopped, testers who open the link see an error page until you start again.
#>
param([switch]$Tunnel)
$root = Split-Path $PSScriptRoot -Parent
$fixed = Test-Path (Join-Path $root ".run\ngrok-domain.txt")

function StopPort($port, $what) {
    $pids = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { Write-Host "  $what was not running"; return }
    foreach ($p in $pids) { Stop-Process -Id $p -Force -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "  stopped the $what (port $port)"
}

Write-Host "SARAURA"
StopPort 3000 "website"
StopPort 8000 "API"
$u = Join-Path $root ".run\public-url.txt"
if ($Tunnel) {
    Get-Process cloudflared, ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    if ($fixed) { Write-Host "  stopped the tunnel; the fixed link comes back with the next start: $(Get-Content $u -ErrorAction SilentlyContinue)" }
    else { Remove-Item $u -ErrorAction SilentlyContinue; Write-Host "  stopped the tunnel: the next start gives a new link" }
} elseif (Test-Path $u) {
    Write-Host "  tunnel still running; the link stays $(Get-Content $u)"
}

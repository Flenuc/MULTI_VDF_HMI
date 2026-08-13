# Install + start Mosquitto for VarioField on Windows.
# Run in elevated PowerShell if possible:  Right-click → Run as administrator
#   powershell -ExecutionPolicy Bypass -File setup_mosquitto.ps1
$ErrorActionPreference = "Stop"
$Port = if ($env:VARIOFIELD_MQTT_PORT) { [int]$env:VARIOFIELD_MQTT_PORT } else { 1883 }

function Write-Log($msg) { Write-Host "[variofield-mosquitto] $msg" }

function Test-PortOpen([string]$HostName = "127.0.0.1", [int]$P = 1883) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect($HostName, $P, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(800)
    if ($ok -and $c.Connected) { $c.Close(); return $true }
    $c.Close()
  } catch {}
  return $false
}

if (Test-PortOpen "127.0.0.1" $Port) {
  Write-Log "Broker already listening on port $Port — nothing to do."
  exit 0
}

$mosq = Get-Command mosquitto -ErrorAction SilentlyContinue
if (-not $mosq) {
  Write-Log "Mosquitto not in PATH — trying winget…"
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    winget install -e --id EclipseFoundation.Mosquitto --accept-package-agreements --accept-source-agreements
  } else {
    Write-Log "Install Mosquitto manually from https://mosquitto.org/download/"
    Write-Log "Or: winget install EclipseFoundation.Mosquitto"
    exit 2
  }
}

# Common install paths
$candidates = @(
  "${env:ProgramFiles}\mosquitto\mosquitto.exe",
  "${env:ProgramFiles(x86)}\mosquitto\mosquitto.exe"
)
$exe = $null
foreach ($c in $candidates) {
  if (Test-Path $c) { $exe = $c; break }
}
if (-not $exe) {
  $cmd = Get-Command mosquitto -ErrorAction SilentlyContinue
  if ($cmd) { $exe = $cmd.Source }
}
if (-not $exe) {
  Write-Log "mosquitto.exe not found after install. Re-open terminal / reboot and re-run."
  exit 3
}

$dir = Split-Path $exe -Parent
$conf = Join-Path $dir "variofield.conf"
@"
listener $Port
allow_anonymous true
"@ | Set-Content -Path $conf -Encoding ASCII

Write-Log "Config: $conf"
Write-Log "Starting Mosquitto service if registered…"
try {
  $svc = Get-Service -Name mosquitto -ErrorAction SilentlyContinue
  if ($svc) {
    Start-Service mosquitto -ErrorAction SilentlyContinue
    Set-Service mosquitto -StartupType Automatic -ErrorAction SilentlyContinue
  }
} catch {}

if (-not (Test-PortOpen "127.0.0.1" $Port)) {
  Write-Log "Starting mosquitto in background with variofield.conf…"
  Start-Process -FilePath $exe -ArgumentList "-c `"$conf`"" -WindowStyle Hidden
  Start-Sleep -Seconds 1
}

if (Test-PortOpen "127.0.0.1" $Port) {
  Write-Log "OK — broker on port $Port"
  Write-Log "VarioField profile: host 127.0.0.1 port $Port (Local Mosquitto)"
  exit 0
}

Write-Log "FAILED — port $Port still closed. Run this script as Administrator."
exit 1

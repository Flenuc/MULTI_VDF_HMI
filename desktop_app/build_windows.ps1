# Build legacy Windows standalone exes (PyInstaller). Prefer this over .bat in CI.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  python -m venv (Join-Path $PSScriptRoot ".venv")
}
& (Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1")
python -m pip install -U pip wheel
pip install -r (Join-Path $PSScriptRoot "requirements.txt")
pip install pyinstaller

New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "dist\windows") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "build\windows") | Out-Null

Write-Host "=== SAJ_PDM30_Gestor.exe ==="
pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "SAJ_PDM30_Gestor" `
  --distpath (Join-Path $PSScriptRoot "dist\windows") `
  --workpath (Join-Path $PSScriptRoot "build\windows") `
  --specpath (Join-Path $PSScriptRoot "build\windows") `
  --paths $PSScriptRoot `
  --add-data "$PSScriptRoot\param_lists;param_lists" `
  --hidden-import "serial.tools.list_ports" `
  --hidden-import "models" `
  --hidden-import "storage" `
  --hidden-import "profiles" `
  --hidden-import "gui" `
  --hidden-import "gui.app" `
  --hidden-import "comms" `
  --hidden-import "comms.serial_client" `
  --hidden-import "comms.mqtt_client" `
  --hidden-import "comms.bluetooth_client" `
  --hidden-import "comms.ble_nus_client" `
  --hidden-import "comms.dummy_client" `
  --hidden-import "comms.base" `
  --collect-submodules "comms" `
  --collect-submodules "gui" `
  --collect-all customtkinter `
  (Join-Path $PSScriptRoot "main.py")

Write-Host "=== MULTI_VDF_HMI_Flasher.exe ==="
pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "MULTI_VDF_HMI_Flasher" `
  --distpath (Join-Path $PSScriptRoot "dist\windows") `
  --workpath (Join-Path $PSScriptRoot "build\windows") `
  --specpath (Join-Path $PSScriptRoot "build\windows") `
  --paths $PSScriptRoot `
  --hidden-import "serial.tools.list_ports" `
  --hidden-import "flasher" `
  --hidden-import "flasher.gui" `
  --hidden-import "flasher.github_releases" `
  --hidden-import "flasher.flash_worker" `
  --hidden-import "esptool" `
  --collect-submodules "flasher" `
  --collect-all customtkinter `
  --collect-all esptool `
  --collect-all serial `
  (Join-Path $PSScriptRoot "run_flasher.py")

$gestor = Join-Path $PSScriptRoot "dist\windows\SAJ_PDM30_Gestor.exe"
$flash = Join-Path $PSScriptRoot "dist\windows\MULTI_VDF_HMI_Flasher.exe"
if (-not (Test-Path $gestor)) { throw "missing SAJ_PDM30_Gestor.exe" }
if (-not (Test-Path $flash)) { throw "missing MULTI_VDF_HMI_Flasher.exe" }

Copy-Item $gestor (Join-Path $PSScriptRoot "dist\SAJ_PDM30_Gestor.exe") -Force
Copy-Item $flash (Join-Path $PSScriptRoot "dist\MULTI_VDF_HMI_Flasher.exe") -Force

@"
MULTI_VDF_HMI - ejecutables Windows
===================================

SAJ_PDM30_Gestor.exe     - app de campo
MULTI_VDF_HMI_Flasher.exe - flasheo de firmwares desde GitHub

Si Windows SmartScreen avisa: Mas informacion -> Ejecutar de todas formas
(binario no firmado).

Generado con: desktop_app\build_windows.ps1
"@ | Set-Content -Path (Join-Path $PSScriptRoot "dist\windows\LEEME.txt") -Encoding ASCII

Write-Host "=== Build Windows listo ==="
Get-ChildItem (Join-Path $PSScriptRoot "dist\windows\*.exe") | Format-Table Name, Length

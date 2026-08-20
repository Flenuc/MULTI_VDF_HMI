@echo off
REM Genera ejecutables standalone Windows (.exe) con PyInstaller
REM Ejecutar EN Windows x64 (o en GitHub Actions windows-latest)
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
  python -m venv "%~dp0.venv"
)
call "%~dp0.venv\Scripts\activate.bat"
python -m pip install -U pip wheel
pip install -r "%~dp0requirements.txt"
pip install pyinstaller

if not exist "%~dp0dist\windows" mkdir "%~dp0dist\windows"
if not exist "%~dp0build\windows" mkdir "%~dp0build\windows"
if not exist "%~dp0dist" mkdir "%~dp0dist"

echo === SAJ_PDM30_Gestor.exe ===
pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "SAJ_PDM30_Gestor" ^
  --distpath "%~dp0dist\windows" ^
  --workpath "%~dp0build\windows" ^
  --specpath "%~dp0build\windows" ^
  --paths "%~dp0" ^
  --add-data "%~dp0param_lists;param_lists" ^
  --hidden-import "serial.tools.list_ports" ^
  --hidden-import "models" ^
  --hidden-import "storage" ^
  --hidden-import "profiles" ^
  --hidden-import "gui" ^
  --hidden-import "gui.app" ^
  --hidden-import "comms" ^
  --hidden-import "comms.serial_client" ^
  --hidden-import "comms.mqtt_client" ^
  --hidden-import "comms.bluetooth_client" ^
  --hidden-import "comms.ble_nus_client" ^
  --hidden-import "comms.dummy_client" ^
  --hidden-import "comms.base" ^
  --collect-submodules "comms" ^
  --collect-submodules "gui" ^
  --collect-all customtkinter ^
  "%~dp0main.py"

echo === MULTI_VDF_HMI_Flasher.exe ===
pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "MULTI_VDF_HMI_Flasher" ^
  --distpath "%~dp0dist\windows" ^
  --workpath "%~dp0build\windows" ^
  --specpath "%~dp0build\windows" ^
  --paths "%~dp0" ^
  --hidden-import "serial.tools.list_ports" ^
  --hidden-import "flasher" ^
  --hidden-import "flasher.gui" ^
  --hidden-import "flasher.github_releases" ^
  --hidden-import "flasher.flash_worker" ^
  --hidden-import "esptool" ^
  --collect-submodules "flasher" ^
  --collect-all customtkinter ^
  --collect-all esptool ^
  --collect-all serial ^
  "%~dp0run_flasher.py"

if exist "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" (
  copy /Y "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" "%~dp0dist\SAJ_PDM30_Gestor.exe" >nul
)
if exist "%~dp0dist\windows\MULTI_VDF_HMI_Flasher.exe" (
  copy /Y "%~dp0dist\windows\MULTI_VDF_HMI_Flasher.exe" "%~dp0dist\MULTI_VDF_HMI_Flasher.exe" >nul
)

(
echo MULTI_VDF_HMI - ejecutables Windows
echo ===================================
echo.
echo SAJ_PDM30_Gestor.exe     - app de campo
echo MULTI_VDF_HMI_Flasher.exe - flasheo de firmwares desde GitHub
echo.
echo Si Windows SmartScreen avisa: Mas informacion -^> Ejecutar de todas formas
echo (binario no firmado).
echo.
echo Generado con: desktop_app\build_windows.bat
) > "%~dp0dist\windows\LEEME.txt"

echo.
if not exist "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" (
  echo ERROR: falta SAJ_PDM30_Gestor.exe
  exit /b 1
)
if not exist "%~dp0dist\windows\MULTI_VDF_HMI_Flasher.exe" (
  echo ERROR: falta MULTI_VDF_HMI_Flasher.exe
  exit /b 1
)
echo === Build Windows listo ===
dir "%~dp0dist\windows\*.exe"
echo.
endlocal
exit /b 0

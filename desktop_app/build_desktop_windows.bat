@echo off
REM Build VarioField desktop for Windows (Electron + PyInstaller + Expo web)
REM Run on Windows x64 with Node.js + Python 3.12
setlocal EnableExtensions
cd /d "%~dp0"
set EXPO_PUBLIC_ENV=production

echo === VarioField 0.3.2 — Windows production build ===
echo === 1) Python backend .exe ===
if not exist "%~dp0.venv\Scripts\python.exe" (
  python -m venv "%~dp0.venv"
)
call "%~dp0.venv\Scripts\activate.bat"
python -m pip install -U pip wheel
pip install -r "%~dp0requirements.txt"
pip install -r "%~dp0backend\requirements.txt"
pip install pyinstaller

if not exist "%~dp0electron\resources\backend" mkdir "%~dp0electron\resources\backend"
if not exist "%~dp0electron\resources\ui" mkdir "%~dp0electron\resources\ui"

pyinstaller --noconfirm --clean ^
  --onefile ^
  --name multi_vdf_backend ^
  --paths "%~dp0" ^
  --distpath "%~dp0electron\resources\backend" ^
  --workpath "%~dp0build\pyi" ^
  --specpath "%~dp0build\pyi" ^
  --console ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import backend.main ^
  --hidden-import backend.session ^
  --hidden-import backend.schemas ^
  --hidden-import comms ^
  --hidden-import comms.serial_client ^
  --hidden-import comms.mqtt_client ^
  --hidden-import comms.bluetooth_client ^
  --hidden-import comms.ble_nus_client ^
  --hidden-import comms.dummy_client ^
  --hidden-import serial.tools.list_ports ^
  --collect-all bleak ^
  "%~dp0backend\main.py"

echo === 2) Expo web UI (production) ===
cd /d "%~dp0frontend"
if not exist node_modules call npm install
set EXPO_PUBLIC_ENV=production
call npx expo export --platform web --output-dir dist --clear
cd /d "%~dp0"
xcopy /E /I /Y "%~dp0frontend\dist\*" "%~dp0electron\resources\ui\"

echo === 3) Electron NSIS installer ===
cd /d "%~dp0electron"
if not exist node_modules call npm install
call npx electron-builder --win nsis
cd /d "%~dp0"

echo.
echo === VarioField Windows build listo ===
dir "%~dp0electron\dist\*.exe"
echo Instalador: electron\dist\VarioField-Setup-0.3.2.exe
echo.
endlocal

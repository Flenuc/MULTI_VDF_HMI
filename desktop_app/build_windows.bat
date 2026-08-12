@echo off
REM Genera ejecutable standalone Windows con PyInstaller
REM Ejecutar EN Windows (no se puede generar .exe nativo desde Linux facilmente)
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
  python -m venv "%~dp0.venv"
)
call "%~dp0.venv\Scripts\activate.bat"
python -m pip install -U pip
pip install -r "%~dp0requirements.txt"
pip install pyinstaller

if not exist "%~dp0dist\windows" mkdir "%~dp0dist\windows"
if not exist "%~dp0build\windows" mkdir "%~dp0build\windows"
if not exist "%~dp0dist" mkdir "%~dp0dist"

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
  --hidden-import "serial_client" ^
  --hidden-import "gui_app" ^
  --collect-all customtkinter ^
  "%~dp0main.py"

if exist "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" (
  copy /Y "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" "%~dp0dist\SAJ_PDM30_Gestor.exe" >nul
)

echo.
echo === Build Windows listo ===
echo Ejecutable en dist\windows\  o  dist\SAJ_PDM30_Gestor.exe
echo Tambien puedes usar: run_windows.bat
pause
endlocal

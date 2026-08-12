@echo off
REM Lanzador Windows — SAJ PDM-30 Gestor de Parametros
setlocal EnableExtensions
cd /d "%~dp0"

REM Prefer prebuilt EXE
if exist "%~dp0dist\SAJ_PDM30_Gestor.exe" (
  start "" "%~dp0dist\SAJ_PDM30_Gestor.exe" %*
  exit /b 0
)
if exist "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" (
  start "" "%~dp0dist\windows\SAJ_PDM30_Gestor.exe" %*
  exit /b 0
)

REM Fallback: venv + python
where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python no esta en el PATH. Instala Python 3.10+ desde python.org
  echo y marca "Add Python to PATH".
  pause
  exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv "%~dp0.venv"
  call "%~dp0.venv\Scripts\activate.bat"
  python -m pip install -U pip
  pip install -r "%~dp0requirements.txt"
) else (
  call "%~dp0.venv\Scripts\activate.bat"
)

python "%~dp0main.py" %*
if errorlevel 1 pause
endlocal

@echo off
REM Post-instalacion: pip + dependencias de VarioField (API + UI web)
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === VarioField — instalando dependencias ===
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PY (
  if exist "%LocalAppData%\MULTI_VDF_HMI\Python312\python.exe" set "PY=%LocalAppData%\MULTI_VDF_HMI\Python312\python.exe"
)

if not defined PY (
  echo ERROR: Python no encontrado tras la instalacion.
  exit /b 1
)

echo Usando: %PY%
%PY% -c "import sys; print(sys.version)"

echo.
echo Actualizando pip...
%PY% -m ensurepip --upgrade >nul 2>&1
%PY% -m pip install -U pip wheel

echo.
echo Instalando dependencias (fastapi, uvicorn, serial, mqtt, bleak)...
%PY% -m pip install -r "%~dp0requirements-variofield.txt"
if errorlevel 1 (
  echo ERROR: fallo pip install
  exit /b 1
)

echo.
echo Comprobando imports...
%PY% -c "import fastapi, uvicorn, serial, paho.mqtt.client, bleak, pydantic; print('OK')"
if errorlevel 1 (
  echo ERROR: faltan modulos
  exit /b 1
)

if not exist "%~dp0ui\index.html" (
  echo AVISO: no se encontro ui\index.html — la interfaz web no se servira.
) else (
  echo UI: ui\index.html OK
)

echo.
echo === Dependencias listas ===
echo Arranque con Launch_VarioField.bat
exit /b 0

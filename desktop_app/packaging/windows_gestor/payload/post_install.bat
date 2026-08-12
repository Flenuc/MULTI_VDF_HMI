@echo off
REM Post-instalacion: pip + dependencias del Gestor
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === SAJ_PDM30_Gestor — instalando dependencias ===
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
echo Instalando dependencias (customtkinter, serial, mqtt, bleak)...
%PY% -m pip install -r "%~dp0requirements-gestor.txt"
if errorlevel 1 (
  echo ERROR: fallo pip install
  exit /b 1
)

echo.
echo Comprobando imports...
%PY% -c "import customtkinter, serial, paho.mqtt.client, bleak; import tkinter; print('OK')"
if errorlevel 1 (
  echo ERROR: faltan modulos (¿Python sin Tcl/Tk o bleak?)
  exit /b 1
)

echo.
echo === Dependencias listas ===
exit /b 0

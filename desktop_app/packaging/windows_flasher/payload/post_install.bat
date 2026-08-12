@echo off
REM Post-instalacion: asegura pip + dependencias del flasher
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo === MULTI_VDF_HMI Flasher — instalando dependencias ===
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
echo Instalando customtkinter, pyserial, esptool...
%PY% -m pip install -r "%~dp0requirements-flasher.txt"
if errorlevel 1 (
  echo ERROR: falló pip install
  exit /b 1
)

echo.
echo Comprobando imports...
%PY% -c "import customtkinter, serial, esptool; print('OK:', customtkinter.__version__ if hasattr(customtkinter,'__version__') else 'ctk')"
if errorlevel 1 (
  echo ERROR: faltan modulos (¿Python sin Tcl/Tk?)
  exit /b 1
)

echo.
echo === Dependencias listas ===
exit /b 0

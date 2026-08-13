@echo off
setlocal
cd /d "%~dp0"

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
  echo No se encontro Python. Ejecute post_install.bat o reinstale el Setup.
  pause
  exit /b 1
)

REM Consola visible: cierra la ventana para parar el backend
title VarioField
%PY% "%~dp0run_variofield.py"
if errorlevel 1 (
  echo.
  echo Error al arrancar. Pruebe post_install.bat si faltan dependencias.
  pause
)
exit /b %ERRORLEVEL%

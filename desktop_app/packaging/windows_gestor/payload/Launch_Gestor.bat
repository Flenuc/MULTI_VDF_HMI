@echo off
setlocal
cd /d "%~dp0"

set "PYW="
where pythonw >nul 2>&1 && set "PYW=pythonw"
if not defined PYW (
  if exist "%LocalAppData%\Programs\Python\Python312\pythonw.exe" set "PYW=%LocalAppData%\Programs\Python\Python312\pythonw.exe"
)
if not defined PYW (
  if exist "%LocalAppData%\MULTI_VDF_HMI\Python312\pythonw.exe" set "PYW=%LocalAppData%\MULTI_VDF_HMI\Python312\pythonw.exe"
)

if defined PYW (
  start "" "%PYW%" "%~dp0main.py"
  exit /b 0
)

where py >nul 2>&1 && (
  start "" py -3 "%~dp0main.py"
  exit /b 0
)

where python >nul 2>&1 && (
  start "" python "%~dp0main.py"
  exit /b 0
)

echo No se encontro Python. Ejecute post_install.bat o reinstale el Setup.
pause
exit /b 1

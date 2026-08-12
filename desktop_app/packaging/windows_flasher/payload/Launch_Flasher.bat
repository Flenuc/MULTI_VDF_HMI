@echo off
setlocal
cd /d "%~dp0"

REM Prefer pythonw (no console), fallback to python / py launcher
set "PYW="
where pythonw >nul 2>&1 && set "PYW=pythonw"
if not defined PYW (
  if exist "%LocalAppData%\Programs\Python\Python312\pythonw.exe" set "PYW=%LocalAppData%\Programs\Python\Python312\pythonw.exe"
)
if not defined PYW (
  if exist "%LocalAppData%\MULTI_VDF_HMI\Python312\pythonw.exe" set "PYW=%LocalAppData%\MULTI_VDF_HMI\Python312\pythonw.exe"
)

if defined PYW (
  start "" "%PYW%" "%~dp0run_flasher.py"
  exit /b 0
)

where py >nul 2>&1 && (
  start "" py -3 -c "import runpy; runpy.run_path(r'%~dp0run_flasher.py', run_name='__main__')"
  exit /b 0
)

where python >nul 2>&1 && (
  start "" python "%~dp0run_flasher.py"
  exit /b 0
)

echo No se encontro Python. Ejecute setup de nuevo o instale Python 3.12+ con Tcl/Tk.
pause
exit /b 1

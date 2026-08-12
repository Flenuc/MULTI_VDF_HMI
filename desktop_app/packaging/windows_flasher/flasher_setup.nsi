; MULTI_VDF_HMI Flasher — Windows Setup (NSIS)
; Compilable en Linux con makensis → genera MULTI_VDF_HMI_Flasher_Setup.exe

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "WinMessages.nsh"

Name "MULTI_VDF_HMI Flasher"
OutFile "MULTI_VDF_HMI_Flasher_Setup.exe"
Unicode true
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\MULTI_VDF_HMI\Flasher"
InstallDirRegKey HKCU "Software\MULTI_VDF_HMI\Flasher" "InstallDir"
SetCompressor /SOLID lzma

!define PRODUCT_NAME "MULTI_VDF_HMI Flasher"
!define PRODUCT_VERSION "0.1.0"
!define PRODUCT_PUBLISHER "Flenuc"
!define PRODUCT_WEB "https://github.com/Flenuc/MULTI_VDF_HMI"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEPAGE_TITLE "Instalar ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instala el flasher de firmwares MULTI_VDF_HMI.$\r$\n$\r$\nSi no hay Python 3.12 en el PC, se instalara automaticamente (con Tcl/Tk para la GUI).$\r$\n$\r$\nSe necesita conexion a Internet la primera vez para pip (customtkinter, esptool)."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Launch_Flasher.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir el Flasher ahora"
!define MUI_FINISHPAGE_LINK "GitHub: Flenuc/MULTI_VDF_HMI"
!define MUI_FINISHPAGE_LINK_LOCATION "${PRODUCT_WEB}"

Var PythonExe
Var NeedPythonInstall

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

VIProductVersion "0.1.0.0"
VIAddVersionKey /LANG=0 "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=0 "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=0 "FileDescription" "Instalador flasher firmwares MULTI_VDF_HMI"
VIAddVersionKey /LANG=0 "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=0 "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=0 "LegalCopyright" "${PRODUCT_PUBLISHER}"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Este instalador es solo para Windows 64-bit."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Function FindPython
  StrCpy $PythonExe ""
  StrCpy $NeedPythonInstall "1"

  ; 1) py launcher
  nsExec::ExecToStack 'cmd /c where py >nul 2>&1'
  Pop $0
  ${If} $0 == 0
    nsExec::ExecToStack 'cmd /c py -3 -c "import sys; assert sys.version_info>=(3,10); import tkinter; print(sys.executable)"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      ; use py -3 as runner marker
      StrCpy $PythonExe "py -3"
      StrCpy $NeedPythonInstall "0"
      Return
    ${EndIf}
  ${EndIf}

  ; 2) python on PATH
  nsExec::ExecToStack 'cmd /c where python >nul 2>&1'
  Pop $0
  ${If} $0 == 0
    nsExec::ExecToStack 'cmd /c python -c "import sys; assert sys.version_info>=(3,10); import tkinter; print(sys.executable)"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      StrCpy $PythonExe "python"
      StrCpy $NeedPythonInstall "0"
      Return
    ${EndIf}
  ${EndIf}

  ; 3) default user install location
  IfFileExists "$LOCALAPPDATA\Programs\Python\Python312\python.exe" 0 +3
    StrCpy $PythonExe "$LOCALAPPDATA\Programs\Python\Python312\python.exe"
    StrCpy $NeedPythonInstall "0"
FunctionEnd

Section "Flasher" SecMain
  SetOutPath "$INSTDIR"

  DetailPrint "Copiando archivos de la aplicacion..."
  File "payload\run_flasher.py"
  File "payload\Launch_Flasher.bat"
  File "payload\post_install.bat"
  File "payload\requirements-flasher.txt"
  File "payload\LEEME.txt"
  SetOutPath "$INSTDIR\flasher"
  File "payload\flasher\__init__.py"
  File "payload\flasher\gui.py"
  File "payload\flasher\flash_worker.py"
  File "payload\flasher\github_releases.py"
  SetOutPath "$INSTDIR"

  Call FindPython

  ${If} $NeedPythonInstall == "1"
    DetailPrint "Python 3.12 no encontrado — instalando (usuario, con Tcl/Tk)..."
    File "payload\python-3.12.10-amd64.exe"
    ; Instalacion silenciosa solo para el usuario actual
    nsExec::ExecToLog '"$INSTDIR\python-3.12.10-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0 Include_dev=0 Include_launcher=1 Include_pip=1 Include_tcltk=1 SimpleInstall=1 TargetDir="$LOCALAPPDATA\Programs\Python\Python312"'
    Pop $0
    DetailPrint "Instalador Python codigo: $0"
    Sleep 2000
    StrCpy $PythonExe "$LOCALAPPDATA\Programs\Python\Python312\python.exe"
    IfFileExists "$PythonExe" +3 0
      MessageBox MB_ICONEXCLAMATION "No se pudo instalar Python automaticamente.$\r$\nInstale Python 3.12+ desde python.org (marque tcl/tk y pip) y vuelva a ejecutar este setup."
      ; continue anyway — post_install may still find something
    Delete "$INSTDIR\python-3.12.10-amd64.exe"
  ${EndIf}

  DetailPrint "Instalando dependencias Python (pip)..."
  nsExec::ExecToLog 'cmd /c ""$INSTDIR\post_install.bat""'
  Pop $0
  ${If} $0 != 0
    DetailPrint "post_install devolvio $0 — puede reintentar ejecutando post_install.bat en $INSTDIR"
    MessageBox MB_ICONEXCLAMATION|MB_OK "La instalacion de dependencias tuvo avisos (codigo $0).$\r$\nSi el flasher no arranca, abra una consola en:$\r$\n$INSTDIR$\r$\ny ejecute post_install.bat (necesita Internet)."
  ${EndIf}

  ; Atajos
  CreateDirectory "$SMPROGRAMS\MULTI_VDF_HMI"
  CreateShortCut "$SMPROGRAMS\MULTI_VDF_HMI\Flasher.lnk" "$INSTDIR\Launch_Flasher.bat" "" "$INSTDIR\Launch_Flasher.bat" 0
  CreateShortCut "$DESKTOP\MULTI_VDF_HMI Flasher.lnk" "$INSTDIR\Launch_Flasher.bat" "" "$INSTDIR\Launch_Flasher.bat" 0

  ; Registro / desinstalador
  WriteRegStr HKCU "Software\MULTI_VDF_HMI\Flasher" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher" "URLInfoAbout" "${PRODUCT_WEB}"
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\MULTI_VDF_HMI Flasher.lnk"
  Delete "$SMPROGRAMS\MULTI_VDF_HMI\Flasher.lnk"
  RMDir "$SMPROGRAMS\MULTI_VDF_HMI"

  Delete "$INSTDIR\run_flasher.py"
  Delete "$INSTDIR\Launch_Flasher.bat"
  Delete "$INSTDIR\post_install.bat"
  Delete "$INSTDIR\requirements-flasher.txt"
  Delete "$INSTDIR\LEEME.txt"
  Delete "$INSTDIR\python-3.12.10-amd64.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\flasher"
  RMDir /r "$INSTDIR\__pycache__"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "Software\MULTI_VDF_HMI\Flasher"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MULTI_VDF_HMI_Flasher"
  ; No desinstala Python del sistema (puede usarse por otras apps)
SectionEnd

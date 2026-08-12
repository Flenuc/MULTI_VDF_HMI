; SAJ_PDM30_Gestor — Windows Setup (NSIS)
; Compilable en Linux con makensis → SAJ_PDM30_Gestor_Setup.exe

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "WinMessages.nsh"

Name "SAJ PDM-30 Gestor"
OutFile "SAJ_PDM30_Gestor_Setup.exe"
Unicode true
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\MULTI_VDF_HMI\Gestor"
InstallDirRegKey HKCU "Software\MULTI_VDF_HMI\Gestor" "InstallDir"
SetCompressor /SOLID lzma

!define PRODUCT_NAME "SAJ PDM-30 Gestor"
!define PRODUCT_VERSION "0.1.0"
!define PRODUCT_PUBLISHER "Flenuc"
!define PRODUCT_WEB "https://github.com/Flenuc/MULTI_VDF_HMI"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEPAGE_TITLE "Instalar ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instala la app de campo SAJ PDM-30 Gestor (MULTI_VDF_HMI).$\r$\n$\r$\nSi no hay Python 3.12 en el PC, se instalara automaticamente (con Tcl/Tk para la GUI).$\r$\n$\r$\nSe necesita conexion a Internet la primera vez para pip (customtkinter, mqtt, bleak, etc.)."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Launch_Gestor.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir el Gestor ahora"
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
VIAddVersionKey /LANG=0 "FileDescription" "Instalador SAJ PDM-30 Gestor (campo)"
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

  nsExec::ExecToStack 'cmd /c where py >nul 2>&1'
  Pop $0
  ${If} $0 == 0
    nsExec::ExecToStack 'cmd /c py -3 -c "import sys; assert sys.version_info>=(3,10); import tkinter; print(sys.executable)"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      StrCpy $PythonExe "py -3"
      StrCpy $NeedPythonInstall "0"
      Return
    ${EndIf}
  ${EndIf}

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

  IfFileExists "$LOCALAPPDATA\Programs\Python\Python312\python.exe" 0 +3
    StrCpy $PythonExe "$LOCALAPPDATA\Programs\Python\Python312\python.exe"
    StrCpy $NeedPythonInstall "0"
FunctionEnd

Section "Gestor" SecMain
  SetOutPath "$INSTDIR"

  DetailPrint "Copiando archivos de la aplicacion..."
  File "payload\main.py"
  File "payload\models.py"
  File "payload\storage.py"
  File "payload\profiles.py"
  File "payload\Launch_Gestor.bat"
  File "payload\post_install.bat"
  File "payload\requirements-gestor.txt"
  File "payload\LEEME.txt"

  SetOutPath "$INSTDIR\gui"
  File "payload\gui\__init__.py"
  File "payload\gui\app.py"

  SetOutPath "$INSTDIR\comms"
  File "payload\comms\__init__.py"
  File "payload\comms\base.py"
  File "payload\comms\serial_client.py"
  File "payload\comms\mqtt_client.py"
  File "payload\comms\bluetooth_client.py"
  File "payload\comms\ble_nus_client.py"
  File "payload\comms\dummy_client.py"
  File "payload\comms\ws_client.py"

  SetOutPath "$INSTDIR\param_lists"
  File "payload\param_lists\*.json"

  SetOutPath "$INSTDIR\config"
  File "payload\config\connection_profiles.example.json"

  SetOutPath "$INSTDIR"

  Call FindPython

  ${If} $NeedPythonInstall == "1"
    DetailPrint "Python 3.12 no encontrado — instalando (usuario, con Tcl/Tk)..."
    File "payload\python-3.12.10-amd64.exe"
    nsExec::ExecToLog '"$INSTDIR\python-3.12.10-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0 Include_dev=0 Include_launcher=1 Include_pip=1 Include_tcltk=1 SimpleInstall=1 TargetDir="$LOCALAPPDATA\Programs\Python\Python312"'
    Pop $0
    DetailPrint "Instalador Python codigo: $0"
    Sleep 2000
    StrCpy $PythonExe "$LOCALAPPDATA\Programs\Python\Python312\python.exe"
    IfFileExists "$PythonExe" +3 0
      MessageBox MB_ICONEXCLAMATION "No se pudo instalar Python automaticamente.$\r$\nInstale Python 3.12+ desde python.org (marque tcl/tk y pip) y vuelva a ejecutar este setup."
    Delete "$INSTDIR\python-3.12.10-amd64.exe"
  ${EndIf}

  DetailPrint "Instalando dependencias Python (pip)..."
  nsExec::ExecToLog 'cmd /c ""$INSTDIR\post_install.bat""'
  Pop $0
  ${If} $0 != 0
    DetailPrint "post_install devolvio $0 — puede reintentar con post_install.bat en $INSTDIR"
    MessageBox MB_ICONEXCLAMATION|MB_OK "La instalacion de dependencias tuvo avisos (codigo $0).$\r$\nSi el Gestor no arranca, abra:$\r$\n$INSTDIR$\r$\ny ejecute post_install.bat (necesita Internet)."
  ${EndIf}

  CreateDirectory "$SMPROGRAMS\MULTI_VDF_HMI"
  CreateShortCut "$SMPROGRAMS\MULTI_VDF_HMI\SAJ PDM-30 Gestor.lnk" "$INSTDIR\Launch_Gestor.bat" "" "$INSTDIR\Launch_Gestor.bat" 0
  CreateShortCut "$DESKTOP\SAJ PDM-30 Gestor.lnk" "$INSTDIR\Launch_Gestor.bat" "" "$INSTDIR\Launch_Gestor.bat" 0

  WriteRegStr HKCU "Software\MULTI_VDF_HMI\Gestor" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor" "URLInfoAbout" "${PRODUCT_WEB}"
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\SAJ PDM-30 Gestor.lnk"
  Delete "$SMPROGRAMS\MULTI_VDF_HMI\SAJ PDM-30 Gestor.lnk"
  RMDir "$SMPROGRAMS\MULTI_VDF_HMI"

  Delete "$INSTDIR\main.py"
  Delete "$INSTDIR\models.py"
  Delete "$INSTDIR\storage.py"
  Delete "$INSTDIR\profiles.py"
  Delete "$INSTDIR\Launch_Gestor.bat"
  Delete "$INSTDIR\post_install.bat"
  Delete "$INSTDIR\requirements-gestor.txt"
  Delete "$INSTDIR\LEEME.txt"
  Delete "$INSTDIR\python-3.12.10-amd64.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\gui"
  RMDir /r "$INSTDIR\comms"
  RMDir /r "$INSTDIR\param_lists"
  RMDir /r "$INSTDIR\config"
  RMDir /r "$INSTDIR\__pycache__"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "Software\MULTI_VDF_HMI\Gestor"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SAJ_PDM30_Gestor"
SectionEnd

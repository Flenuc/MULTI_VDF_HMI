; VarioField — Windows Setup (NSIS)
; Compilable en Linux con makensis → VarioField-Setup-0.3.2.exe
; Empaqueta: backend Python + UI web estática + instalador Python oficial.

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "WinMessages.nsh"

Name "VarioField"
OutFile "VarioField-Setup-0.3.2.exe"
Unicode true
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\MULTI_VDF_HMI\VarioField"
InstallDirRegKey HKCU "Software\MULTI_VDF_HMI\VarioField" "InstallDir"
SetCompressor /SOLID lzma

!define PRODUCT_NAME "VarioField"
!define PRODUCT_VERSION "0.3.2"
!define PRODUCT_PUBLISHER "Flenuc"
!define PRODUCT_WEB "https://github.com/Flenuc/MULTI_VDF_HMI"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEPAGE_TITLE "Instalar ${PRODUCT_NAME} ${PRODUCT_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instala VarioField (app de campo MULTI_VDF_HMI).$\r$\n$\r$\nIncluye el backend Python y la interfaz web.$\r$\n$\r$\nSi no hay Python 3.12, se instalara automaticamente.$\r$\n$\r$\nSe necesita Internet la primera vez para pip (fastapi, uvicorn, bleak, etc.)."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Launch_VarioField.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir VarioField ahora"
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

VIProductVersion "0.3.2.0"
VIAddVersionKey /LANG=0 "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=0 "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=0 "FileDescription" "Instalador VarioField (campo)"
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
    nsExec::ExecToStack 'cmd /c py -3 -c "import sys; assert sys.version_info>=(3,10); print(sys.executable)"'
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
    nsExec::ExecToStack 'cmd /c python -c "import sys; assert sys.version_info>=(3,10); print(sys.executable)"'
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

Section "VarioField" SecMain
  SetOutPath "$INSTDIR"

  DetailPrint "Copiando aplicacion..."
  File "payload\run_variofield.py"
  File "payload\Launch_VarioField.bat"
  File "payload\post_install.bat"
  File "payload\requirements-variofield.txt"
  File "payload\LEEME.txt"
  File "payload\models.py"
  File "payload\profiles.py"
  File "payload\storage.py"

  SetOutPath "$INSTDIR\backend"
  File "payload\backend\__init__.py"
  File "payload\backend\__main__.py"
  File "payload\backend\main.py"
  File "payload\backend\session.py"
  File "payload\backend\schemas.py"
  File "payload\backend\param_api.py"
  File "payload\backend\requirements.txt"

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

  ; UI web estatica (Expo export) — recursive
  SetOutPath "$INSTDIR\ui"
  File /r "payload\ui\*.*"

  SetOutPath "$INSTDIR"

  Call FindPython

  ${If} $NeedPythonInstall == "1"
    DetailPrint "Python 3.12 no encontrado — instalando (usuario)..."
    File "payload\python-3.12.10-amd64.exe"
    nsExec::ExecToLog '"$INSTDIR\python-3.12.10-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0 Include_dev=0 Include_launcher=1 Include_pip=1 Include_tcltk=0 SimpleInstall=1 TargetDir="$LOCALAPPDATA\Programs\Python\Python312"'
    Pop $0
    DetailPrint "Instalador Python codigo: $0"
    Sleep 2000
    StrCpy $PythonExe "$LOCALAPPDATA\Programs\Python\Python312\python.exe"
    IfFileExists "$PythonExe" +3 0
      MessageBox MB_ICONEXCLAMATION "No se pudo instalar Python automaticamente.$\r$\nInstale Python 3.12+ desde python.org (con pip) y vuelva a ejecutar este setup."
    Delete "$INSTDIR\python-3.12.10-amd64.exe"
  ${EndIf}

  DetailPrint "Instalando dependencias Python (pip)..."
  nsExec::ExecToLog 'cmd /c ""$INSTDIR\post_install.bat""'
  Pop $0
  ${If} $0 != 0
    DetailPrint "post_install devolvio $0 — puede reintentar con post_install.bat en $INSTDIR"
    MessageBox MB_ICONEXCLAMATION|MB_OK "La instalacion de dependencias tuvo avisos (codigo $0).$\r$\nSi VarioField no arranca, abra:$\r$\n$INSTDIR$\r$\ny ejecute post_install.bat (necesita Internet)."
  ${EndIf}

  CreateDirectory "$SMPROGRAMS\MULTI_VDF_HMI"
  CreateShortCut "$SMPROGRAMS\MULTI_VDF_HMI\VarioField.lnk" "$INSTDIR\Launch_VarioField.bat" "" "$INSTDIR\Launch_VarioField.bat" 0
  CreateShortCut "$DESKTOP\VarioField.lnk" "$INSTDIR\Launch_VarioField.bat" "" "$INSTDIR\Launch_VarioField.bat" 0

  WriteRegStr HKCU "Software\MULTI_VDF_HMI\VarioField" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField" "URLInfoAbout" "${PRODUCT_WEB}"
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\VarioField.lnk"
  Delete "$SMPROGRAMS\MULTI_VDF_HMI\VarioField.lnk"
  RMDir "$SMPROGRAMS\MULTI_VDF_HMI"

  Delete "$INSTDIR\run_variofield.py"
  Delete "$INSTDIR\Launch_VarioField.bat"
  Delete "$INSTDIR\post_install.bat"
  Delete "$INSTDIR\requirements-variofield.txt"
  Delete "$INSTDIR\LEEME.txt"
  Delete "$INSTDIR\models.py"
  Delete "$INSTDIR\profiles.py"
  Delete "$INSTDIR\storage.py"
  Delete "$INSTDIR\python-3.12.10-amd64.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\backend"
  RMDir /r "$INSTDIR\comms"
  RMDir /r "$INSTDIR\param_lists"
  RMDir /r "$INSTDIR\config"
  RMDir /r "$INSTDIR\ui"
  RMDir /r "$INSTDIR\__pycache__"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "Software\MULTI_VDF_HMI\VarioField"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioField"
SectionEnd

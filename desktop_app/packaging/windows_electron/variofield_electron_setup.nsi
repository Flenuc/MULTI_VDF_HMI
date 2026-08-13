; VarioField Electron — Windows Setup (NSIS)
; Compilable en Linux con makensis. Empaqueta Electron win32-x64 + Python embed + UI.
; El stage se genera con build_variofield_windows_electron_setup.sh → stage/VarioField

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"

Name "VarioField"
OutFile "VarioField-Setup-0.3.2.exe"
Unicode true
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\MULTI_VDF_HMI\VarioField"
InstallDirRegKey HKCU "Software\MULTI_VDF_HMI\VarioFieldElectron" "InstallDir"
SetCompressor /SOLID lzma

!define PRODUCT_NAME "VarioField"
!define PRODUCT_VERSION "0.3.2"
!define PRODUCT_PUBLISHER "Flenuc"
!define PRODUCT_WEB "https://github.com/Flenuc/MULTI_VDF_HMI"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEPAGE_TITLE "Instalar ${PRODUCT_NAME} ${PRODUCT_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instala VarioField con shell Electron nativo para Windows.$\r$\n$\r$\nIncluye el motor Chromium embebido, el backend Python portable y la interfaz de campo.$\r$\n$\r$\nNo requiere Python ni Node preinstalados."
!define MUI_FINISHPAGE_RUN "$INSTDIR\VarioField.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir VarioField ahora"
!define MUI_FINISHPAGE_LINK "GitHub: Flenuc/MULTI_VDF_HMI"
!define MUI_FINISHPAGE_LINK_LOCATION "${PRODUCT_WEB}"

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
VIAddVersionKey /LANG=0 "FileDescription" "VarioField Electron (campo)"
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

Section "VarioField" SecMain
  SetOutPath "$INSTDIR"
  DetailPrint "Copiando VarioField (Electron + Python + UI)..."
  ; stage/VarioField/* generado por el script de build
  ; Usar \ al final + * (no *.*) para no omitir ficheros sin extensión
  ; (METADATA, LICENSE, version, etc.) — *.* de NSIS los salta.
  File /r "stage\VarioField\"

  CreateDirectory "$SMPROGRAMS\MULTI_VDF_HMI"
  CreateShortCut "$SMPROGRAMS\MULTI_VDF_HMI\VarioField.lnk" "$INSTDIR\VarioField.exe" "" "$INSTDIR\VarioField.exe" 0
  CreateShortCut "$DESKTOP\VarioField.lnk" "$INSTDIR\VarioField.exe" "" "$INSTDIR\VarioField.exe" 0

  WriteRegStr HKCU "Software\MULTI_VDF_HMI\VarioFieldElectron" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "URLInfoAbout" "${PRODUCT_WEB}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "DisplayIcon" "$INSTDIR\VarioField.exe"
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\VarioField.lnk"
  Delete "$SMPROGRAMS\MULTI_VDF_HMI\VarioField.lnk"
  RMDir "$SMPROGRAMS\MULTI_VDF_HMI"

  ; Borrar todo el arbol de instalacion
  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "Software\MULTI_VDF_HMI\VarioFieldElectron"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VarioFieldElectron"
SectionEnd

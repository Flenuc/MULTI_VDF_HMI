#!/usr/bin/env bash
# Genera MULTI_VDF_HMI_Flasher_Setup.exe (instalador NSIS para Windows x64)
# Se puede ejecutar en Linux (aarch64/x86_64) con el paquete `nsis`.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$DIR/packaging/windows_flasher"
PAYLOAD="$PKG/payload"
OUT_DIR="$DIR/dist/windows"
PYTHON_VER="3.12.10"
PYTHON_EXE="python-${PYTHON_VER}-amd64.exe"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/${PYTHON_EXE}"

echo "=== Build Windows Setup (Flasher) ==="

if ! command -v makensis >/dev/null 2>&1; then
  echo "ERROR: makensis no encontrado. Instale: sudo apt install nsis"
  exit 1
fi

mkdir -p "$PAYLOAD/flasher" "$OUT_DIR" "$PKG/cache"

# Sync app sources from desktop_app
cp -f "$DIR/run_flasher.py" "$PAYLOAD/run_flasher.py"
cp -f "$DIR/flasher/__init__.py" "$PAYLOAD/flasher/"
cp -f "$DIR/flasher/gui.py" "$PAYLOAD/flasher/"
cp -f "$DIR/flasher/flash_worker.py" "$PAYLOAD/flasher/"
cp -f "$DIR/flasher/github_releases.py" "$PAYLOAD/flasher/"
cp -f "$PKG/requirements-flasher.txt" "$PAYLOAD/requirements-flasher.txt"

# Ensure helper scripts exist (written by packaging)
if [[ ! -f "$PAYLOAD/Launch_Flasher.bat" ]]; then
  echo "ERROR: falta $PAYLOAD/Launch_Flasher.bat"
  exit 1
fi
if [[ ! -f "$PAYLOAD/post_install.bat" ]]; then
  echo "ERROR: falta $PAYLOAD/post_install.bat"
  exit 1
fi

# Download official Python Windows installer (cached)
if [[ ! -f "$PKG/cache/$PYTHON_EXE" ]]; then
  echo "Descargando Python ${PYTHON_VER} Windows x64..."
  curl -fL --retry 3 -o "$PKG/cache/$PYTHON_EXE.partial" "$PYTHON_URL"
  mv "$PKG/cache/$PYTHON_EXE.partial" "$PKG/cache/$PYTHON_EXE"
fi
cp -f "$PKG/cache/$PYTHON_EXE" "$PAYLOAD/$PYTHON_EXE"
ls -lh "$PAYLOAD/$PYTHON_EXE"

echo "Compilando NSIS..."
# makensis escribe OutFile relativo al .nsi o cwd
cd "$PKG"
makensis -V2 flasher_setup.nsi

if [[ ! -f "$PKG/MULTI_VDF_HMI_Flasher_Setup.exe" ]]; then
  echo "ERROR: no se genero el Setup.exe"
  exit 1
fi

mv -f "$PKG/MULTI_VDF_HMI_Flasher_Setup.exe" "$OUT_DIR/MULTI_VDF_HMI_Flasher_Setup.exe"
# Copia de conveniencia
cp -f "$OUT_DIR/MULTI_VDF_HMI_Flasher_Setup.exe" "$DIR/dist/MULTI_VDF_HMI_Flasher_Setup.exe"

# LEEME en dist/windows
cat > "$OUT_DIR/LEEME_SETUP.txt" << EOF
MULTI_VDF_HMI_Flasher_Setup.exe
================================
Instalador Windows x64 del flasher de firmwares.

1. Copie el .exe a un PC Windows 10/11 64-bit
2. Ejecutelo (si SmartScreen avisa: Mas info → Ejecutar de todas formas)
3. Si no hay Python, lo instala el propio setup
4. Primera vez: Internet para pip (customtkinter / esptool)

Atajos: Escritorio y menu Inicio → MULTI_VDF_HMI Flasher
EOF

# No dejar el instalador de Python suelto en payload versionado
rm -f "$PAYLOAD/$PYTHON_EXE"

echo ""
echo "=== Setup listo ==="
ls -lh "$OUT_DIR/MULTI_VDF_HMI_Flasher_Setup.exe"
file "$OUT_DIR/MULTI_VDF_HMI_Flasher_Setup.exe" || true
echo "Ruta: $OUT_DIR/MULTI_VDF_HMI_Flasher_Setup.exe"

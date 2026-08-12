#!/usr/bin/env bash
# Genera SAJ_PDM30_Gestor_Setup.exe (instalador NSIS para Windows x64)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$DIR/packaging/windows_gestor"
PAYLOAD="$PKG/payload"
OUT_DIR="$DIR/dist/windows"
CACHE_DIR="$DIR/packaging/windows_flasher/cache"
PYTHON_VER="3.12.10"
PYTHON_EXE="python-${PYTHON_VER}-amd64.exe"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/${PYTHON_EXE}"

echo "=== Build Windows Setup (Gestor) ==="

if ! command -v makensis >/dev/null 2>&1; then
  echo "ERROR: makensis no encontrado. Instale: sudo apt install nsis"
  exit 1
fi

mkdir -p "$PAYLOAD"/{gui,comms,param_lists,config} "$OUT_DIR" "$CACHE_DIR"

# Sync sources
cp -f "$DIR/main.py" "$PAYLOAD/main.py"
cp -f "$DIR/models.py" "$PAYLOAD/models.py"
cp -f "$DIR/storage.py" "$PAYLOAD/storage.py"
cp -f "$DIR/profiles.py" "$PAYLOAD/profiles.py"
cp -f "$DIR/gui/__init__.py" "$PAYLOAD/gui/"
cp -f "$DIR/gui/app.py" "$PAYLOAD/gui/"
cp -f "$DIR/comms/"*.py "$PAYLOAD/comms/"
cp -f "$DIR/param_lists/"*.json "$PAYLOAD/param_lists/"
cp -f "$DIR/config/connection_profiles.example.json" "$PAYLOAD/config/"
cp -f "$PKG/requirements-gestor.txt" "$PAYLOAD/requirements-gestor.txt"

# Ensure helpers
for f in Launch_Gestor.bat post_install.bat LEEME.txt; do
  if [[ ! -f "$PAYLOAD/$f" ]]; then
    echo "ERROR: falta $PAYLOAD/$f"
    exit 1
  fi
done

# Python installer (shared cache with flasher)
if [[ ! -f "$CACHE_DIR/$PYTHON_EXE" ]]; then
  echo "Descargando Python ${PYTHON_VER} Windows x64..."
  curl -fL --retry 3 -o "$CACHE_DIR/$PYTHON_EXE.partial" "$PYTHON_URL"
  mv "$CACHE_DIR/$PYTHON_EXE.partial" "$CACHE_DIR/$PYTHON_EXE"
fi
cp -f "$CACHE_DIR/$PYTHON_EXE" "$PAYLOAD/$PYTHON_EXE"
ls -lh "$PAYLOAD/$PYTHON_EXE"

echo "Compilando NSIS..."
cd "$PKG"
makensis -V2 gestor_setup.nsi

if [[ ! -f "$PKG/SAJ_PDM30_Gestor_Setup.exe" ]]; then
  echo "ERROR: no se genero el Setup.exe"
  exit 1
fi

mv -f "$PKG/SAJ_PDM30_Gestor_Setup.exe" "$OUT_DIR/SAJ_PDM30_Gestor_Setup.exe"
cp -f "$OUT_DIR/SAJ_PDM30_Gestor_Setup.exe" "$DIR/dist/SAJ_PDM30_Gestor_Setup.exe"

cat > "$OUT_DIR/LEEME_GESTOR_SETUP.txt" << EOF
SAJ_PDM30_Gestor_Setup.exe
==========================
Instalador Windows x64 de la app de campo (Gestor).

1. Copie el .exe a un PC Windows 10/11 64-bit
2. Ejecutelo (SmartScreen: Mas info → Ejecutar de todas formas)
3. Si no hay Python, lo instala el setup
4. Primera vez: Internet para pip

Atajos: Escritorio y menu Inicio → SAJ PDM-30 Gestor
EOF

rm -f "$PAYLOAD/$PYTHON_EXE"

echo ""
echo "=== Setup Gestor listo ==="
ls -lh "$OUT_DIR/SAJ_PDM30_Gestor_Setup.exe"
file "$OUT_DIR/SAJ_PDM30_Gestor_Setup.exe" || true
echo "Ruta: $OUT_DIR/SAJ_PDM30_Gestor_Setup.exe"

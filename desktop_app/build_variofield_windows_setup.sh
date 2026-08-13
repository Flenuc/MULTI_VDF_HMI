#!/usr/bin/env bash
# Genera VarioField-Setup-0.3.2.exe (instalador NSIS para Windows x64)
# Mismo enfoque que flasher/gestor: makensis en Linux + Python embebido.
# No necesita Windows ni GitHub Actions. La UI es Expo web estática servida
# por el backend (sin Electron en este paquete).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$DIR/packaging/windows_variofield"
PAYLOAD="$PKG/payload"
OUT_DIR="$DIR/dist/windows"
CACHE_DIR="$DIR/packaging/windows_flasher/cache"
PYTHON_VER="3.12.10"
PYTHON_EXE="python-${PYTHON_VER}-amd64.exe"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/${PYTHON_EXE}"
VERSION="0.3.2"
SETUP_NAME="VarioField-Setup-${VERSION}.exe"

echo "=== Build Windows Setup (VarioField ${VERSION}) ==="

if ! command -v makensis >/dev/null 2>&1; then
  echo "ERROR: makensis no encontrado. Instale: sudo apt install nsis"
  exit 1
fi

# --- 1) Export Expo web UI (production) ---
echo "--- Export UI (Expo web) ---"
if [[ -d "$DIR/frontend/node_modules" ]]; then
  (
    cd "$DIR/frontend"
    export EXPO_PUBLIC_ENV=production
    npx expo export --platform web --output-dir dist --clear
  )
elif command -v npm >/dev/null 2>&1; then
  (
    cd "$DIR/frontend"
    npm ci || npm install
    export EXPO_PUBLIC_ENV=production
    npx expo export --platform web --output-dir dist --clear
  )
else
  echo "ERROR: no hay node_modules ni npm para exportar la UI"
  exit 1
fi

if [[ ! -f "$DIR/frontend/dist/index.html" ]]; then
  echo "ERROR: no se genero frontend/dist/index.html"
  exit 1
fi

# --- 2) Sync payload sources ---
echo "--- Sync payload ---"
mkdir -p "$PAYLOAD"/{backend,comms,param_lists,config,ui} "$OUT_DIR" "$CACHE_DIR"

# Launcher + helpers (versionados en packaging)
for f in Launch_VarioField.bat post_install.bat LEEME.txt run_variofield.py; do
  if [[ ! -f "$PAYLOAD/$f" ]]; then
    echo "ERROR: falta $PAYLOAD/$f"
    exit 1
  fi
done

cp -f "$PKG/requirements-variofield.txt" "$PAYLOAD/requirements-variofield.txt"
cp -f "$DIR/models.py" "$PAYLOAD/models.py"
cp -f "$DIR/storage.py" "$PAYLOAD/storage.py"
cp -f "$DIR/profiles.py" "$PAYLOAD/profiles.py"

cp -f "$DIR/backend/__init__.py" "$PAYLOAD/backend/"
cp -f "$DIR/backend/__main__.py" "$PAYLOAD/backend/"
cp -f "$DIR/backend/main.py" "$PAYLOAD/backend/"
cp -f "$DIR/backend/session.py" "$PAYLOAD/backend/"
cp -f "$DIR/backend/schemas.py" "$PAYLOAD/backend/"
cp -f "$DIR/backend/param_api.py" "$PAYLOAD/backend/"
cp -f "$DIR/backend/requirements.txt" "$PAYLOAD/backend/"

cp -f "$DIR/comms/"*.py "$PAYLOAD/comms/"
cp -f "$DIR/param_lists/"*.json "$PAYLOAD/param_lists/"
cp -f "$DIR/config/connection_profiles.example.json" "$PAYLOAD/config/"

# UI: wipe + copy export
rm -rf "$PAYLOAD/ui"
mkdir -p "$PAYLOAD/ui"
cp -a "$DIR/frontend/dist/." "$PAYLOAD/ui/"
test -f "$PAYLOAD/ui/index.html"
echo "UI files: $(find "$PAYLOAD/ui" -type f | wc -l)"

# --- 3) Python Windows installer (shared cache) ---
if [[ ! -f "$CACHE_DIR/$PYTHON_EXE" ]]; then
  echo "Descargando Python ${PYTHON_VER} Windows x64..."
  curl -fL --retry 3 -o "$CACHE_DIR/$PYTHON_EXE.partial" "$PYTHON_URL"
  mv "$CACHE_DIR/$PYTHON_EXE.partial" "$CACHE_DIR/$PYTHON_EXE"
fi
cp -f "$CACHE_DIR/$PYTHON_EXE" "$PAYLOAD/$PYTHON_EXE"
ls -lh "$PAYLOAD/$PYTHON_EXE"

# --- 4) Compile NSIS ---
echo "--- Compilando NSIS ---"
cd "$PKG"
makensis -V2 variofield_setup.nsi

if [[ ! -f "$PKG/$SETUP_NAME" ]]; then
  echo "ERROR: no se genero $SETUP_NAME"
  ls -la "$PKG" || true
  exit 1
fi

mv -f "$PKG/$SETUP_NAME" "$OUT_DIR/$SETUP_NAME"
cp -f "$OUT_DIR/$SETUP_NAME" "$DIR/dist/$SETUP_NAME"

cat > "$OUT_DIR/LEEME_VARIOFIELD_SETUP.txt" << EOF
${SETUP_NAME}
================================
Instalador Windows x64 de VarioField ${VERSION}
(backend Python + UI web; sin Electron).

1. Copie el .exe a un PC Windows 10/11 64-bit
2. Ejecutelo (SmartScreen: Mas info → Ejecutar de todas formas)
3. Si no hay Python, lo instala el setup
4. Primera vez: Internet para pip
5. Arranca Launch_VarioField.bat → navegador en http://127.0.0.1:8765

Atajos: Escritorio y menu Inicio → VarioField

Build alternativo (Linux): desktop_app/build_variofield_windows_setup.sh
EOF

rm -f "$PAYLOAD/$PYTHON_EXE"
# No versionar el volcado de UI en git (se regenera en cada build)
# dejamos payload/ui en disco para inspeccion; opcional limpiar:
# rm -rf "$PAYLOAD/ui" && mkdir -p "$PAYLOAD/ui" && echo "placeholder" > "$PAYLOAD/ui/.gitkeep"

echo ""
echo "=== Setup VarioField listo ==="
ls -lh "$OUT_DIR/$SETUP_NAME"
file "$OUT_DIR/$SETUP_NAME" || true
echo "Ruta: $OUT_DIR/$SETUP_NAME"

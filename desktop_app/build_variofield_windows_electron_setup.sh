#!/usr/bin/env bash
# Build VarioField Windows Setup with *native Electron* from Linux (incl. aarch64).
#
# Layout inside installer:
#   VarioField.exe          (electron.exe renamed)
#   resources/app/          main.js, preload.js, package.json
#   resources/ui/           Expo web export
#   resources/python/       CPython embeddable win_amd64 + site-packages (wheels)
#   resources/pyapp/        FastAPI backend sources
#
# Requires: curl, unzip, makensis, python3, npm/npx (for expo export)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$DIR/packaging/windows_electron"
CACHE="$PKG/cache"
STAGE="$PKG/stage/VarioField"
OUT_DIR="$DIR/dist/windows"
VERSION="$(cd "$DIR" && node -p "require('./electron/package.json').version" 2>/dev/null || echo "0.3.3")"
# Ensure NSIS OutFile matches package version
if [[ -f "$PKG/variofield_electron_setup.nsi" ]]; then
  sed -i -E "s/VarioField-Setup-[0-9.]+\\.exe/VarioField-Setup-${VERSION}.exe/g" "$PKG/variofield_electron_setup.nsi" || true
  sed -i -E "s/PRODUCT_VERSION \"[0-9.]+\"/PRODUCT_VERSION \"${VERSION}\"/g" "$PKG/variofield_electron_setup.nsi" || true
  sed -i -E "s/VIProductVersion \"[0-9.]+\"/VIProductVersion \"${VERSION}.0\"/g" "$PKG/variofield_electron_setup.nsi" || true
fi
SETUP_NAME="VarioField-Setup-${VERSION}.exe"

PYTHON_VER="3.12.10"
PYTHON_EMBED="python-${PYTHON_VER}-embed-amd64.zip"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VER}/${PYTHON_EMBED}"

# Match installed electron package if present
ELECTRON_VER="$(node -e "try{console.log(require('$DIR/electron/node_modules/electron/package.json').version)}catch(e){console.log('33.4.11')}" 2>/dev/null || echo "33.4.11")"
ELECTRON_ZIP="electron-v${ELECTRON_VER}-win32-x64.zip"
ELECTRON_URL="https://github.com/electron/electron/releases/download/v${ELECTRON_VER}/${ELECTRON_ZIP}"

echo "=== Build Windows Electron Setup (VarioField ${VERSION}) ==="
echo "Electron ${ELECTRON_VER}  |  Python embed ${PYTHON_VER}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: falta '$1'"; exit 1; }; }
need curl
need unzip
need makensis
need python3
need npm

mkdir -p "$CACHE" "$OUT_DIR" "$PKG/stage"

# ---------------------------------------------------------------------------
# 1) Expo web UI
# ---------------------------------------------------------------------------
echo "--- 1) Export UI ---"
(
  cd "$DIR/frontend"
  export EXPO_PUBLIC_ENV=production
  if [[ ! -d node_modules ]]; then npm ci || npm install; fi
  npx expo export --platform web --output-dir dist --clear
)
test -f "$DIR/frontend/dist/index.html"

# ---------------------------------------------------------------------------
# 2) Download Electron win32-x64
# ---------------------------------------------------------------------------
echo "--- 2) Electron win32-x64 ---"
if [[ ! -f "$CACHE/$ELECTRON_ZIP" ]]; then
  echo "Descargando $ELECTRON_URL"
  curl -fL --retry 3 -o "$CACHE/$ELECTRON_ZIP.partial" "$ELECTRON_URL"
  mv "$CACHE/$ELECTRON_ZIP.partial" "$CACHE/$ELECTRON_ZIP"
fi
ls -lh "$CACHE/$ELECTRON_ZIP"

rm -rf "$STAGE"
mkdir -p "$STAGE"
unzip -q "$CACHE/$ELECTRON_ZIP" -d "$STAGE"
# Rename electron.exe → VarioField.exe
if [[ -f "$STAGE/electron.exe" ]]; then
  mv "$STAGE/electron.exe" "$STAGE/VarioField.exe"
fi
# Drop default app; we ship resources/app
rm -f "$STAGE/resources/default_app.asar"

# ---------------------------------------------------------------------------
# 3) Electron app files
# ---------------------------------------------------------------------------
echo "--- 3) App shell ---"
mkdir -p "$STAGE/resources/app"
cp -f "$DIR/electron/main.js" "$STAGE/resources/app/"
cp -f "$DIR/electron/preload.js" "$STAGE/resources/app/"
# Minimal package.json (no devDependencies needed at runtime)
python3 - <<PY
import json
from pathlib import Path
src = json.loads(Path("$DIR/electron/package.json").read_text())
out = {
    "name": src.get("name", "variofield-desktop"),
    "productName": src.get("productName", "VarioField"),
    "version": src.get("version", "$VERSION"),
    "description": src.get("description", "VarioField"),
    "main": "main.js",
    "author": src.get("author", {}),
    "license": src.get("license", "MIT"),
    "private": True,
}
Path("$STAGE/resources/app/package.json").write_text(json.dumps(out, indent=2) + "\n")
print("package.json written")
PY

# ---------------------------------------------------------------------------
# 4) UI
# ---------------------------------------------------------------------------
echo "--- 4) UI resources ---"
rm -rf "$STAGE/resources/ui"
mkdir -p "$STAGE/resources/ui"
cp -a "$DIR/frontend/dist/." "$STAGE/resources/ui/"
test -f "$STAGE/resources/ui/index.html"

# ---------------------------------------------------------------------------
# 5) Python embeddable + win wheels
# ---------------------------------------------------------------------------
echo "--- 5) Python embed + wheels ---"
if [[ ! -f "$CACHE/$PYTHON_EMBED" ]]; then
  echo "Descargando $PYTHON_URL"
  curl -fL --retry 3 -o "$CACHE/$PYTHON_EMBED.partial" "$PYTHON_URL"
  mv "$CACHE/$PYTHON_EMBED.partial" "$CACHE/$PYTHON_EMBED"
fi

PY_ROOT="$STAGE/resources/python"
rm -rf "$PY_ROOT"
mkdir -p "$PY_ROOT"
unzip -q "$CACHE/$PYTHON_EMBED" -d "$PY_ROOT"

# Enable site-packages + pyapp (._pth ignores PYTHONPATH)
PTH="$(echo "$PY_ROOT"/python*._pth)"
if [[ ! -f "$PTH" ]]; then
  echo "ERROR: no se encontro python*._pth en embed"
  ls -la "$PY_ROOT"
  exit 1
fi
ZIP_NAME="python312.zip"
if [[ ! -f "$PY_ROOT/python312.zip" ]]; then
  ZIP_NAME="$(basename "$(ls "$PY_ROOT"/python3*.zip | head -1)")"
fi
# Paths relative to the directory that contains python.exe
cat > "$PTH" <<EOF
${ZIP_NAME}
.
Lib\\site-packages
..\\pyapp
import site
EOF
echo "--- python._pth ---"
cat "$PTH"

SITE="$PY_ROOT/Lib/site-packages"
mkdir -p "$SITE"

WHEEL_DIR="$CACHE/wheels-win_amd64"
mkdir -p "$WHEEL_DIR"
REQ="$PKG/requirements-wheels.txt"

# Drop stale pydantic* wheels so --no-deps cannot leave mismatched pair
rm -f "$WHEEL_DIR"/pydantic-*.whl "$WHEEL_DIR"/pydantic_core-*.whl

echo "Descargando wheels win_amd64..."
# shellcheck disable=SC2046
python3 -m pip download -d "$WHEEL_DIR" --no-deps \
  --platform win_amd64 \
  --python-version 312 \
  --implementation cp \
  --abi cp312 \
  --only-binary=:all: \
  --index-url https://pypi.org/simple \
  --trusted-host pypi.org \
  $(grep -v '^\s*#' "$REQ" | grep -v '^\s*$' | tr '\n' ' ')

echo "Extrayendo wheels → site-packages..."
# Fresh site-packages (avoid leftover wrong pydantic_core from prior builds)
rm -rf "$SITE"
mkdir -p "$SITE"
shopt -s nullglob
for whl in "$WHEEL_DIR"/*.whl; do
  unzip -qo "$whl" -d "$SITE"
done
shopt -u nullglob

# Fail build if pydantic / pydantic-core are out of sync (common --no-deps trap)
SITE_PACKAGES="$SITE" python3 - <<'PY'
from pathlib import Path
import os, re, sys
site = Path(os.environ["SITE_PACKAGES"])
def ver(name_prefix):
    for p in site.glob(f"{name_prefix}-*.dist-info"):
        m = re.match(rf"{re.escape(name_prefix)}-([^-]+)\.dist-info$", p.name)
        if m:
            return m.group(1), p
    return None, None
pv, pdir = ver("pydantic")
cv, cdir = ver("pydantic_core")
print(f"pydantic={pv}  pydantic_core={cv}")
if not pv or not cv:
    print("ERROR: pydantic or pydantic-core missing after wheel extract", file=sys.stderr)
    sys.exit(1)
meta = (pdir / "METADATA").read_text(encoding="utf-8", errors="replace")
req = None
for line in meta.splitlines():
    if line.lower().startswith("requires-dist:") and "pydantic-core" in line.lower():
        m = re.search(r"pydantic-core\s*==\s*([0-9.]+)", line, re.I)
        if m:
            req = m.group(1)
            break
if req and req != cv:
    print(f"ERROR: pydantic requires pydantic-core=={req} but we have {cv}", file=sys.stderr)
    sys.exit(1)
print("pydantic pair OK")
PY

# Clean wheel metadata clutter is fine to keep for imports
echo "site-packages entries: $(ls "$SITE" | wc -l)"

# Native wheels (pydantic_core, winrt, …) need MSVC runtime next to python.exe.
# winrt wheel ships msvcp140.dll; copy it (and any siblings) into python/.
echo "Copiando runtimes MSVC al lado de python.exe..."
find "$SITE" -iname 'msvcp*.dll' -o -iname 'vcruntime*.dll' -o -iname 'concrt*.dll' 2>/dev/null \
  | while read -r dll; do
      cp -n "$dll" "$PY_ROOT/" 2>/dev/null || cp -f "$dll" "$PY_ROOT/"
    done
ls -lh "$PY_ROOT"/msvcp*.dll "$PY_ROOT"/vcruntime*.dll 2>/dev/null || true

# ---------------------------------------------------------------------------
# 6) pyapp sources
# ---------------------------------------------------------------------------
echo "--- 6) Backend sources (pyapp) ---"
PYAPP="$STAGE/resources/pyapp"
rm -rf "$PYAPP"
mkdir -p "$PYAPP"/{backend,comms,param_lists,config}

cp -f "$PKG/pyapp/run_variofield.py" "$PYAPP/run_variofield.py"
cp -f "$DIR/models.py" "$PYAPP/"
cp -f "$DIR/storage.py" "$PYAPP/"
cp -f "$DIR/profiles.py" "$PYAPP/"
cp -f "$DIR/backend/__init__.py" "$PYAPP/backend/"
cp -f "$DIR/backend/__main__.py" "$PYAPP/backend/"
cp -f "$DIR/backend/main.py" "$PYAPP/backend/"
cp -f "$DIR/backend/session.py" "$PYAPP/backend/"
cp -f "$DIR/backend/schemas.py" "$PYAPP/backend/"
cp -f "$DIR/backend/param_api.py" "$PYAPP/backend/"
cp -f "$DIR/backend/broker.py" "$PYAPP/backend/"
cp -f "$DIR/comms/"*.py "$PYAPP/comms/"
cp -f "$DIR/param_lists/"*.json "$PYAPP/param_lists/"
cp -f "$DIR/config/connection_profiles.example.json" "$PYAPP/config/"

# Drive profiles (multi-VDF catalogs)
echo "--- 6a) drive_profiles ---"
REPO_ROOT="$(cd "$DIR/.." && pwd)"
DP_DST="$STAGE/resources/drive_profiles"
rm -rf "$DP_DST"
if [[ -d "$REPO_ROOT/drive_profiles" ]]; then
  mkdir -p "$DP_DST"
  cp -a "$REPO_ROOT/drive_profiles/." "$DP_DST/"
  echo "drive_profiles: $(find "$DP_DST" -name profile.json | wc -l) profile.json"
else
  echo "WARN: $REPO_ROOT/drive_profiles missing"
fi

# Scripts (Mosquitto setup)
echo "--- 6b) scripts (Mosquitto) ---"
mkdir -p "$STAGE/resources/scripts"
cp -f "$DIR/scripts/setup_mosquitto.sh" "$STAGE/resources/scripts/" 2>/dev/null || true
cp -f "$DIR/scripts/setup_mosquitto.ps1" "$STAGE/resources/scripts/"
cp -f "$DIR/scripts/mosquitto-variofield.conf" "$STAGE/resources/scripts/"

# LEEME + diagnóstico de campo
cat > "$STAGE/LEEME.txt" << EOF
VarioField ${VERSION} — Windows (Electron nativo)
================================================
Instalado con VarioField-Setup-${VERSION}.exe

- Ejecutable: VarioField.exe
- Backend: Python embebido (resources/python) + sources (resources/pyapp)
- UI: resources/ui (servida en http://127.0.0.1:8765)

No requiere Python ni Node del sistema.
Cierre la ventana de la app para detener el backend.

Si no arranca:
1) Ejecute Diagnose_Backend.bat (consola con el error)
2) Revise %APPDATA%\\VarioField\\backend.log  (o userData de Electron)
3) Revise resources\\pyapp\\backend-boot.log

Repo: https://github.com/Flenuc/MULTI_VDF_HMI
EOF

cat > "$STAGE/Diagnose_Backend.bat" << 'EOF'
@echo off
setlocal
cd /d "%~dp0"
echo === VarioField backend diagnose ===
echo DIR=%CD%
if not exist "resources\python\python.exe" (
  echo ERROR: falta resources\python\python.exe
  pause
  exit /b 1
)
if not exist "resources\pyapp\run_variofield.py" (
  echo ERROR: falta resources\pyapp\run_variofield.py
  pause
  exit /b 1
)
set "PATH=%CD%\resources\python;%PATH%"
set "MULTI_VDF_HOST=127.0.0.1"
set "MULTI_VDF_PORT=8765"
set "MULTI_VDF_UI_DIR=%CD%\resources\ui"
set "PYTHONUNBUFFERED=1"
set "VARIOFIELD_EMBED=1"
echo.
echo Arrancando backend (Ctrl+C para salir)...
echo.
"resources\python\python.exe" "resources\pyapp\run_variofield.py"
echo.
echo Exit code=%ERRORLEVEL%
pause
EOF


echo "Stage size:"
du -sh "$STAGE"

# ---------------------------------------------------------------------------
# 7) NSIS
# ---------------------------------------------------------------------------
echo "--- 7) Compilar NSIS ---"
cd "$PKG"
# Ensure stage path exists relative to nsi
test -f "$STAGE/VarioField.exe"
test -f "$STAGE/resources/app/main.js"
test -f "$STAGE/resources/python/python.exe"
test -f "$STAGE/resources/pyapp/run_variofield.py"
test -f "$STAGE/resources/ui/index.html"

makensis -V2 variofield_electron_setup.nsi

if [[ ! -f "$PKG/$SETUP_NAME" ]]; then
  echo "ERROR: no se genero $SETUP_NAME"
  ls -la "$PKG"
  exit 1
fi

mv -f "$PKG/$SETUP_NAME" "$OUT_DIR/$SETUP_NAME"
cp -f "$OUT_DIR/$SETUP_NAME" "$DIR/dist/$SETUP_NAME"

cat > "$OUT_DIR/LEEME_ELECTRON_SETUP.txt" << EOF
${SETUP_NAME}
================================
Instalador Windows x64 de VarioField ${VERSION}
con shell Electron nativo + Python embebido.

Build (Linux/ARM/x64):
  desktop_app/build_variofield_windows_electron_setup.sh

1. Ejecute el Setup en Windows 10/11 64-bit
2. SmartScreen: Mas info → Ejecutar de todas formas
3. Atajo Escritorio / Inicio → VarioField
4. No necesita Python ni Internet en el PC destino
   (dependencias van dentro del instalador)

Diferencia vs Setup "web":
  Este abre ventana Electron (Chromium embebido).
  El Setup ligero solo usa el navegador del sistema.
EOF

echo ""
echo "=== Setup Electron listo ==="
ls -lh "$OUT_DIR/$SETUP_NAME"
file "$OUT_DIR/$SETUP_NAME" || true
echo "Ruta: $OUT_DIR/$SETUP_NAME"

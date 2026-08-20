#!/usr/bin/env bash
# Build VarioField desktop production pack (Electron + PyInstaller + Expo web)
# Output: desktop_app/electron/dist/VarioField-*.AppImage
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export EXPO_PUBLIC_ENV="${EXPO_PUBLIC_ENV:-production}"
VERSION="$(node -p "require('./electron/package.json').version" 2>/dev/null || echo "0.3.3")"
echo "=== VarioField ${VERSION} — build producción (EXPO_PUBLIC_ENV=${EXPO_PUBLIC_ENV}) ==="

echo "=== 1) Python backend binary (PyInstaller) ==="
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip wheel
pip install -q -r requirements.txt -r backend/requirements.txt pyinstaller

rm -rf build/pyi
mkdir -p electron/resources/backend electron/resources/ui electron/resources/drive_profiles

# Multi-VDF catalogs (SAJ PDM/PDH …) next to packaged backend
REPO_ROOT="$(cd "$DIR/.." && pwd)"
if [[ -d "$REPO_ROOT/drive_profiles" ]]; then
  rm -rf electron/resources/drive_profiles
  mkdir -p electron/resources/drive_profiles
  cp -a "$REPO_ROOT/drive_profiles/." electron/resources/drive_profiles/
  echo "drive_profiles: $(find electron/resources/drive_profiles -name profile.json | wc -l) profile.json"
else
  echo "WARN: $REPO_ROOT/drive_profiles missing — catalog API will be empty in package"
fi

pyinstaller --noconfirm --clean \
  --onefile \
  --name multi_vdf_backend \
  --paths "$DIR" \
  --distpath "$DIR/electron/resources/backend" \
  --workpath "$DIR/build/pyi" \
  --specpath "$DIR/build/pyi" \
  --console \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import backend.main \
  --hidden-import backend.session \
  --hidden-import backend.schemas \
  --hidden-import backend.param_api \
  --hidden-import backend.broker \
  --hidden-import backend.mqtt_discover \
  --hidden-import comms \
  --hidden-import comms.serial_client \
  --hidden-import comms.mqtt_client \
  --hidden-import comms.bluetooth_client \
  --hidden-import comms.ble_nus_client \
  --hidden-import comms.dummy_client \
  --hidden-import models \
  --hidden-import profiles \
  --hidden-import storage \
  --hidden-import serial.tools.list_ports \
  --collect-all bleak \
  "$DIR/backend/main.py"

chmod +x electron/resources/backend/multi_vdf_backend
ls -lh electron/resources/backend/multi_vdf_backend

# Example MQTT profiles (seeded into Electron userData/config on first run)
mkdir -p electron/resources/config
cp -f config/connection_profiles.example.json \
  electron/resources/config/connection_profiles.example.json

echo "=== 2) Expo web static UI (production) ==="
cd frontend
if [[ ! -d node_modules ]]; then npm install; fi
if [[ ! -d node_modules/react-native-web ]]; then
  npx expo install react-dom react-native-web @expo/metro-runtime
fi
export EXPO_PUBLIC_ENV=production
npx expo export --platform web --output-dir dist --clear
cd ..
rm -rf electron/resources/ui/*
cp -a frontend/dist/. electron/resources/ui/
test -f electron/resources/ui/index.html
echo "UI files: $(find electron/resources/ui -type f | wc -l)"

echo "=== 3) Electron AppImage ==="
cd electron
if [[ ! -d node_modules ]]; then npm install; fi
# Ensure icons available (electron-builder looks at app-icons)
if [[ ! -f app-icons/icon.png ]]; then
  echo "WARN: app-icons/icon.png missing — using default Electron icon"
fi

cat > resources/backend/LEEME.txt << EOF
VarioField backend ${VERSION}
API + UI en http://127.0.0.1:8765
Electron define MULTI_VDF_UI_DIR hacia resources/ui
Electron define MULTI_VDF_DRIVE_PROFILES hacia resources/drive_profiles
Electron define MULTI_VDF_CONFIG_DIR hacia userData/config (perfiles MQTT)
EOF

npx electron-builder --linux AppImage
cd ..

echo ""
echo "=== VarioField ${VERSION} — build listo ==="
ls -lh electron/dist/*AppImage 2>/dev/null || ls -lh electron/dist/
ARCH="$(uname -m)"
echo ""
echo "Ejecutar:"
echo "  chmod +x electron/dist/VarioField-*.AppImage"
echo "  ./electron/dist/VarioField-*-*.AppImage"
echo ""
echo "Host arch: ${ARCH}  (arm64 Pi → AppImage arm64; x86_64 PC → AppImage x64)"
echo "Notas: RELEASE_NOTES_${VERSION}.md (o RELEASE_NOTES_0.3.3.md)"

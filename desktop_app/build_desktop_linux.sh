#!/usr/bin/env bash
# Build MULTI_VDF_HMI desktop (Electron + PyInstaller backend + Expo web UI)
# Output: desktop_app/electron/dist/  (AppImage / deb) + resources
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== 1) Python backend binary (PyInstaller) ==="
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip wheel
pip install -q -r requirements.txt -r backend/requirements.txt pyinstaller

rm -rf build/pyi dist/backend_bin
mkdir -p electron/resources/backend electron/resources/ui

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
  --hidden-import comms \
  --hidden-import comms.serial_client \
  --hidden-import comms.mqtt_client \
  --hidden-import comms.bluetooth_client \
  --hidden-import comms.ble_nus_client \
  --hidden-import comms.dummy_client \
  --hidden-import serial.tools.list_ports \
  --collect-all bleak \
  "$DIR/backend/main.py"

chmod +x electron/resources/backend/multi_vdf_backend
ls -lh electron/resources/backend/

echo "=== 2) Expo web static UI ==="
cd frontend
if [[ ! -d node_modules ]]; then npm install; fi
if [[ ! -d node_modules/react-native-web ]]; then
  npx expo install react-dom react-native-web @expo/metro-runtime
fi
npx expo export --platform web --output-dir dist --clear
cd ..
rm -rf electron/resources/ui/*
cp -a frontend/dist/. electron/resources/ui/
# Also wire MULTI_VDF_UI_DIR for the onefile binary (Electron sets it to resources/ui)
test -f electron/resources/ui/index.html
echo "UI files: $(find electron/resources/ui -type f | wc -l)"

echo "=== 3) Electron app ==="
cd electron
if [[ ! -d node_modules ]]; then npm install; fi
# Place a tiny README next to backend
cat > resources/backend/LEEME.txt << EOF
multi_vdf_backend — API + UI host
Electron sets MULTI_VDF_UI_DIR to ../ui
Port: 127.0.0.1:8765
EOF

# AppImage only by default — .deb uses fpm (x86) and fails on aarch64/Pi.
npx electron-builder --linux AppImage
cd ..

echo ""
echo "=== Desktop Linux build listo ==="
ls -lh electron/dist/*AppImage 2>/dev/null || ls -lh electron/dist/
echo ""
echo "Ejecutar (estás en desktop_app):"
echo "  chmod +x electron/dist/MULTI_VDF_HMI-*.AppImage"
echo "  ./electron/dist/MULTI_VDF_HMI-*-arm64.AppImage"
echo ""
echo "Dev sin empaquetar (desde desktop_app):"
echo "  cd electron && npm start"
echo "  # NO: cd desktop_app/electron  (si ya estás dentro de desktop_app)"

#!/usr/bin/env bash
# Genera ejecutables standalone Linux (Gestor + Flasher) con PyInstaller
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
pip install pyinstaller

OUT_DIR="$DIR/dist/linux"
mkdir -p "$OUT_DIR" "$DIR/dist" "$DIR/build/linux"

ARCH="$(uname -m)"
echo "=== Build Linux ($ARCH) ==="

COMMON_ARGS=(
  --noconfirm
  --clean
  --onefile
  --windowed
  --distpath "$OUT_DIR"
  --workpath "$DIR/build/linux"
  --specpath "$DIR/build/linux"
  --paths "$DIR"
  --hidden-import "serial.tools.list_ports"
  --hidden-import "customtkinter"
  --collect-all customtkinter
)

# --- Gestor principal ---
echo "--- SAJ_PDM30_Gestor ---"
pyinstaller \
  "${COMMON_ARGS[@]}" \
  --name "SAJ_PDM30_Gestor" \
  --add-data "$DIR/param_lists:param_lists" \
  --hidden-import "models" \
  --hidden-import "storage" \
  --hidden-import "profiles" \
  --hidden-import "gui" \
  --hidden-import "gui.app" \
  --hidden-import "comms" \
  --hidden-import "comms.serial_client" \
  --hidden-import "comms.mqtt_client" \
  --hidden-import "comms.bluetooth_client" \
  --hidden-import "comms.ble_nus_client" \
  --hidden-import "comms.dummy_client" \
  --hidden-import "comms.base" \
  --collect-submodules "comms" \
  --collect-submodules "gui" \
  "$DIR/main.py"

# --- Flasher de firmwares ---
echo "--- MULTI_VDF_HMI_Flasher ---"
pyinstaller \
  "${COMMON_ARGS[@]}" \
  --name "MULTI_VDF_HMI_Flasher" \
  --hidden-import "flasher" \
  --hidden-import "flasher.gui" \
  --hidden-import "flasher.github_releases" \
  --hidden-import "flasher.flash_worker" \
  --hidden-import "esptool" \
  --collect-submodules "flasher" \
  --collect-all esptool \
  --collect-all serial \
  "$DIR/run_flasher.py"

# Convenience copies at dist/
for name in SAJ_PDM30_Gestor MULTI_VDF_HMI_Flasher; do
  if [[ -f "$OUT_DIR/$name" ]]; then
    cp -f "$OUT_DIR/$name" "$DIR/dist/$name"
    chmod +x "$OUT_DIR/$name" "$DIR/dist/$name"
  fi
done

# README in dist
cat > "$OUT_DIR/LEEME.txt" << EOF
MULTI_VDF_HMI — ejecutables Linux ($ARCH)
=========================================

SAJ_PDM30_Gestor
  App de campo: USB / MQTT / Bluetooth LE (NUS) / SPP / simulado.
  Ejecutar:  ./SAJ_PDM30_Gestor

MULTI_VDF_HMI_Flasher
  Descarga firmwares desde GitHub (Flenuc/MULTI_VDF_HMI) y flashea con esptool.
  Ejecutar:  ./MULTI_VDF_HMI_Flasher
  Requiere:  permisos de puerto serial (usuario en grupo dialout/plugdev).

Si el SO no abre el binario:
  chmod +x SAJ_PDM30_Gestor MULTI_VDF_HMI_Flasher
  # dependencias del sistema (raro en one-file):
  # sudo apt install libxcb-cursor0 libxkbcommon-x11-0

Generado con: desktop_app/build_linux.sh
EOF

cp -f "$OUT_DIR/LEEME.txt" "$DIR/dist/LEEME_linux.txt" 2>/dev/null || true

echo ""
echo "=== Build Linux listo ($ARCH) ==="
ls -lh "$OUT_DIR"/SAJ_PDM30_Gestor "$OUT_DIR"/MULTI_VDF_HMI_Flasher 2>/dev/null || true
echo "Carpeta: $OUT_DIR"

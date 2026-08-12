#!/usr/bin/env bash
# Genera ejecutable standalone Linux con PyInstaller
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install pyinstaller

OUT_DIR="$DIR/dist/linux"
mkdir -p "$OUT_DIR" "$DIR/dist" "$DIR/build/linux"

# one-file windowed binary; absolute --add-data avoids specpath relative bugs
pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name "SAJ_PDM30_Gestor" \
  --distpath "$OUT_DIR" \
  --workpath "$DIR/build/linux" \
  --specpath "$DIR/build/linux" \
  --paths "$DIR" \
  --add-data "$DIR/param_lists:param_lists" \
  --hidden-import "serial.tools.list_ports" \
  --hidden-import "models" \
  --hidden-import "storage" \
  --hidden-import "serial_client" \
  --hidden-import "gui_app" \
  --collect-all customtkinter \
  "$DIR/main.py"

# Convenience copy at dist/
if [[ -f "$OUT_DIR/SAJ_PDM30_Gestor" ]]; then
  cp -f "$OUT_DIR/SAJ_PDM30_Gestor" "$DIR/dist/SAJ_PDM30_Gestor"
  chmod +x "$OUT_DIR/SAJ_PDM30_Gestor" "$DIR/dist/SAJ_PDM30_Gestor"
fi

echo ""
echo "=== Build Linux listo ==="
echo "Ejecutable: $OUT_DIR/SAJ_PDM30_Gestor"
ls -lh "$OUT_DIR/SAJ_PDM30_Gestor" "$DIR/dist/SAJ_PDM30_Gestor" 2>/dev/null || true
echo "Lanzar con: ./run_linux.sh  o  ./dist/SAJ_PDM30_Gestor"

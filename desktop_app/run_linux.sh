#!/usr/bin/env bash
# Lanzador Linux — SAJ PDM-30 Gestor de Parámetros
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Prefer prebuilt binary if present
if [[ -x "$DIR/dist/SAJ_PDM30_Gestor" ]]; then
  exec "$DIR/dist/SAJ_PDM30_Gestor" "$@"
fi
if [[ -x "$DIR/dist/linux/SAJ_PDM30_Gestor" ]]; then
  exec "$DIR/dist/linux/SAJ_PDM30_Gestor" "$@"
fi

# Fallback: venv + python
if [[ ! -d "$DIR/.venv" ]]; then
  echo "Creando entorno virtual..."
  python3 -m venv "$DIR/.venv"
  # shellcheck disable=SC1091
  source "$DIR/.venv/bin/activate"
  pip install -U pip
  pip install -r "$DIR/requirements.txt"
else
  # shellcheck disable=SC1091
  source "$DIR/.venv/bin/activate"
fi

exec python "$DIR/main.py" "$@"

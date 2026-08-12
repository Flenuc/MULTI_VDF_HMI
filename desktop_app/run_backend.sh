#!/usr/bin/env bash
# Start the Python transport API (default http://127.0.0.1:8765)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip wheel
pip install -q -r requirements.txt -r backend/requirements.txt

export PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --log-level info

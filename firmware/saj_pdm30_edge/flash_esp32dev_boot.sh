#!/usr/bin/env bash
# Flash esp32dev when auto-reset fails: hold BOOT, tap RESET, then run this.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.platformio/penv/bin:$PATH"
PORT="${1:-/dev/ttyACM0}"
echo "Port=$PORT — enter download mode (hold BOOT, tap EN/RESET), then wait…"
pio run -e esp32dev -t upload --upload-port "$PORT"

#!/usr/bin/env bash
# Start Expo web UI (expects backend on :8765)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
# Install web deps if missing
if [[ ! -d node_modules/react-native-web ]]; then
  npx expo install react-dom react-native-web @expo/metro-runtime
fi
export EXPO_PUBLIC_API_URL="${EXPO_PUBLIC_API_URL:-http://127.0.0.1:8765}"
exec npx expo start --web --port 8081

#!/usr/bin/env bash
# Rewrite git history to remove known leaked Wi-Fi strings from the public repo.
# REQUIRES: pip install git-filter-repo
# REQUIRES: explicit human OK before: git push --force-with-lease
#
# Usage (from repo root, clean working tree preferred):
#   ./scripts/purge_wifi_secrets_from_history.sh
# Then verify:
#   git log -S 'BombasROWA' --all   # must be empty
#   git log -S 'REDACTED_SSID' --all
# Only then (with team OK):
#   git push --force-with-lease origin main
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "Instalá git-filter-repo: pip install git-filter-repo" >&2
  exit 1
fi

echo "Rewriting history to strip leaked Wi-Fi identifiers…"
# Replace sensitive tokens with redaction markers across all blobs
git filter-repo --force \
  --replace-text <(cat <<'EOF'
********==>********
REDACTED_SSID==>REDACTED_SSID
EOF
)

echo
echo "Done. Verify with:"
echo "  git log -S 'BombasROWA' --all"
echo "  git log -S 'REDACTED_SSID' --all"
echo "Then ONLY after explicit OK: git push --force-with-lease origin main"
echo "Collaborators must re-clone or reset hard to the new history."

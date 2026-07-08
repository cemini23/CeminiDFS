#!/usr/bin/env bash
# Load CeminiDFS BBM Copilot (v1.3.0) into Google Chrome.
# Persistent install: chrome://extensions → Developer mode → Load unpacked → this folder.
# Quick session load: launches Chrome with --load-extension (survives until Chrome quits).

set -euo pipefail

EXT_DIR="$(cd "$(dirname "$0")/../extension/bbm-copilot" && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

echo "BBM Copilot extension: $EXT_DIR"
echo "Manifest version: $(python3 -c "import json; print(json.load(open('$EXT_DIR/manifest.json'))['version'])") (requires app.underdogsports.com)"
echo ""

# Reveal folder for Load unpacked (Finder)
open "$EXT_DIR"

# Extensions page
open -a "Google Chrome" "chrome://extensions/" 2>/dev/null || true

cat <<'EOF'

Install (one-time, ~30 sec):
  1. On chrome://extensions — toggle "Developer mode" (top-right)
  2. Click "Load unpacked"
  3. Select the bbm-copilot folder (Finder window just opened)
  4. Pin "CeminiDFS BBM Copilot" — click puzzle icon → pin
  5. Click extension icon → API base: http://127.0.0.1:8765 → Save

Before draft:
  ceminidfs bbm serve --slot <1-12> --archetype C --single-entry   # Golden / 1-max
  Extension popup → Test Connection (fills draft_id) → Save
  Open draft at https://app.underdogsports.com/ (reload tab after extension update)

EOF

if [[ -x "$CHROME" ]]; then
  echo "Also loading extension for this Chrome session via --load-extension ..."
  "$CHROME" --load-extension="$EXT_DIR" --new-window "https://underdogfantasy.com/" 2>/dev/null &
fi

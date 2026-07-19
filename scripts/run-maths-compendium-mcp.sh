#!/usr/bin/env bash
# Optional agent-assist MCP (K163). Not a runtime pipeline dependency.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPENDIUM="$ROOT/.local/adopts/maths-cs-ai-compendium"
MCP_DIR="$COMPENDIUM/mcp"
if [[ ! -d "$MCP_DIR" ]]; then
  echo "maths-compendium MCP missing at $MCP_DIR (symlink/clone per briefs/2026-07-14_k163-maths-compendium-mcp-extract.md)" >&2
  exit 1
fi
export COMPENDIUM_ROOT="$COMPENDIUM"
cd "$MCP_DIR"
exec npm start

#!/usr/bin/env bash
# Weekly ESPN redraft refresh: draft card + prerank from season-long ADP.
# Usage: scripts/espn_redraft_refresh.sh [adp.csv] [projections.csv]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADP="${1:-$ROOT/config/espn-ppr-adp.csv}"
PROJ_ARGS=()
if [[ "${2:-}" != "" ]]; then
  PROJ_ARGS=(--projections "$2")
fi
if [[ ! -f "$ADP" ]]; then
  echo "ADP not found: $ADP" >&2
  echo "Expected tracked snapshot: config/espn-ppr-adp.csv" >&2
  exit 1
fi
cd "$ROOT"
ceminidfs redraft refresh --adp "$ADP" "${PROJ_ARGS[@]}"
echo "Timeline: weekly Aug refresh → freeze ~Aug 25 → load ESPN Pre-Draft Rankings ≥1hr before draft."

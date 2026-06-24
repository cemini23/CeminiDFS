#!/usr/bin/env bash
ADP="${1:?usage: bbm_weekly_refresh.sh path/to/adp.csv [projections.csv]}"
PROJ="${2:-}"
if [ -n "$PROJ" ]; then
  exec ceminidfs bbm refresh-weekly --adp "$ADP" --projections "$PROJ"
fi
exec ceminidfs bbm refresh-weekly --adp "$ADP"

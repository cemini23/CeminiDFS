# QB Calibration Notes

## 2026-06 — fixing QB under-projection bias

The 2025 walk-forward calibration (weeks 5-17) flagged QB as systematically
under-projected: MAE **6.67** with bias **-1.42** FD pts. Because FanDuel QB
scoring is dominated by `pass_yds` (0.04/yd) and `pass_td` (4 pts), and both are
`projected_pass_attempts × efficiency`, three compounding drivers pulled QB
projections low: (1) passing efficiency was shrunk toward **league-wide** priors
(`ypa` 7.0, `td_rate` 0.045) that include backups and garbage time, so starting
QBs — the only QBs we project — were dragged below their true level by a single
hardcoded `k=90`; (2) the coherence pass-protection penalty is one-directional
(it only ever trims QB `pass_yds` for stressed offenses, never boosts
well-protected ones), adding net negative bias across the pool; (3) the
implied-total pass-volume boost was conservative. The fix wires the previously
unused `stats.shrinkage` config into QB efficiency via a `StatsSettings`
dataclass (mirroring `UsageSettings`), adds QB-specific shrinkage keys
(`qb_ypa`, `qb_td_rate`, `qb_int_rate`, `qb_rush`) and priors
(`stats.priors.qb_ypa`, `stats.priors.qb_td_rate`), lightens QB shrinkage
(k 90→55) with slightly higher anchors (ypa 7.0→7.25, td_rate 0.045→0.052),
adds a `coherence_risk.pass_protection.qb_yds_penalty_scale` (set to 0.5) so the
one-sided penalty contributes less downward bias, and nudges the QB pass-volume
boost (`qb_implied_pass_boost` 0.014→0.020, baseline 22→20) — a QB-isolated lever
since WR/TE targets derive from team volume, not the QB's projected attempts. All
defaults preserve prior behavior when no config is supplied. Walk-forward
re-run (2025 w5-17): QB bias **-1.42 → -0.35**, QB MAE **6.67 → 6.66** (under the
6.75 gate), overall MAE 4.64 (< 4.85) and RB MAE 5.35 (< 5.45) gates intact.

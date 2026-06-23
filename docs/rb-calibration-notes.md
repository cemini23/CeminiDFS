# RB MAE/Bias Calibration Notes

## Problem Statement

RB MAE was ~5.35–5.36, borderline vs wiki target of 5.30. There was a slight under-bias in RB projections, particularly for rush yardage and TDs, because rushing efficiency was being shrunk toward league-wide priors that include:

- Goal-line vulture touches (high TD/carry, low YPC)
- Backup RBs with limited sample sizes
- Situational carries (short-yardage, clock-killing)

These factors bias league averages downward relative to starter RB efficiency.

## Solution

Mirrors the QB calibration approach (EDGE-B): position-specific shrinkage and priors for RBs.

### Changes Made

1. **Extended `stats_settings.py`** with RB-specific keys:
   - `rb_ypc_shrinkage_k`: Shrinkage strength for YPC (default: 120 vs generic 250)
   - `rb_td_per_carry_shrinkage_k`: Shrinkage strength for TD/carry (default: 120)
   - `rb_ypc_prior`: Regression anchor for YPC (default: 4.5 vs league 4.3)
   - `rb_td_per_carry_prior`: Regression anchor for TD/carry (default: 0.035 vs league 0.03)

2. **Updated `stats.py`** `_rushing_efficiency` function:
   - Accepts `position` and `settings` parameters
   - When `position == "RB"`, uses RB-specific shrinkage and priors
   - Falls back to generic shrinkage for QBs and other positions

3. **Tuned `config/nfl_dfs.yaml`** with calibrated defaults:
   ```yaml
   stats:
     shrinkage:
       rb_ypc: 120          # Lighter than generic 250
       rb_td_per_carry: 120
     priors:
       rb_ypc: 4.5          # Above league 4.3
       rb_td_per_carry: 0.035  # Above league 0.03
   ```

## Calibration Rationale

| Parameter | Old Value | New Value | Rationale |
|-----------|-----------|-----------|-----------|
| YPC shrinkage | 250 | 120 | Retain more of observed starter efficiency |
| TD/carry shrinkage | 250 | 120 | Less pull toward goal-line vulture-inflated league rate |
| YPC prior | 4.3 | 4.5 | Starter baseline above league average |
| TD/carry prior | 0.03 | 0.035 | Starter baseline excludes pure vultures |

## Expected Impact

- **MAE reduction**: Target reduction from ~5.35 to <5.30
- **Bias correction**: Projections should shift up slightly for starter RBs
- **Walk-forward**: Effect should be consistent across weeks as starter roles stabilize

## Config Overrides

For custom tuning without code changes:

```yaml
stats:
  shrinkage:
    rb_ypc: 100          # Even lighter shrinkage
    rb_td_per_carry: 100
  priors:
    rb_ypc: 4.6          # Higher starter baseline
    rb_td_per_carry: 0.04
```

## Testing

Run bias check on synthetic fixtures:

```bash
pytest tests/test_stats.py -v -k "rb"
```

Key test: `test_calibrated_rb_config_increases_projection_vs_defaults` validates that RB projections increase with calibrated config vs defaults.

# Team sim T7 decision record

Date: 2026-10-16. Lane: easy. Status: decision record.

## Sample

Season 2026. The backtest weeks are 2, 3, 4, 5, and 6.
The live file has 64 scored games. The published note said 63.
The tie `2026_05_NYG_WAS` stays in the MAE.
Week 6 still has 13 unscored games.

## Metric table

| Metric | model A | model B | Vegas | Blend_A_Vegas |
|--------|---------|---------|-------|---------------|
| Total MAE | 12.47 | 10.35 | 10.34 | 11.19 |
| Margin MAE | 10.13 | 9.40 | 9.34 | 9.59 |
| Winner accuracy | 0.540 | 0.635 | 0.603 | 0.571 |
| Brier | 0.251 | 0.233 | 0.234 | 0.237 |
| Log loss | 0.695 | 0.659 | 0.661 | 0.665 |
| p15-p85 cover | 0.688 | 0.672 | n/a | n/a |

## Bootstrap

The bootstrap used 5000 draws and seed 20261017.

Model A minus Vegas total MAE is 2.13, with interval 0.46 to 3.89.
Model B minus Vegas stays inside the noise on total, margin, Brier, and log loss.
Model B winner accuracy mean is +0.0315, and the interval starts at 0.0000.

No model beats Vegas on this sample.
The one exception is the model B winner accuracy, and that interval touches zero.

## Band scales and shrink

Model A uses a band scale of 0.74. Model B uses a band scale of 0.61.
Both scales were fit on this same sample. They are not an out-of-sample proof.
`HFA_SHRINK` stays 0.5.
The shrink table did not show a better pair of model B errors at 0, 0.25, or 0.75.

## Decision

Keep model B for the score distributions only.
Park model A.
Do not use model A, model B, or the blend as a side against the Vegas number.

SHADOW only. No bet.

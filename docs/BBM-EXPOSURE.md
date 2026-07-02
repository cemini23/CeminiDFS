# BBM Exposure Policy

This project tracks BBM exposure against a 150-entry portfolio.

- `TOTAL_ENTRIES = 150`
- In-progress drafts count at `50%` weight when previewing exposure.
- Hard cap: `100%` of the entry budget.
- Soft brake: start tapering at `95%` of cap, so the multiplier reaches zero at the cap.
- Combo pair cap: `25%` for configured stack pairs.
- Practice drafts (`is_practice = 1`, `draft_id` starting with `'practice-'`) are excluded from all exposure, combo, portfolio-gap, and reconcile math.

The exposure ratio is always measured as weighted counts divided by `TOTAL_ENTRIES`.

```text
exposure = (complete_drafts + 0.5 * in_progress_drafts) / 150
```

For stack pairs, the same denominator applies and the configured combo cap is used as the ceiling.

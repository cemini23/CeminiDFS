# Handoff to CeminiParlays

CeminiDFS writes a handoff CSV that CeminiParlays can read. The two CLIs stay split; the operator copies the file by hand.

CeminiDFS now writes this file next to the lineup output after `optimize`, `late-swap`, or `sim-rerank`, and also on `ceminidfs review` (even when the three review flags are off).

The handoff CSV columns are: `player,team,projection,lineup_exposure_pct,game,implied_total`. `implied_total` may be blank. No FanDuel contest IDs, no salary.

## Artifact

| Artifact | Typical path | Columns to use |
|----------|--------------|----------------|
| Handoff CSV | `runs/{season}_week_{N}/ceminidfs_handoff.csv` | player, team, projection, lineup_exposure_pct, game, implied_total |

## CeminiParlays may read

The operator copies the handoff CSV and CeminiParlays reads the copy.

## `--from-ceminidfs` (Parlays reads; DFS only writes)

Copy `ceminidfs_handoff.csv` into the Parlays slate folder. Then:

```bash
ceminiparlays compose --lines runs/slate/lines.csv --auto \
  --from-ceminidfs runs/slate/ceminidfs_handoff.csv
```

Missing file prints `CEMINIDFS_HANDOFF_MISSING` and continues. High DFS lineup share prints an exposure note. The flag does not drop legs, reprice, or submit. No live pipe. The two CLIs stay split.

## What CeminiDFS gives back

Nothing at runtime. CeminiDFS does not read CeminiParlays output. After the slate, the operator may paste the Recap Desk notes from `GROK-BOTS.md` into a local brief. The Recap Desk is live in Grok Bot.app; it still does not write this repo.

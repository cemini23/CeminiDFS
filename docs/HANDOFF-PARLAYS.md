# Handoff to CeminiParlays

CeminiDFS writes a handoff CSV that CeminiParlays can read. The two CLIs stay split; the operator copies the file by hand.

CeminiDFS now writes this file next to the lineup output after `optimize`, `late-swap`, or `sim-rerank`, and also on `ceminidfs review` (even when the five review flags are off).

The handoff CSV columns are: `player,team,projection,lineup_exposure_pct,game,implied_total,injury_status`. `projection` is `fd_projection` when that column is present. `implied_total` stays blank when no cited total exists. The file drops DST, DEF, and D rows. No FanDuel contest IDs, no salary.

`ceminidfs research-export env` writes `environment.csv`. Pass that file to `ceminiparlays compose --environment`. `review`, `optimize`, and `run` accept `--environment` and copy `implied_total` onto the handoff. A blank cell stays blank.

## Artifact

| Artifact | Typical path | Columns to use |
|----------|--------------|----------------|
| Handoff CSV | `runs/{season}_week_{N}/ceminidfs_handoff.csv` | player, team, projection, lineup_exposure_pct, game, implied_total, injury_status |
| Environment CSV | `ceminidfs research-export env --out environment.csv` | path for `ceminiparlays compose --environment` |

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

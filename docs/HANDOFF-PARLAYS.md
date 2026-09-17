# Handoff to CeminiParlays

CeminiDFS and CeminiParlays stay two CLIs. CeminiDFS builds DFS projections and
GPP lineups. CeminiParlays builds sportsbook tickets. Neither CLI calls the other.

The handoff is a file copy by the operator. There is no live pipe and no shared
database.

## CeminiParlays may read

The operator copies a file and CeminiParlays reads the copy.

| Artifact | Typical path | Columns to use |
|----------|--------------|----------------|
| Canonical / project CSV | `runs/{season}_week_{N}/canonical_projections_{season}_w{N}.csv` | player, team, projection |
| Implied team totals / Vegas columns | same canonical CSV, if present | implied team total, spread, total |
| Weather / stadium fields | same canonical CSV, if present | weather, wind, roof type |

Use the projection, the implied team totals, and the weather fields as research
inputs. Do not treat a projection as a price.

## CeminiParlays must not read

- Committed salary CSVs (FanDuel / DraftKings manual exports).
- `.env` or any other secret.
- FanDuel contest IDs.
- Lineup upload files as a product (`*_fanduel_upload.csv`, `*_fanduel_ids.csv`).

## `--from-ceminidfs` (specified, not built)

A future CeminiParlays flag could read a CeminiDFS projection file in one step.
The flag is **specified, not built**. Do not implement it in CeminiDFS. Do not
add a live pipe from CeminiParlays into CeminiDFS.

Until that flag ships, the operator copies the CSV by hand. The two CLIs stay
split.

## What CeminiDFS gives back

Nothing at runtime. CeminiDFS does not read CeminiParlays output. After the slate,
the operator may paste the Recap Desk notes from
[`GROK-BOTS.md`](GROK-BOTS.md) into a local brief. The Recap Desk does not write
this repo.

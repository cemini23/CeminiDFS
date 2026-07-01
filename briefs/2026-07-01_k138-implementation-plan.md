# K138 — GitHub DFS eval (2026-07-01)

**Source:** `OSINT WORKSPACE/wiki/sources/eval-github-repo-plan-dfs-marl-poker-osint-2026-07-01.md`

## CeminiDFS scope

| Repo | K138 verdict | Action |
|------|--------------|--------|
| cwendt94/espn-api | **Adopt** (MIT) | Optional `[espn]` extra; injury overlay when `league_id` configured |
| BenBrostoff/draftfast | **CONDITIONAL-GO → Reject** | No LICENSE file on GitHub; overlaps pydfs (K128 reference-only) |
| jokecamp/FootballData | Reference-only | Wiki note; nflverse remains canonical |
| statsbomb/open-data | Reject | Non-commercial UA |

## Deliverables

| ID | Patch | Acceptance |
|----|-------|------------|
| K138-1 | `docs/espn-api-eval.md` + ROADMAP + K128 footnote | Posture documented |
| K138-2 | `data/espn.py` + `[espn]` optional dep | Injury map from ESPN league roster |
| K138-3 | `ceminidfs espn probe` + config `espn_adjunct` | Probe prints roster injury counts |
| K138-4 | Wire overlay into `project_week` canonical rows | Fills empty `injury_status` when enabled |
| K138-5 | Tests with mocked League | ✅ pytest green |

## Out of scope

- draftfast install (no license file)
- PM / poker steals from same batch
- ESPN without operator `league_id`

## Verify

```bash
pytest tests/test_espn_k138.py tests/ -q
ruff check src/ceminidfs tests
```

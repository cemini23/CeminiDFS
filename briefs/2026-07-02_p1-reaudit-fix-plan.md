# P1 re-audit fix plan — CeminiDFS follow-up sprint (6 backlog items + 2 GLM/UX riders)

**Date:** 2026-07-02
**Status:** ✅ **SHIPPED** — 297 tests pass, extension v1.2.0
**Source audit:** `briefs/2026-07-02_cursor-audit-reaudit-synthesis.md` (verdict: SHIP-WITH-FIXES; these are the P1 backlog items)
**Base:** `main` @ `ccc7171` **plus the uncommitted 15-fix sprint** (274 passed, 1 skipped). Phase 0 commits that state first — do not branch off a dirty tree.
**Executors:** 3 parallel subagents (WS-1, WS-2, WS-3), zero file overlap, merged sequentially 2 → 3 → 1 (any order is safe; 2-before-3 lets the extension manual checklist run against the final API).

---

## 0. Fix traceability (P1 # → workstream)

| # | Fix | Source | Workstream | Files touched |
|---|-----|--------|-----------|---------------|
| 1 | `merge_adp_csv` default `add_unmatched=False` | Kimi/GLM consensus | **WS-1** | `normalize_adp.py`, `cli.py`, `test_bbm_core.py` (1 test) |
| 2 | Advisory pivot: no archetype mutation on GET recs | GLM | **WS-2** | `session.py` |
| 3 | Disambiguation: `ambiguous[]` + `player_id` from `/api/pick` and `/api/sync` | Kimi | **WS-2** (server) + **WS-3** (client) | `api_server.py`, `ledger.py`, `content.js` |
| 4 | `/api/sync` skips names already in `picks` (undo ordering) | GLM | **WS-2** | `api_server.py` |
| 5 | Elite RB check: exact `merge_name`, not substring | Gemini | **WS-2** | `archetype.py` |
| 6 | Season data: nflreadpy fetch for W17 + byes, hardcoded fallback | Gemini/GLM | **WS-1** | `schedule.py`, `cli.py` |
| 7 | `pivot_warning` (+ new `pivot_to`) top-level even when recs empty | GLM | **WS-2** | `session.py`, `api_server.py` |
| 8 | Extension: pivot banner + ambiguous-name UI | UX rider on #2/#3 | **WS-3** | `content.js`, `styles.css`, `manifest.json` |

**File ownership (hard rule — no workstream edits another's files):**

- **WS-1 "Data & season":** `src/ceminidfs/bbm/normalize_adp.py`, `src/ceminidfs/bbm/schedule.py`, `src/ceminidfs/bbm/cli.py`, `tests/bbm/test_adp_and_schedule.py` (new), `tests/bbm/conftest.py` (**one additive autouse fixture**, §2.5), `tests/bbm/test_bbm_core.py` (**exactly one test edit**, §2.5)
- **WS-2 "Server & pivot":** `src/ceminidfs/bbm/api_server.py`, `src/ceminidfs/bbm/session.py`, `src/ceminidfs/bbm/archetype.py`, `src/ceminidfs/bbm/ledger.py`, `tests/bbm/test_api_contracts.py`, `tests/bbm/test_practice_and_pivots.py`
- **WS-3 "Extension":** `extension/bbm-copilot/content.js`, `extension/bbm-copilot/styles.css`, `extension/bbm-copilot/manifest.json`, `extension/bbm-copilot/README.md` (optional doc touch-up)

Nobody edits `tests/bbm/test_identity_exposure.py`, `practice.py`, `recommender.py`, `registry.py`, `config.py`, `reconcile.py`, or `popup.*`. `cli.py` is WS-1's **only** because both of its changes (ADP flag, `refresh-schedule` subcommand) live there; WS-2 must not touch it (the `get_recommendations` signature it imports is preserved, see contract #1).

---

## 1. Interface contracts (frozen before coding; WS-3 builds against WS-2's)

1. **`session.get_recommendations(round_num, pick_num, archetype_str, draft_id, limit=3) -> list[dict]`** — signature and return shape unchanged (CLI + practice.py keep working untouched). Becomes a thin wrapper over #2 that stuffs `pivot_warning` into `results[0]` exactly as today.
2. **`session.get_recommendations_meta(round_num, pick_num, archetype_str, draft_id, limit=3) -> dict`** — new. Returns `{"recommendations": list[dict], "pivot_warning": str | None, "pivot_to": str | None}`. Advisory pivots **never** change the scoring archetype and never write the DB; `pivot_to` is the suggested archetype letter (e.g. `"B"`) when the advisory fires and `pivot_applied` is still 0, else `None`.
3. **`ledger.get_player_by_id(player_id, db_path=None) -> dict | None`** — new. Exact `players_dim` PK lookup, same dict shape as `get_players_by_name` entries. No fuzzy, no stub.
4. **HTTP API (additive only; no existing field is removed or renamed):**
   - `GET /api/recommendations` — `"pivot_warning": str|null` is now sourced from meta (present even when `recommendations` is `[]`); new sibling `"pivot_to": "A"–"E"|null`.
   - `POST /api/pick` body: `{draft_id, name?: str, player_id?: str}` — at least one of name/player_id. `player_id` path: found → record; missing → `404 {"error": "Player not found: <player_id>"}`. Name path unchanged, but ambiguous `matches[]` entries gain `"player_id"` (alongside existing `name/position/team/index`).
   - `POST /api/taken` body: same `{draft_id, name?, player_id?}` contract. Unknown `player_id` → 404 (stubs remain a **name-path-only** behavior); ambiguous `matches[]` entries gain `"player_id"`.
   - `POST /api/sync` response gains `"skipped_existing": [names], "skipped_count": int` (players resolved but already in this draft's `picks` or `room_taken`; they are **not** re-recorded). Each `ambiguous[].matches[]` entry gains `"player_id"` and `"index"`. `synced` now contains only newly recorded players.
5. **`schedule.py` public API** — `get_bye_week`, `get_week17_matchups`, `are_opponents_week17` keep their signatures; they now consult a cached-JSON layer with the hardcoded 2026 constants as fallback. Constants `WEEK_BYES`, `BYE_WEEKS_2026`, `WEEK17_MATCHUPS_2026` stay defined (config re-export `BYE_WEEKS` untouched). New: `DEFAULT_SEASON`, `get_schedule_cache_path`, `fetch_season_schedule`, `save_schedule_cache`, `load_schedule_cache`, `clear_schedule_memo`.
6. **`normalize_adp.merge_adp_csv(csv_path, registry, *, add_unmatched: bool = False)`** — default flipped. `AdpMergeResult` shape unchanged.

---

## 2. Workstream 1 — "Data & season" (fixes #1, #6)

### 2.1 `merge_adp_csv` default flip (fix #1) — `src/ceminidfs/bbm/normalize_adp.py`

Line 239: change `add_unmatched: bool = True` → `add_unmatched: bool = False`. Extend the docstring:

```python
def merge_adp_csv(
    csv_path: Path | str,
    registry: dict[str, Any],
    *,
    add_unmatched: bool = False,
) -> AdpMergeResult:
    """Update registry ADP values from a BBTB-style CSV (name + adp columns).

    Unmatched names are reported, never added, unless add_unmatched=True is
    passed explicitly — auto-adding created junk team="FA" rows (2026-07-02 audit).
    """
```

No other logic changes — the `add_unmatched` branch body stays (it is the explicit opt-in path).

### 2.2 CLI opt-in flag (fix #1) — `src/ceminidfs/bbm/cli.py`

Both refresh parsers gain the flag:

```python
    refresh_parser.add_argument(
        "--add-unmatched", action="store_true",
        help="Insert unmatched CSV names as new team=FA registry rows (off by default)",
    )
```

(same `add_argument` on `weekly_parser`). Thread it through:

```python
def _refresh_registry(
    adp_csv: Path,
    projections_csv: Path | None = None,
    add_unmatched: bool = False,
) -> tuple[Any, Any | None, int] | None:
    ...
    adp_result = merge_adp_csv(adp_csv, registry, add_unmatched=add_unmatched)
```

`_cmd_refresh_adp` passes `_refresh_registry(args.csv, add_unmatched=args.add_unmatched)`; `_cmd_refresh_weekly` passes `_refresh_registry(args.adp, args.projections, add_unmatched=args.add_unmatched)`. `_print_refresh_summary` already prints the unmatched list — the operator sees exactly what was skipped and can re-run with `--add-unmatched` or fix the CSV.

### 2.3 Dynamic season schedule (fix #6) — `src/ceminidfs/bbm/schedule.py`

Replace the module docstring ("2026 bye-week calendar…" → "Season schedule data (byes + W17) — nflreadpy cache with hardcoded 2026 fallback.") and delete the `TODO(K-next)` comment (this is that TODO). Keep all three hardcoded structures verbatim as the fallback. Add:

```python
import json
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

DEFAULT_SEASON: Final[int] = 2026
_SCHEDULE_LOADERS: Final[tuple[str, ...]] = ("load_schedules", "import_schedules")


def get_schedule_cache_path(season: int = DEFAULT_SEASON) -> Path:
    """JSON cache written by `ceminidfs bbm refresh-schedule` (data/bbm is not git-tracked)."""
    return Path("data/bbm") / f"schedule_{season}.json"


def fetch_season_schedule(season: int = DEFAULT_SEASON) -> dict[str, Any]:
    """Fetch REG-season schedule via nflreadpy; derive per-team byes + W17 pairs.

    Raises ImportError (install hint) if nflreadpy is missing, ValueError if the
    fetched season looks incomplete (schedule not published yet).
    """


def save_schedule_cache(data: dict[str, Any], path: Path | None = None) -> Path: ...
def load_schedule_cache(season: int = DEFAULT_SEASON, path: Path | None = None) -> dict[str, Any] | None: ...
def clear_schedule_memo() -> None: ...   # _active_schedule.cache_clear(); test/CLI hook
```

Implementation notes:

- **`fetch_season_schedule`** mirrors `data/rosters.py` patterns but stays self-contained (no `ceminidfs.data` import — that pulls pandas; the `bbm` extra already includes `nflreadpy`): local `_require_nflreadpy()` raising `ImportError("Install nflreadpy with `pip install nflreadpy` to fetch schedule data.")`, `_call_loader(module, _SCHEDULE_LOADERS, season)` with the same `TypeError → loader(seasons=season)` retry. Convert to rows **without pandas/pyarrow**: `data.to_dicts()` if the frame has it (polars), else `data.to_dict("records")` (pandas), else `list(data)`.
- Filter rows to `game_type == "REG"` and `int(row["season"]) == season`. Build `weeks_played: defaultdict[str, set[int]]` from `home_team`/`away_team` per `week`. `all_weeks = set(range(1, max_week + 1))`. `bye_weeks = {team: min(missing) for team, missing in ... if len(missing) == 1}`. `week17_matchups = [(away, home) for rows with week == 17]`.
- **Completeness guard:** `if len(bye_weeks) < 28 or len(week17_matchups) < 14: raise ValueError(f"{season} schedule incomplete ({len(bye_weeks)} byes, {len(week17_matchups)} W17 games) — season not published yet?")`.
- Return `{"season": season, "fetched": date.today().isoformat(), "bye_weeks": {...}, "week17_matchups": [[a, b], ...]}` (JSON-safe lists, not tuples).
- **`load_schedule_cache`** returns `None` on missing file, JSON decode error, season mismatch, or the same completeness guard failing — never raises.
- **Resolution layer:**

```python
@lru_cache(maxsize=1)
def _active_schedule() -> tuple[dict[str, int], tuple[tuple[str, str], ...], str]:
    """(bye_weeks, w17_matchups, source) — 'cache' when a valid JSON cache exists, else 'hardcoded'."""
    cached = load_schedule_cache(DEFAULT_SEASON)
    if cached is not None:
        byes = {str(t).upper(): int(w) for t, w in cached["bye_weeks"].items()}
        w17 = tuple((str(a).upper(), str(b).upper()) for a, b in cached["week17_matchups"])
        return byes, w17, "cache"
    return dict(BYE_WEEKS_2026), tuple(WEEK17_MATCHUPS_2026), "hardcoded"
```

- Rewire the three public functions through it (behavior identical when no cache exists):

```python
def get_bye_week(team: str) -> int | None:
    return _active_schedule()[0].get(team.strip().upper())


def get_week17_matchups() -> list[tuple[str, str]]:
    return list(_active_schedule()[1])


def are_opponents_week17(team_a: str, team_b: str) -> bool:
    a, b = team_a.strip().upper(), team_b.strip().upper()
    return any({a, b} == {t1, t2} for t1, t2 in _active_schedule()[1])
```

No importer changes needed: `config.py` re-exports, `registry.py`/`session.py`/`backtest.py` (`get_bye_week`) and `recommender.py` (`are_opponents_week17`) all go through functions. `config.BYE_WEEKS is schedule.BYE_WEEKS_2026` stays true (fallback constant untouched).

### 2.4 CLI `refresh-schedule` (fix #6) — `src/ceminidfs/bbm/cli.py`

```python
    schedule_parser = subparsers.add_parser(
        "refresh-schedule", help="Fetch season byes + W17 matchups via nflreadpy"
    )
    schedule_parser.add_argument("--season", type=int, default=2026, help="Season year (default: 2026)")
```

`handler_map` gains `"refresh-schedule": _cmd_refresh_schedule`; add `refresh-schedule` to the "Available:" help string.

```python
def _cmd_refresh_schedule(args: argparse.Namespace) -> int:
    from ceminidfs.bbm.schedule import (
        clear_schedule_memo,
        fetch_season_schedule,
        save_schedule_cache,
    )

    try:
        data = fetch_season_schedule(args.season)
    except Exception as exc:  # ImportError, ValueError, network errors from nflreadpy
        print(f"Error: {exc}", file=sys.stderr)
        print("Hardcoded 2026 schedule fallback remains active.", file=sys.stderr)
        return 1
    path = save_schedule_cache(data)
    clear_schedule_memo()
    print(
        f"Schedule cache written: {path} "
        f"({len(data['bye_weeks'])} team byes, {len(data['week17_matchups'])} W17 games)"
    )
    return 0
```

Broad `except Exception` is intentional (same rationale as the overlay degrade in the 07-01 plan; ruff has no BLE rule enabled). Failure never breaks drafting — the fallback stays live.

### 2.5 Shared-file test edits (exactly two, both WS-1's)

1. **`tests/bbm/test_bbm_core.py::test_merge_adds_unmatched_players`** (line 151) — the default flip is the point of fix #1, so this test switches to the explicit opt-in: `result = merge_adp_csv(csv_path, registry, add_unmatched=True)`. All assertions unchanged. **No other line in this file may be touched.**
2. **`tests/bbm/conftest.py`** — one **additive autouse fixture** so every BBM test (including the frozen `test_identity_exposure.py::test_schedule_w17_and_bye_parity` / `test_config_bye_week_lookup`, which assert `get_bye_week("KC") == 5` etc.) runs against the hardcoded fallback even when the dev machine has a real `data/bbm/schedule_2026.json`:

```python
@pytest.fixture(autouse=True)
def isolated_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Pin schedule lookups to the hardcoded fallback (no real cache leaks into tests)."""
    from ceminidfs.bbm import schedule

    monkeypatch.setattr(
        schedule,
        "get_schedule_cache_path",
        lambda season=schedule.DEFAULT_SEASON: tmp_path / f"schedule_{season}.json",
    )
    schedule.clear_schedule_memo()
    yield tmp_path
    schedule.clear_schedule_memo()
```

The existing `bbm_db` fixture is untouched. (Non-`tests/bbm/` suites don't need this: nothing under `tests/` outside `tests/bbm/` calls schedule functions, and the cache file won't exist in CI.)

### 2.6 Tests — `tests/bbm/test_adp_and_schedule.py` (new)

Schedule tests rely on the autouse `isolated_schedule` fixture from §2.5 (request it by name where the `tmp_path` it yields is needed for writing a fake cache).

| Test | Asserts |
|------|---------|
| `test_merge_adp_default_skips_unmatched` | `merge_adp_csv(csv, build_seed_registry())` with a `Test Prospect,145.0,WR` row → `added == 0`, `matched == 0`, `unmatched == ["Test Prospect"]`, and **no** `team="FA"` row named "Test Prospect" in `registry["players"]` |
| `test_merge_adp_opt_in_still_adds` | same CSV with `add_unmatched=True` → `added == 1`, player present with `team == "FA"`, `signal == "NEUTRAL"` (guards the opt-in path stays intact) |
| `test_refresh_registry_threads_add_unmatched` | monkeypatch `cli.ensure_initialized`/`cli.load_registry`/`cli.save_registry`/`cli.sync_players_from_registry` to no-ops and `cli.merge_adp_csv` to capture kwargs (csv file must exist — write a 1-row tmp CSV); `_refresh_registry(csv_path)` → captured `add_unmatched is False`; `_refresh_registry(csv_path, add_unmatched=True)` → `True` |
| `test_schedule_fallback_when_no_cache` (`isolated_schedule`) | `get_bye_week("KC") == 5`, `are_opponents_week17("KC", "DEN") is True`, `("KC", "CAR")` False, `_active_schedule()[2] == "hardcoded"` |
| `test_schedule_cache_overrides_hardcoded` (`isolated_schedule`) | write JSON `{"season": 2026, "bye_weeks": {"KC": 7, ... 28+ teams}, "week17_matchups": [["KC","LV"], ... 14+ pairs]}`; after `clear_schedule_memo()` → `get_bye_week("KC") == 7`, `are_opponents_week17("KC", "LV") is True`, `("KC", "DEN")` False, source `"cache"` |
| `test_schedule_cache_rejected_when_incomplete` (`isolated_schedule`) | cache JSON with 3 teams / 1 matchup → `load_schedule_cache` returns `None`; functions serve hardcoded values |
| `test_fetch_season_schedule_derives_byes_and_w17` | monkeypatch `schedule._require_nflreadpy` to a fake module whose `load_schedules` returns row dicts: 32 teams × weeks 1–18 with one hole per team, W17 rows present, plus one `game_type="POST"` row that must be ignored → `bye_weeks` exact, `week17_matchups` exact, POST row excluded |
| `test_fetch_season_schedule_rejects_incomplete` | fake frame with 4 teams → `pytest.raises(ValueError, match="incomplete")` |
| `test_fetch_missing_nflreadpy_raises_hint` | `_require_nflreadpy` monkeypatched to raise → `pytest.raises(ImportError, match="pip install nflreadpy")` |
| `test_refresh_schedule_cli_writes_cache` (`isolated_schedule`) | monkeypatch `schedule.fetch_season_schedule` to return a valid dict; `_cmd_refresh_schedule(Namespace(season=2026))` → returns 0, JSON file exists, subsequent `get_bye_week` serves the fake value |

---

## 3. Workstream 2 — "Server & pivot" (fixes #2, #3-server, #4, #5, #7)

### 3.1 Advisory pivot stops mutating the scoring context (fix #2) — `src/ceminidfs/bbm/session.py`

Restructure `get_recommendations` (lines 164–234) into the meta/wrapper pair from contracts #1–2. The meta function is the current body with **one line deleted** — `draft_state.archetype = pivot_result.new_archetype` (line 203) — so recommendations are scored against the *primary* (DB) archetype until the operator explicitly confirms:

```python
def get_recommendations_meta(
    round_num: int,
    pick_num: int,
    archetype_str: str,
    draft_id: str,
    limit: int = 3,
) -> dict[str, Any]:
    """Top-N recommendations plus advisory pivot metadata.

    Advisory pivots are surfaced as pivot_warning/pivot_to only — the scoring
    archetype never changes until 'archetype X' / POST /api/pivot is confirmed.
    GET paths never write the DB.
    """
    empty = {"recommendations": [], "pivot_warning": None, "pivot_to": None}
    draft_state = build_draft_state(draft_id, round_num)
    if draft_state is None:
        return empty

    if archetype_str:            # explicit operator override — still honored
        try:
            draft_state.archetype = Archetype(archetype_str)
        except ValueError:
            pass

    available = get_available_models(draft_id)
    pivot_result = pivot_state_machine(
        primary=draft_state.archetype,
        roster=draft_state.roster,
        round_num=round_num,
        board=available,
    )

    pivot_warning = None
    pivot_to = None
    if pivot_result.new_archetype and not is_pivot_applied(draft_id):
        pivot_to = pivot_result.new_archetype.value
        pivot_warning = (
            (pivot_result.warning or f"Pivot to {pivot_to}")
            + f" — advisory only; confirm with 'archetype {pivot_to}' or POST /api/pivot"
        )
        # NOTE: deliberately no draft_state.archetype mutation here (P1 #2).

    ...  # exposure_fn, recommend_top3, results-building loop unchanged
    return {"recommendations": results, "pivot_warning": pivot_warning, "pivot_to": pivot_to}


def get_recommendations(
    round_num: int, pick_num: int, archetype_str: str, draft_id: str, limit: int = 3
) -> list[dict[str, Any]]:
    """CLI bridge — top-N display dicts; pivot warning attached to results[0]."""
    meta = get_recommendations_meta(round_num, pick_num, archetype_str, draft_id, limit=limit)
    results = meta["recommendations"]
    if meta["pivot_warning"] and results:
        results[0]["pivot_warning"] = meta["pivot_warning"]
    return results
```

`cli.py` (line 333) and `practice.py` (line 130) read `recs[0]["pivot_warning"]` — unchanged, untouched.

### 3.2 `pivot_warning`/`pivot_to` survive empty recs (fix #7) — `src/ceminidfs/bbm/api_server.py`

`_handle_recommendations` (lines 213–266): replace the `session.get_recommendations(...)` call with `meta = session.get_recommendations_meta(...)`, iterate `meta["recommendations"]` for `formatted_recs`, and change the response to:

```python
        self._send_json_response({
            "draft_id": draft_id,
            "round": current_round,
            "pick_num": pick_num,
            "archetype": archetype,
            "pivot_warning": meta["pivot_warning"],
            "pivot_to": meta["pivot_to"],
            "recommendations": formatted_recs,
        })
```

This deletes the lossy `recs[0].get("pivot_warning") if recs else None` (line 264) — the GLM finding.

### 3.3 `player_id` lookup (fix #3, ledger side) — `src/ceminidfs/bbm/ledger.py`

New function next to `get_players_by_name` (contract #3):

```python
def get_player_by_id(player_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Fetch one players_dim row by exact player_id (extension disambiguation echo-back)."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
        FROM players_dim WHERE player_id = ?
        """,
        (player_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "player_id": row[0], "name": row[1], "team": row[2], "position": row[3],
        "bye_week": row[4], "tier": row[5], "cap_pct": row[6], "adp": row[7],
        "signal": row[8], "injury_fade": bool(row[9]),
    }
```

No other `ledger.py` change.

### 3.4 `/api/pick` + `/api/taken` disambiguation contract (fix #3, server side) — `src/ceminidfs/bbm/api_server.py`

Both handlers get the same head (shown for `_handle_pick`; `_handle_taken` is identical except its stub fallback stays on the name path):

```python
        name = body.get("name")
        player_id = body.get("player_id")

        if player_id is not None and not isinstance(player_id, str):
            self._send_error("Invalid player_id", status=400)
            return
        if not player_id and (not name or not isinstance(name, str)):
            self._send_error("Missing or invalid name", status=400)
            return
        ...
        if player_id:
            player = ledger.get_player_by_id(player_id)
            if player is None:
                self._send_error(f"Player not found: {player_id}", status=404)
                return
        else:
            player = ledger.resolve_player_query(name)
            ...  # existing ambiguous / 404 / stub flows unchanged
```

In **both** ambiguous response builders (`_handle_pick` lines 380–394, `_handle_taken` lines 445–460) add `"player_id": m.get("player_id")` to each match dict. `_handle_taken`'s docstring gains: "player_id path never stubs — stubs are a name-path fallback only."

### 3.5 `/api/sync` skips already-recorded players + ambiguous parity (fixes #3, #4) — `src/ceminidfs/bbm/api_server.py`

In `_handle_sync` (lines 268–348), after the draft-state fetch add:

```python
        session = _get_session()
        already_recorded = session.get_taken_player_ids(draft_id)  # picks(is_mine=1) ∪ room_taken
        skipped_existing: list[str] = []
```

In the per-name loop, after a successful resolve and **before** `record_taken`:

```python
            if player["player_id"] in already_recorded:
                skipped_existing.append(player["name"])
                continue

            ledger.record_taken(draft_id, current_round, pick_num, player["player_id"])
            already_recorded.add(player["player_id"])   # dedupe repeats within one scan
```

Ambiguous entries gain parity with pick/taken — the match-dict comprehension adds `"player_id": m.get("player_id")` and `"index": i + 1` (enumerate). Response gains:

```python
            "skipped_existing": skipped_existing,
            "skipped_count": len(skipped_existing),
```

Why this fixes the GLM undo-ordering bug: a board scan always sees my own drafted players; previously they were re-recorded into `room_taken`, so `/api/undo` popped a bogus `taken` action before the real `pick`. Now my picks (and prior scans' taken rows) are skipped, `synced` reports only new players, and the action log stays clean. `record_taken`'s `INSERT OR IGNORE` remains as a second line of defense.

### 3.6 Elite RB exact matching (fix #5) — `src/ceminidfs/bbm/archetype.py`

Move the `normalize_name` import to module top (it's currently function-local in `_is_stack_anchor_gone`), add a module constant, and replace `_is_elite_rb_tier_empty` (lines 130–146):

```python
from ceminidfs.bbm.normalize_adp import normalize_name

# Exact normalized merge names — substring matching false-matched e.g. any "taylor"
# (2026-07-02 audit, Gemini). Refresh alongside the seed registry each season.
ELITE_RB_MERGE_NAMES: Final[frozenset[str]] = frozenset({
    "jahmyr gibbs",
    "bijan robinson",
    "jonathan taylor",
    "derrick henry",
    "chase brown",
    "devon achane",
    "ashton jeanty",
})


def _is_elite_rb_tier_empty(board: List[Player]) -> bool:
    """True when no elite-tier RB (exact merge_name match) remains on the board."""
    for player in board:
        if player.position != "RB":
            continue
        merge = normalize_name(player.merge_name or player.name)
        if merge in ELITE_RB_MERGE_NAMES:
            return False
    return True
```

(`typing.Final` import needed.) `normalize_name` is idempotent, so board players whose `merge_name` was set to a raw `name.lower()` (e.g. `"de'von achane"` from `build_draft_state`) still normalize to `"devon achane"`. `_is_stack_anchor_gone` may keep or drop its local import — dropping it for the module-level one is the tidy option.

### 3.7 Tests — `tests/bbm/test_api_contracts.py` (extend; one port per test, 18780+)

| Test | Port | Asserts |
|------|------|---------|
| `test_pick_ambiguous_includes_player_ids` | 18780 | POST /api/pick `{"name": "Chase"}` (LIKE-matches Ja'Marr Chase + Chase Brown) → 200, `ambiguous is True`, `len(matches) >= 2`, every match has non-empty `player_id`, `index`, `name`, `position`, `team`; `picks` table still empty |
| `test_pick_by_player_id` | 18781 | look up Chase Brown's id via `ledger.get_players_by_name("Chase Brown")[0]["player_id"]`; POST /api/pick `{"player_id": <id>}` → 200, `player.name == "Chase Brown"`, picks row exists; unknown id `"bbm:nope"` → 404 `"Player not found: bbm:nope"` |
| `test_taken_by_player_id_no_stub` | 18782 | POST /api/taken `{"player_id": <real id>}` → 200, `is_stub is False`, room_taken row exists; POST with `{"player_id": "bbm:ghost"}` → 404 and **zero** `stub:%` rows |
| `test_sync_ambiguous_reports_matches` | 18783 | POST /api/sync `{"names": ["Chase"]}` → `ambiguous_count == 1`, `ambiguous[0]["query"] == "Chase"`, matches carry `player_id` + `index`; `room_taken` empty |
| `test_sync_skips_already_picked` | 18784 | pick "Ja'Marr Chase" via /api/pick, then sync `{"names": ["Ja'Marr Chase", "Puka Nacua"]}` → `synced` == [Puka], `skipped_existing == ["Ja'Marr Chase"]`, `skipped_count == 1`; Chase's id **absent** from `room_taken`; then /api/undo → `undone == "taken"` (Puka), second undo → `undone == "pick"` (Chase) — the exact GLM ordering scenario |
| `test_sync_rescan_reports_skipped` | 18785 | sync `{"names": ["Puka Nacua"]}` twice → second response `synced_count == 0`, `skipped_count == 1`; `action_log` has exactly one `taken` row for the draft |
| `test_pivot_warning_survives_empty_recs` | 18786 | forced-pivot monkeypatch (reuse `forced_pivot` pattern) **plus** `monkeypatch.setattr("ceminidfs.bbm.session.recommend_top3", lambda *a, **k: [])` → GET /api/recommendations → 200, `recommendations == []`, `pivot_warning` non-null, `pivot_to == "B"` |
| `test_pivot_to_cleared_after_apply` | 18787 | forced-pivot monkeypatch; POST /api/pivot `{"archetype": "B"}` → GET → `pivot_warning is None` and `pivot_to is None` |

Existing tests to re-verify unmodified: `test_recommendations_get_is_readonly` (still passes — warning present, `pivot_applied` 0), `test_pivot_endpoint_applies`, both sync tests (response is additive).

### 3.8 Tests — `tests/bbm/test_practice_and_pivots.py` (extend)

| Test | Asserts |
|------|---------|
| `test_advisory_pivot_keeps_primary_archetype` | create archetype-D draft; monkeypatch `session.pivot_state_machine` → `PivotResult(new_archetype=Archetype.B, warning="forced", trigger_reason="test")` and `session.recommend_top3` to capture `draft_state.archetype` and return `[]`; `get_recommendations_meta(6, 64, "", draft_id)` → captured archetype **is `Archetype.D`** (pre-fix it was B), `pivot_warning` contains "advisory only", `pivot_to == "B"`, `recommendations == []` |
| `test_get_recommendations_wrapper_attaches_warning` | same monkeypatches but `recommend_top3` returns one rec → `get_recommendations(...)` list has `results[0]["pivot_warning"]` set (CLI/practice contract intact) |
| `test_elite_rb_exact_no_substring_false_positive` | `_is_elite_rb_tier_empty([_player("Tyler Taylor", "RB", "CIN", 180)]) is True` (substring code returned False); `[_player("Jonathan Taylor", "RB", "IND", 8)]` → False; `[_player("Jonathan Taylor", "WR", "IND", 8)]` → True (position guard) |
| `test_elite_rb_matches_normalized_merge_name` | `_player("De'Von Achane", "RB", "MIA", 12)` (merge_name `"de'von achane"` via the helper) → `_is_elite_rb_tier_empty([...]) is False` |
| `test_get_player_by_id_roundtrip` (uses `bbm_db`) | `get_player_by_id(get_players_by_name("Puka Nacua")[0]["player_id"], db_path=bbm_db)["name"] == "Puka Nacua"`; `get_player_by_id("bbm:missing", db_path=bbm_db) is None` |

---

## 4. Workstream 3 — "Extension" (fixes #3-client, #8) — `content.js`, `styles.css`, `manifest.json`

Builds against contract #4. No JS test harness — manual checklist in §4.5.

### 4.1 Pivot banner + apply button — `content.js`

`fetchRecommendations` success path becomes:

```javascript
      renderPivotWarning(data.pivot_warning, data.pivot_to);
      renderRecommendations(data.recommendations || []);
```

New functions:

```javascript
  function renderPivotWarning(warning, pivotTo) {
    let el = panel.querySelector('#bbm-pivot');
    if (!warning) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.id = 'bbm-pivot';
      el.className = 'bbm-pivot-warning';
      const body = panel.querySelector('.bbm-body');
      body.insertBefore(el, body.querySelector('.bbm-section'));
    }
    el.innerHTML = `<span>${escapeHtml(warning)}</span>` + (pivotTo
      ? `<button class="bbm-btn bbm-btn-pivot" id="bbm-apply-pivot">Pivot → ${escapeHtml(pivotTo)}</button>`
      : '');
    const btn = el.querySelector('#bbm-apply-pivot');
    if (btn) btn.addEventListener('click', () => applyPivot(pivotTo));
  }

  async function applyPivot(archetype) {
    const statusEl = panel.querySelector('#bbm-sync-status');
    try {
      const res = await fetch(`${config.apiBase}/api/pivot`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId, archetype }),
      });
      const data = await res.json();
      statusEl.textContent = (!res.ok || data.error)
        ? (data.error || `Pivot failed (${res.status})`)
        : `Pivoted to ${archetype}`;
      fetchRecommendations();   // warning clears server-side (pivot_applied=1)
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
    }
  }
```

Rendering is idempotent per poll tick (3s interval): same warning → same DOM, warning gone → banner removed.

### 4.2 Ambiguous-name UI — `content.js`

One shared renderer; candidates POST back with the exact `player_id` from the API (no re-resolution race):

```javascript
  function renderAmbiguous(query, matches, endpoint) {
    // endpoint: '/api/pick' (Rec button flow) or '/api/taken' (Scan Board flow)
    let box = panel.querySelector('#bbm-ambiguous');
    if (!box) {
      box = document.createElement('div');
      box.id = 'bbm-ambiguous';
      box.className = 'bbm-ambiguous';
      panel.querySelector('.bbm-body').appendChild(box);
    }
    const row = document.createElement('div');
    row.className = 'bbm-ambiguous-row';
    row.innerHTML = `<div class="bbm-ambiguous-query">Which “${escapeHtml(query)}”?</div>`;
    (matches || []).slice(0, 4).forEach((m) => {
      const btn = document.createElement('button');
      btn.className = 'bbm-btn bbm-ambiguous-btn';
      btn.textContent = `${m.name} (${m.position || '?'} ${m.team || '?'})`;
      btn.addEventListener('click', async () => {
        await postResolved(endpoint, m.player_id);
        row.remove();
        if (!box.querySelector('.bbm-ambiguous-row')) box.remove();
      });
      row.appendChild(btn);
    });
    const dismiss = document.createElement('button');
    dismiss.className = 'bbm-btn bbm-btn-icon bbm-ambiguous-dismiss';
    dismiss.textContent = '✕';
    dismiss.addEventListener('click', () => {
      row.remove();
      if (!box.querySelector('.bbm-ambiguous-row')) box.remove();
    });
    row.appendChild(dismiss);
    box.appendChild(row);
  }

  async function postResolved(endpoint, playerId) {
    const statusEl = panel.querySelector('#bbm-sync-status');
    try {
      const res = await fetch(`${config.apiBase}${endpoint}`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId, player_id: playerId }),
      });
      const data = await res.json();
      statusEl.textContent = (!res.ok || data.error)
        ? (data.error || `Failed (${res.status})`)
        : `Recorded ${data.player?.name || playerId}`;
      fetchRecommendations();
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
    }
  }
```

Wire into the two flows:

- **`recordPick`** — after `const data = await res.json();`, before the error branch:

```javascript
      if (res.ok && data.ambiguous) {
        statusEl.textContent = `Ambiguous: ${data.query}`;
        renderAmbiguous(data.query, data.matches, '/api/pick');
        return;
      }
```

  (This also fixes the latent bug where an ambiguous 200 displayed "Recorded <name>" despite nothing being recorded.)

- **`scanBoard`** — replace the status line and surface ambiguity:

```javascript
      const ambiguousCount = data.ambiguous_count ?? 0;
      statusEl.textContent =
        `Synced ${data.synced_count ?? 0} — ${data.skipped_count ?? 0} known — ` +
        `${data.unmatched_count ?? 0} unmatched` +
        (ambiguousCount ? ` — ${ambiguousCount} ambiguous` : '');
      if (data.unmatched?.length) console.warn('BBM unmatched names:', data.unmatched);
      (data.ambiguous || []).slice(0, 3).forEach((entry) => {
        renderAmbiguous(entry.query, entry.matches, '/api/taken');
      });
      fetchRecommendations();
      if (!ambiguousCount) setTimeout(() => { statusEl.textContent = ''; }, 3000);
```

  (Skip the auto-clear when ambiguity is pending so the count stays visible.)

### 4.3 Styles — `styles.css`

Append, matching the existing panel palette:

```css
.bbm-pivot-warning {
  display: flex; align-items: center; gap: 8px; justify-content: space-between;
  margin: 6px 0; padding: 6px 8px; border-radius: 6px;
  background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.5);
  color: #fbbf24; font-size: 11px; line-height: 1.3;
}
.bbm-btn-pivot { flex-shrink: 0; }
.bbm-ambiguous { margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); }
.bbm-ambiguous-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin: 4px 0; }
.bbm-ambiguous-query { width: 100%; font-size: 11px; opacity: 0.8; }
.bbm-ambiguous-btn { font-size: 11px; padding: 2px 6px; }
```

### 4.4 Manifest — `manifest.json`

Bump `"version"` to `"1.2.0"`. Optional: append one line each to `README.md` for the pivot button and ambiguous chooser.

### 4.5 Manual checklist (attach results to PR)

1. `chrome://extensions` → reload unpacked → v1.2.0 shows.
2. **Contract curls** (serve running): `curl -s -X POST localhost:8765/api/pick -d '{"draft_id":"<id>","name":"Chase"}' -H 'Content-Type: application/json'` → `ambiguous: true` with `player_id` per match; repeat with `{"player_id": "<one of them>"}` → recorded. `/api/sync` with a picked player's name → appears in `skipped_existing`.
3. **Skip-picked**: Rec a pick in the panel, then Scan Board → status shows `… 1 known …` and `sqlite3 data/bbm/bbm7.db "SELECT COUNT(*) FROM room_taken rt JOIN picks p ON rt.player_id = p.player_id AND rt.draft_id = p.draft_id"` returns 0.
4. **Pivot banner**: practice draft, archetype D, take 0 RBs through R6 → amber banner with `Pivot → B` button appears; click → status `Pivoted to B`, banner clears on next poll, `drafts.pivot_applied = 1`.
5. **Ambiguous UI**: with a scan (or curl-seeded sync) returning ambiguity → "Which …?" row renders with candidate buttons; clicking one records it as taken (verify `room_taken`) and the row disappears; ✕ dismisses without recording.

---

## 5. Order of operations

```
Phase 0 (operator, before branching):
  - git add -A && git commit  → land the 15-fix sprint (the re-audit target) on main
  - .venv/bin/pytest -q       → confirm 274 passed, 1 skipped baseline
  - cp data/bbm/bbm7.db data/bbm/bbm7.db.bak-20260702   (habit; this sprint has no migration)

Phase 1 (parallel — the three workstreams are fully independent, no shared files):
  - WS-1 on branch fix/p1-a-data-season
  - WS-2 on branch fix/p1-b-server-pivot
  - WS-3 on branch fix/p1-c-extension
  Each: implement, add tests, run its own test files + ruff on owned paths.
  WS-3 has no Python tests — it validates against contract §1.4 and defers the
  manual checklist to Phase 3.

Phase 2 (sequential merges into main):
  1. Merge WS-2 → .venv/bin/pytest tests/ -q  (green)
  2. Merge WS-3 → tests again (no Python touched — smoke only)
  3. Merge WS-1 → .venv/bin/pytest tests/ -q && .venv/bin/ruff check src/ceminidfs tests

Phase 3 (post-merge ops, once):
  - ceminidfs bbm refresh-schedule            # writes data/bbm/schedule_2026.json (or warns + falls back)
  - ceminidfs bbm serve --slot 4              # run extension manual checklist §4.5
  - Optional next ADP refresh: note unmatched names now require --add-unmatched or a CSV fix
```

No interface dependency exists between workstreams (WS-3 codes against the frozen contract, not WS-2's branch), so any merge order works; the listed order just makes the manual checklist meaningful immediately.

---

## 6. Verification matrix (definition of done)

| Gate | Command | Pass criteria |
|------|---------|--------------|
| Unit/integration | `.venv/bin/pytest tests/ -q` | 274 baseline + ~23 new, 0 failures, 1 skip |
| Lint | `.venv/bin/ruff check src/ceminidfs tests` | clean |
| No junk FA on refresh | `merge_adp_csv` default call with unknown name | `added == 0`, name in `unmatched` |
| GET is advisory | forced pivot + GET /api/recommendations ×2 | `pivot_warning`/`pivot_to` set, `pivot_applied` still 0, recs scored on primary archetype |
| Empty-recs warning | GLM scenario test (18786) | `recommendations: []` with non-null `pivot_warning` |
| Sync hygiene | pick → scan → undo | undo pops `taken` before `pick` only for genuinely new taken rows; picked player never in `room_taken` |
| Disambiguation | curl checklist §4.5 step 2 | `player_id` round-trip records the chosen player |
| Schedule fallback | `mv data/bbm/schedule_2026.json /tmp` → run any rec | byes/W17 identical to hardcoded (source `"hardcoded"`), zero errors |
| Extension | manual checklist §4.5 | all 5 steps pass |

## 7. Rollback

- Code: one branch per workstream → `git revert -m 1 <merge-commit>` independently; no cross-branch dependencies.
- Data: `data/bbm/schedule_2026.json` is additive — deleting it restores hardcoded behavior instantly. No DB schema changes this sprint (`bbm7.db.bak-20260702` is belt-and-braces).
- Extension: reload previous unpacked version (v1.1.0) if the panel misbehaves.

## 8. Known risks / executor notes

- **`tests/bbm/test_bbm_core.py` is frozen except one named test** (`test_merge_adds_unmatched_players`, WS-1, §2.5). If any *other* test there fails, stop and report — do not edit.
- **WS-2 must not change `get_recommendations`'s signature or list-return shape** — `cli.py` (WS-1's file) and `practice.py` (nobody's) import it. The meta function is the only new surface.
- **Schedule tests must never hit the network.** All nflreadpy access goes through `schedule._require_nflreadpy()` precisely so tests can monkeypatch it. `_active_schedule` is `lru_cache`d — every test that touches cache state calls `clear_schedule_memo()` (use the `isolated_schedule` fixture).
- **`data/bbm/schedule_2026.json` uses a relative path**, same convention as `get_db_path()` — commands run from the repo root. A stale cache on the operator machine is harmless for 2026 (hardcoded data *is* the real 2026 schedule) but `refresh-schedule` should be re-run after any nflverse schedule correction.
- **Ambiguity matches ordering** (`ORDER BY adp ASC, name ASC`) is stable, but the extension intentionally posts `player_id`, not the `index`, so a mid-draft ADP refresh cannot mis-route a disambiguation click.
- **`/api/sync` skip uses `session.get_taken_player_ids`** (picks `is_mine=1` ∪ `room_taken`). Hypothetical `is_mine=0` rows in `picks` wouldn't be skipped — no current flow writes those in serve mode; `INSERT OR IGNORE` still absorbs them.
- **Elite RB list is seasonal data** (like `STACK_PAIRS`/`FADE_PLAYERS`): `ELITE_RB_MERGE_NAMES` must be refreshed alongside the seed registry each season — the constant's comment says so.
- WS-3's `renderAmbiguous` caps at 3 queries × 4 candidates to keep the panel usable on a noisy scan; the full lists remain in the JSON response and console.

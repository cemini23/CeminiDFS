"""Per-player, per-stat projection distributions for the CeminiParlays handoff.

This module is additive. It reads the existing per-stat models
(``pipeline.engine.build_diy_projections_from_frames`` ->
``models.stats.build_week_stats``) and reshapes one week into a long frame whose
columns are a fixed interop contract:

    player_name,player_key,stat_type,median,sd,family

``median`` and ``sd`` are in stat units (yards), not fantasy points. ``family``
is always ``lognormal``.

The per-stat standard deviation is not exposed by the stats models, so it is
derived from the repo's existing Monte-Carlo output instead of a hand-picked
constant. The simulation (``models.simulate.simulate_fd_points``) draws each
player's fantasy points from a lognormal with median ``fd_projection`` and a
per-player relative dispersion. We read that relative dispersion back off the
simulation output (sample ``sd / median`` per player) and apply it to each stat's
median. For a lognormal this is exact: ``sd = median * sqrt(exp(sigma_log^2) - 1)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ceminidfs.config import load_config
from ceminidfs.models.simulate import simulate_fd_points
from ceminidfs.pipeline import backtest
from ceminidfs.pipeline.engine import build_diy_projections_from_frames, normalize_join_key

DISTRIBUTION_COLUMNS = ("player_name", "player_key", "stat_type", "median", "sd", "family")
STAT_TYPES = ("pass_yds", "rush_yds", "rec_yds")
DISTRIBUTION_FAMILY = "lognormal"

# Fallbacks when the config carries no simulate block. The seed keeps the export
# reproducible run-to-run; it is a seed, not a dispersion constant.
DEFAULT_SIM_ITERATIONS = 5000
DEFAULT_SIM_SEED = 20261005

_INTERNAL_COLUMNS = (
    "player_name",
    "player_key",
    "player_id",
    "team",
    "stat_type",
    "median",
    "sd",
    "family",
)


def parse_season_week(token: str | int) -> tuple[int, int]:
    """Parse a ``<season>_<week>`` token such as ``2026_5`` into a tuple."""

    text = str(token).strip()
    for separator in ("_", "-"):
        if separator in text:
            season_text, week_text = text.split(separator, 1)
            try:
                return int(season_text), int(week_text)
            except ValueError as exc:
                raise ValueError(
                    f"Could not parse season_week {token!r}; expected e.g. 2026_5"
                ) from exc
    raise ValueError(f"Could not parse season_week {token!r}; expected e.g. 2026_5")


def build_week_distributions(
    season: int,
    week: int,
    *,
    config: Mapping[str, Any] | None = None,
    n_iterations: int | None = None,
    seed: int | None = None,
) -> pd.DataFrame:
    """Return one week of per-player, per-stat lognormal distributions.

    The result carries the six contract columns plus ``player_id`` and ``team``
    for the market join. Only players with a positive median for a stat are
    emitted, so no zero-mean rows reach the handoff.
    """

    cfg = dict(config or load_config())
    pbp = backtest.load_season_pbp(season)
    vegas = backtest.resolve_vegas_for_week(season, week)
    if vegas.empty:
        raise ValueError(
            f"No cached Vegas lines for {season} week {week}; run fetch first"
        )

    weather = backtest.resolve_weather_for_week(season, week, config=cfg)
    historical = backtest._historical_pbp(pbp, season, week)
    roster = backtest.roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        raise ValueError(f"No roster built for {season} week {week}; run fetch first")

    scored = build_diy_projections_from_frames(
        season,
        week,
        pbp,
        vegas,
        weather,
        roster,
        config=cfg,
    )
    if scored.empty:
        raise ValueError(f"No player stat projections built for {season} week {week}")

    dispersion = _relative_dispersion_from_simulation(
        scored,
        cfg,
        n_iterations=n_iterations,
        seed=seed,
    )
    return _melt_distributions(scored, dispersion)


def write_distributions_csv(distributions: pd.DataFrame, path: str | Path) -> Path:
    """Write the long distribution frame in the fixed six-column schema."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    frame = distributions.copy()
    for column in ("player_name", "player_key", "stat_type"):
        if column not in frame.columns:
            frame[column] = ""
    frame["family"] = DISTRIBUTION_FAMILY
    frame = frame.loc[:, list(DISTRIBUTION_COLUMNS)]
    frame.to_csv(out, index=False, lineterminator="\n")
    return out


def format_distributions_summary(distributions: pd.DataFrame, season: int, week: int) -> str:
    """Return a human-readable summary of one week of distributions."""

    lines = [
        f"CeminiDFS distributions — season {season} week {week}",
        f"Rows: {len(distributions)}",
        "",
        "Per stat_type:",
    ]
    if distributions.empty:
        lines.append("  (no rows)")
        return "\n".join(lines)

    counts = distributions.groupby("stat_type").size()
    for stat_type in STAT_TYPES:
        lines.append(f"  {stat_type:9s} n={int(counts.get(stat_type, 0))}")
    return "\n".join(lines)


def _relative_dispersion_from_simulation(
    scored: pd.DataFrame,
    config: Mapping[str, Any],
    *,
    n_iterations: int | None,
    seed: int | None,
) -> pd.Series:
    """Return per-player relative dispersion (sd / median) read off the simulation."""

    simulate_cfg = config.get("simulate", {}) if isinstance(config, Mapping) else {}
    if not isinstance(simulate_cfg, Mapping):
        simulate_cfg = {}

    iterations = n_iterations
    if iterations is None:
        iterations = int(simulate_cfg.get("n_iterations", DEFAULT_SIM_ITERATIONS) or DEFAULT_SIM_ITERATIONS)

    resolved_seed = seed
    if resolved_seed is None:
        configured = simulate_cfg.get("seed")
        resolved_seed = int(configured) if configured is not None else DEFAULT_SIM_SEED

    matrix = simulate_fd_points(
        scored,
        n_iterations=int(iterations),
        seed=int(resolved_seed),
        config=config,
    )
    if matrix.size == 0:
        return pd.Series(0.0, index=scored.index)

    medians = np.median(matrix, axis=1)
    deviations = np.std(matrix, axis=1, ddof=1)
    relative = np.divide(deviations, medians, out=np.zeros_like(deviations), where=medians > 0)
    return pd.Series(relative, index=scored.index)


def _melt_distributions(scored: pd.DataFrame, dispersion: pd.Series) -> pd.DataFrame:
    """Reshape scored per-stat projections into the long distribution frame."""

    names = scored.get("player_name", pd.Series("", index=scored.index)).astype(str)
    teams = scored.get("team", pd.Series("", index=scored.index)).astype(str)
    positions = scored.get("position", pd.Series("", index=scored.index)).astype(str)
    player_ids = scored.get("player_id", pd.Series("", index=scored.index)).astype(str)
    player_keys = [
        normalize_join_key(name, team, position)
        for name, team, position in zip(names, teams, positions)
    ]

    frames: list[pd.DataFrame] = []
    for stat_type in STAT_TYPES:
        if stat_type not in scored.columns:
            continue
        medians = pd.to_numeric(scored[stat_type], errors="coerce").fillna(0.0)
        mask = medians > 0
        if not mask.any():
            continue
        frames.append(
            pd.DataFrame(
                {
                    "player_name": names.loc[mask].to_numpy(),
                    "player_key": [key for key, keep in zip(player_keys, mask) if keep],
                    "player_id": player_ids.loc[mask].to_numpy(),
                    "team": teams.loc[mask].to_numpy(),
                    "stat_type": stat_type,
                    "median": medians.loc[mask].to_numpy(),
                    "sd": (medians.loc[mask] * dispersion.loc[mask]).to_numpy(),
                    "family": DISTRIBUTION_FAMILY,
                }
            )
        )

    if not frames:
        return pd.DataFrame(columns=_INTERNAL_COLUMNS)

    return pd.concat(frames, ignore_index=True)

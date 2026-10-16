"""Build the upgraded ``ceminidfs_handoff.csv`` contract.

The handoff is what a downstream parlays pricer reads to turn our model into
sportsbook prop prices. The old contract passed only FanDuel FPPG and a game
total, which is not enough to price a player prop. This module derives the
full player-level contract from a finished run:

- game environment (``implied_total``, ``spread``, ``game_id``)
- FanDuel points distribution (``fpts_median``, ``fpts_sigma``)
- zero-scrape synthetic ownership (``jev_proj_own``)
- the Jev regime routing (``jev_regime_state``, ``jev_regime_conf``)
- disaggregated stat-level GMM distributions (median/sigma/p15/p85)

Every stat band comes from the same conditional three-component regime mixture
the projection engine samples (``ceminidfs.models.simulate.sample_regime_gmm``).
Jev routes; Python samples. No sportsbook, ownership board, or paid projection
site is read, and nothing is scraped.

The builder reads a run directory (``runs/<season>_week_<week>``):

- ``player_projection_base.parquet`` -- per-stat model medians and ``join_key``
- ``canonical_projections_<season>_w<week>.csv`` -- slate id, FD id, salary
- ``artifacts/cache/<season>/week_<week>/vegas.parquet`` -- totals and spreads
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


class HandoffInputError(RuntimeError):
    """A handoff input exists on disk but cannot be read.

    A missing optional input stays lenient: the handoff degrades to an empty
    frame or ``None``. A file that is present but unreadable is a real defect,
    so it raises instead of silently collapsing to the fallback.
    """


# --------------------------------------------------------------------------- #
# Contract header. The order is fixed: CeminiParlays reads by column name, but
# a positional consumer must see the documented order.
# --------------------------------------------------------------------------- #
HANDOFF_BASE_COLUMNS = [
    "slate_id",
    "game_id",
    "player_id",
    "player_name",
    "team",
    "opp",
    "position",
    "implied_total",
    "spread",
    "fpts_median",
    "fpts_sigma",
    "jev_proj_own",
    "jev_regime_state",
    "jev_regime_conf",
]


@dataclass(frozen=True)
class StatSpec:
    """One disaggregated stat: source base columns, dispersion, output fields."""

    name: str
    sources: tuple[str, ...]
    cv: float
    fields: tuple[str, ...]


STAT_SPECS: tuple[StatSpec, ...] = (
    StatSpec("pass_yds", ("pass_yds",), 0.32, ("median", "sigma", "p15", "p85")),
    StatSpec("rush_yds", ("rush_yds",), 0.55, ("median", "sigma", "p15", "p85")),
    StatSpec("rec_yds", ("rec_yds",), 0.55, ("median", "sigma", "p15", "p85")),
    StatSpec("receptions", ("rec",), 0.42, ("median", "sigma")),
    StatSpec("pass_tds", ("pass_td",), 0.95, ("mean",)),
    StatSpec("rush_rec_tds", ("rush_td", "rec_td"), 1.00, ("mean",)),
)


def _stat_columns() -> list[str]:
    columns: list[str] = []
    for spec in STAT_SPECS:
        columns.extend(f"{spec.name}_{field}" for field in spec.fields)
    return columns


STAT_COLUMNS = _stat_columns()
HANDOFF_COLUMNS = HANDOFF_BASE_COLUMNS + STAT_COLUMNS

# Per-stat mean columns read from the projection base parquet.
BASE_STAT_COLUMNS = ("pass_yds", "pass_td", "rush_yds", "rush_td", "rec", "rec_yds", "rec_td")

DEFAULT_HANDOFF_ITERATIONS = 4000
DEFAULT_HANDOFF_SEED = 20261015
# (p85 - p15) of a standard normal. sigma divides the central band back out.
SIGMA_EFF_DENOMINATOR = 2.073
_EPSILON = 1.0e-9


@dataclass
class PlayerHandoff:
    """One player-level handoff record."""

    player_name: str
    player_id: str = ""
    slate_id: str = ""
    game_id: str = ""
    team: str = ""
    opp: str = ""
    position: str = ""
    implied_total: str = ""
    spread: str = ""
    fpts_median: str = ""
    fpts_sigma: str = ""
    jev_proj_own: str = ""
    jev_regime_state: str = ""
    jev_regime_conf: str = ""
    jev_provider: str = ""
    stats: dict[str, str] = field(default_factory=dict)
    p95_ceiling: float | None = None
    fpts_median_value: float | None = None
    jev_proj_own_value: float | None = None

    def row(self) -> list[str]:
        values: list[str] = [
            self.slate_id,
            self.game_id,
            self.player_id,
            self.player_name,
            self.team,
            self.opp,
            self.position,
            self.implied_total,
            self.spread,
            self.fpts_median,
            self.fpts_sigma,
            self.jev_proj_own,
            self.jev_regime_state,
            self.jev_regime_conf,
        ]
        values.extend(self.stats.get(column, "") for column in STAT_COLUMNS)
        return values

    def leverage_ratio(self) -> str:
        """``p95_ceiling_rate / jev_proj_own`` in percent points.

        The ceiling rate is the p95 ceiling relative to the median. It is a
        continuous leverage proxy: a high relative ceiling per unit ownership is
        a better GPP play than a chalky low-ceiling name.
        """

        if self.p95_ceiling is None or self.fpts_median_value in (None, 0.0):
            return ""
        own = self.jev_proj_own_value
        if own is None or own <= 0.0:
            return ""
        rate = float(self.p95_ceiling) / float(self.fpts_median_value)
        return f"{rate / float(own):.4f}"


@dataclass
class HandoffContext:
    """Player-level handoff records keyed by id and by normalized name."""

    players: dict[str, PlayerHandoff] = field(default_factory=dict)
    slate_id: str = ""

    def lookup(self, name: str, player_id: str | None = None) -> PlayerHandoff | None:
        if player_id:
            found = self.players.get(str(player_id))
            if found is not None:
                return found
        return self.players.get(normalize_handoff_name(name))

    def ordered(self) -> list[PlayerHandoff]:
        unique: dict[int, PlayerHandoff] = {}
        for record in self.players.values():
            unique.setdefault(id(record), record)
        return sorted(unique.values(), key=lambda record: normalize_handoff_name(record.player_name))

    def __len__(self) -> int:  # pragma: no cover - trivial.
        return len(self.ordered())


def normalize_handoff_name(name: Any) -> str:
    return " ".join(str(name or "").strip().lower().split())


# --------------------------------------------------------------------------- #
# Sampling. Reuses the engine's conditional regime mixture so stat bands and the
# FanDuel point band come from the same generative model.
# --------------------------------------------------------------------------- #
def _gmm_bands(
    medians: np.ndarray,
    sigmas: np.ndarray,
    weights: np.ndarray,
    *,
    n_iterations: int,
    seed: int,
) -> dict[str, np.ndarray]:
    """Return median/sigma/p15/p85/mean arrays for a stacked batch of draws."""

    from ceminidfs.models.simulate import median_recenter_factors, sample_regime_gmm

    medians = np.asarray(medians, dtype=float)
    sigmas = np.asarray(sigmas, dtype=float)
    weights = np.asarray(weights, dtype=float)
    factors = median_recenter_factors(medians, sigmas, weights)
    rng = np.random.default_rng(int(seed))
    draws = sample_regime_gmm(
        medians * factors,
        sigmas,
        weights,
        n_iterations=int(n_iterations),
        rng=rng,
    )
    p15, median, p85, p95 = np.quantile(draws, (0.15, 0.5, 0.85, 0.95), axis=1)
    return {
        "median": median,
        "sigma": (p85 - p15) / SIGMA_EFF_DENOMINATOR,
        "p15": p15,
        "p85": p85,
        "p95": p95,
        "mean": draws.mean(axis=1),
    }


def _position_cv(position: Any) -> float:
    from ceminidfs.models.simulate import DEFAULT_POSITION_CV, POSITION_CV

    token = str(position or "").strip().upper()
    if token == "DST":
        token = "DEF"
    return float(POSITION_CV.get(token, DEFAULT_POSITION_CV))


# --------------------------------------------------------------------------- #
# Builder.
# --------------------------------------------------------------------------- #
def read_canonical(root: str | Path) -> pd.DataFrame:
    """Read the newest ``canonical_projections_*.csv`` in a run directory."""

    directory = Path(root)
    candidates = sorted(directory.glob("canonical_projections_*.csv"))
    if not candidates:
        return pd.DataFrame()
    try:
        return pd.read_csv(candidates[-1])
    except (OSError, ValueError) as exc:
        raise HandoffInputError(f"cannot read canonical projections file {candidates[-1]}: {exc}") from exc


def _read_vegas(season: int | None, week: int | None) -> pd.DataFrame:
    if season is None or week is None:
        return pd.DataFrame()
    from ceminidfs.data.fetch import week_cache_dir

    path = week_cache_dir(int(season), int(week)) / "vegas.parquet"
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        raise HandoffInputError(f"cannot read vegas file {path}: {exc}") from exc


def _team_environment(vegas: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(implied_totals, spreads)`` keyed by team abbreviation."""

    totals: dict[str, str] = {}
    spreads: dict[str, str] = {}
    if vegas is None or vegas.empty:
        return totals, spreads
    for row in vegas.to_dict("records"):
        home = str(row.get("home_team") or "").upper()
        away = str(row.get("away_team") or "").upper()
        line = _first_number(row.get("total_line"), row.get("game_total"), row.get("total"))
        spread = _first_number(row.get("spread_line"), row.get("spread"))
        home_total = _first_number(row.get("home_implied_total"))
        away_total = _first_number(row.get("away_implied_total"))
        if line is not None and spread is not None:
            if home_total is None:
                home_total = round(line / 2.0 + spread / 2.0, 2)
            if away_total is None:
                away_total = round(line / 2.0 - spread / 2.0, 2)
        if home:
            if home_total is not None:
                totals[home] = _fmt(home_total)
            if spread is not None:
                spreads[home] = _fmt(spread)
        if away:
            if away_total is not None:
                totals[away] = _fmt(away_total)
            if spread is not None:
                spreads[away] = _fmt(-float(spread))
    return totals, spreads


def build_handoff_context(
    run_dir: str | Path,
    *,
    client: Any = None,
    config: Mapping[str, Any] | None = None,
    n_iterations: int = DEFAULT_HANDOFF_ITERATIONS,
    seed: int = DEFAULT_HANDOFF_SEED,
) -> HandoffContext | None:
    """Build the handoff context from a run directory.

    Returns ``None`` when no projection base is present, so the writer can fall
    back to the lineup-level summary. Every Jev answer is cached on disk by the
    client; without a client the router uses its documented priors (offline).
    """

    from ceminidfs.models.regime_gmm import (
        regime_weight_lookup,
        route_regimes,
    )
    from ceminidfs.models.synthetic_ownership import synthetic_ownership

    root = Path(run_dir)
    base_path = root / "player_projection_base.parquet"
    if not base_path.is_file():
        return None
    try:
        base = pd.read_parquet(base_path)
    except (OSError, ValueError) as exc:
        raise HandoffInputError(f"cannot read projection base {base_path}: {exc}") from exc
    if base.empty:
        return None

    canonical = read_canonical(root)
    season = _first_int(base.get("season")) if "season" in base.columns else None
    week = _first_int(base.get("week")) if "week" in base.columns else None
    vegas = _read_vegas(season, week)
    totals, spreads = _team_environment(vegas)

    universe = _merge_universe(base, canonical)

    rows: list[dict[str, Any]] = []
    for record in universe.to_dict("records"):
        rows.append(_handoff_row(record))

    routings = route_regimes(
        client,
        rows,
        id_key="player_id",
        implied_totals=totals,
    )
    weights = regime_weight_lookup(routings)

    owned = synthetic_ownership(rows, client=client)
    own_by_id = {str(row.get("player_id")): row for row in owned}

    gmm = _sample_stat_frame(
        rows,
        weights,
        n_iterations=n_iterations,
        seed=seed,
    )

    players: dict[str, PlayerHandoff] = {}
    slate_id = str(universe["slate_id"].iloc[0]) if "slate_id" in universe.columns and len(universe) else ""
    for index, record in enumerate(rows):
        player_id = str(record.get("player_id") or "")
        team = str(record.get("team") or "").upper()
        routing = routings.get(player_id)
        ownership_row = own_by_id.get(player_id, {})
        stat_values = {column: _fmt(gmm[column][index]) for column in STAT_COLUMNS if column in gmm}
        fpts_median = gmm.get("fpts_median", [None] * len(rows))[index]
        fpts_sigma = gmm.get("fpts_sigma", [None] * len(rows))[index]
        p95 = gmm.get("fpts_p95", [None] * len(rows))[index]
        own_value = _as_float(ownership_row.get("jev_proj_own"))
        handoff = PlayerHandoff(
            player_name=str(record.get("player_name") or ""),
            player_id=player_id,
            slate_id=str(record.get("slate_id") or slate_id),
            game_id=str(record.get("game_id") or ""),
            team=team,
            opp=str(record.get("opp") or "").upper(),
            position=str(record.get("position") or "").upper(),
            implied_total=totals.get(team, ""),
            spread=spreads.get(team, ""),
            fpts_median=_fmt(fpts_median),
            fpts_sigma=_fmt(fpts_sigma),
            jev_proj_own=_fmt(own_value),
            jev_regime_state=routing.top_state if routing is not None else "",
            jev_regime_conf=_fmt(routing.confidence) if routing is not None else "",
            jev_provider=routing.provider_used if routing is not None else "",
            stats=stat_values,
            p95_ceiling=_as_float(p95),
            fpts_median_value=_as_float(fpts_median),
            jev_proj_own_value=own_value,
        )
        if not handoff.player_name:
            continue
        players[normalize_handoff_name(handoff.player_name)] = handoff
        if player_id:
            players[player_id] = handoff

    return HandoffContext(players=players, slate_id=slate_id)


def _merge_universe(base: pd.DataFrame, canonical: pd.DataFrame) -> pd.DataFrame:
    """Join the base stats to the canonical slate rows on ``join_key``.

    The canonical frame is the slate universe (it carries salary, slate id, FD
    id). A canonical row without a base match keeps its identity but gets zero
    stat means. Without a canonical frame the base frame stands alone.
    """

    base_view = base.copy()
    base_view["join_key"] = base_view.get("join_key", "").astype(str)
    stat_columns = [column for column in BASE_STAT_COLUMNS if column in base_view.columns]
    base_index = base_view.drop_duplicates(subset=["join_key"], keep="first").set_index("join_key")

    records: list[dict[str, Any]] = []
    if canonical is None or canonical.empty:
        for row in base_view.to_dict("records"):
            record: dict[str, Any] = {
                "player_name": row.get("player_name", ""),
                "team": row.get("team", ""),
                "position": row.get("position", ""),
                "opp": row.get("opponent") or row.get("opp") or "",
                "game_id": row.get("game") or "",
                "player_id": row.get("player_id", ""),
                "slate_id": "",
                "injury_status": "",
                "salary": "",
                "fd_projection": row.get("fd_projection", 0.0),
                "join_key": row.get("join_key", ""),
            }
            for column in stat_columns:
                record[column] = row.get(column, 0.0)
            records.append(record)
        return pd.DataFrame(records)

    for row in canonical.to_dict("records"):
        name = row.get("player_name") or row.get("name") or ""
        team = row.get("team") or ""
        position = _canonical_position(row)
        key = _join_key(name, team, position)
        base_row = base_index.loc[key].to_dict() if key in base_index.index else {}
        projection = (
            row.get("fd_projection")
            or row.get("FPPG")
            or base_row.get("fd_projection")
            or 0.0
        )
        record = {
            "player_name": name,
            "team": team,
            "position": position,
            "opp": row.get("opp") or "",
            "game_id": row.get("game") or "",
            "player_id": row.get("fd_id") or row.get("player_key") or name,
            "slate_id": row.get("slate_id") or "",
            "injury_status": row.get("injury_status") or row.get("Injury Indicator") or "",
            "salary": row.get("fd_salary") or row.get("salary") or "",
            "fd_projection": projection,
            "join_key": key,
        }
        for column in stat_columns:
            record[column] = base_row.get(column, 0.0)
        records.append(record)
    return pd.DataFrame(records)


def _canonical_position(row: Mapping[str, Any]) -> str:
    value = row.get("fd_position") or row.get("position") or row.get("dk_position") or ""
    return str(value).upper()


def _join_key(name: Any, team: Any, position: Any) -> str:
    try:
        from ceminidfs.pipeline.engine import normalize_join_key

        return normalize_join_key(name, team, position)
    except Exception:  # pragma: no cover - defensive for partial installs.
        return "|".join(
            (
                " ".join(str(name or "").strip().lower().split()),
                str(team or "").strip().upper(),
                str(position or "").strip().upper(),
            )
        )


def _handoff_row(record: Mapping[str, Any]) -> dict[str, Any]:
    team = str(record.get("team") or "").upper()
    position = str(record.get("position") or "").upper()
    row = dict(record)
    row.update(
        {
            "team": team,
            "position": position,
            "opp": str(record.get("opp") or "").upper(),
            "report_status": str(record.get("injury_status") or ""),
            "injury_status": str(record.get("injury_status") or ""),
            "fd_projection": record.get("fd_projection") or 0.0,
            "projection": record.get("fd_projection") or 0.0,
            "fanduel_salary": record.get("salary") or "",
            "salary": record.get("salary") or "",
        }
    )
    return row


def _sample_stat_frame(
    rows: Sequence[Mapping[str, Any]],
    weights: Mapping[str, Sequence[float]],
    *,
    n_iterations: int,
    seed: int,
) -> dict[str, np.ndarray]:
    """Sample FanDuel points and each stat for every row.

    Returns a mapping of ``<column> -> ndarray`` aligned to ``rows``. Stat means
    come from the projection base; dispersion is a documented per-stat
    coefficient of variation. The regime mixture is shared across stats, so the
    injury/role tail shows up in every band.
    """

    n_players = len(rows)
    if n_players == 0:
        return {}

    from ceminidfs.models.regime_gmm import HEALTHY_PRIOR

    healthy = np.array(
        [
            HEALTHY_PRIOR["full_role"],
            HEALTHY_PRIOR["snap_count_decoy"],
            HEALTHY_PRIOR["in_game_reaggravation_exit"],
        ],
        dtype=float,
    )
    weight_matrix = np.tile(healthy, (n_players, 1))
    for index, row in enumerate(rows):
        player_id = str(row.get("player_id") or "")
        entry = weights.get(player_id)
        if entry is not None:
            weight_matrix[index] = np.asarray(list(entry)[:3], dtype=float)
    totals = weight_matrix.sum(axis=1, keepdims=True)
    weight_matrix = weight_matrix / np.where(totals > 0.0, totals, 1.0)

    out: dict[str, np.ndarray] = {}
    fpts_median = np.zeros(n_players, dtype=float)
    for index, row in enumerate(rows):
        projections = _float_or_zero(row.get("fd_projection"))
        fpts_median[index] = max(projections, 0.0)
    fpts_sigma = np.array(
        [_position_cv(row.get("position")) * fpts_median[index] for index, row in enumerate(rows)],
        dtype=float,
    )
    fpts_bands = _gmm_bands(
        fpts_median, fpts_sigma, weight_matrix, n_iterations=n_iterations, seed=seed
    )
    out["fpts_median"] = fpts_bands["median"]
    out["fpts_sigma"] = fpts_bands["sigma"]
    out["fpts_p95"] = fpts_bands["p95"]

    for spec in STAT_SPECS:
        values = np.array(
            [
                sum(_float_or_zero(row.get(column)) for column in spec.sources)
                for row in rows
            ],
            dtype=float,
        )
        values = np.maximum(values, 0.0)
        bands = _gmm_bands(
            values,
            spec.cv * values,
            weight_matrix,
            n_iterations=n_iterations,
            seed=seed,
        )
        for field_name in spec.fields:
            out[f"{spec.name}_{field_name}"] = bands[field_name]
    return out


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _as_float(value)
        if parsed is not None:
            return parsed
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _float_or_zero(value: Any) -> float:
    parsed = _as_float(value)
    return parsed if parsed is not None else 0.0


def _first_int(series: Any) -> int | None:
    if series is None:
        return None
    for value in list(series):
        parsed = _as_float(value)
        if parsed is not None:
            return int(parsed)
    return None


def _fmt(value: Any) -> str:
    parsed = _as_float(value)
    if parsed is None:
        return ""
    return f"{parsed:.4f}"

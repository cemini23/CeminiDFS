import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs import cli
from ceminidfs.pipeline import market_benchmark


def test_parse_closing_props_ignores_other_columns(tmp_path: Path):
    path = tmp_path / "props.csv"
    path.write_text(
        "player_key,stat_type,line,side,platform\n"
        "p1|kc|qb,pass_yds,268.5,over,prizepicks\n"
        "p1|kc|qb,pass_yds,268.5,under,prizepicks\n",
        encoding="utf-8",
    )

    frame = market_benchmark.parse_closing_props(path)

    assert list(frame.columns) == ["player_key", "stat_type", "line"]
    assert len(frame) == 2


def test_parse_closing_props_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        market_benchmark.parse_closing_props(tmp_path / "missing.csv")


def test_parse_closing_props_empty_raises(tmp_path: Path):
    header_only = tmp_path / "header_only.csv"
    header_only.write_text("player_key,stat_type,line\n", encoding="utf-8")
    with pytest.raises(ValueError):
        market_benchmark.parse_closing_props(header_only)

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        market_benchmark.parse_closing_props(empty)


def test_parse_closing_props_missing_column_raises(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("player_key,line\np1|kc|qb,268.5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        market_benchmark.parse_closing_props(path)


def test_model_beats_market(tmp_path: Path):
    props = _write_props(tmp_path, n=40, line=320.0)
    result = market_benchmark.run_market_benchmark(
        2026,
        5,
        props,
        distributions=_distributions(n=40, median=250.0),
        actuals=_actuals(n=40, actual=250.0),
    )

    assert result.n_legs == 40
    assert result.verdict == market_benchmark.VERDICT_MODEL
    assert result.model_mae_fd < result.market_mae_fd
    assert result.by_stat[0].better == "model"


def test_market_beats_model(tmp_path: Path):
    props = _write_props(tmp_path, n=40, line=250.0)
    result = market_benchmark.run_market_benchmark(
        2026,
        5,
        props,
        distributions=_distributions(n=40, median=320.0),
        actuals=_actuals(n=40, actual=250.0),
    )

    assert result.n_legs == 40
    assert result.verdict == market_benchmark.VERDICT_MARKET
    assert result.market_mae_fd < result.model_mae_fd
    assert result.by_stat[0].better == "market"


def test_under_thirty_legs_is_no_coverage(tmp_path: Path):
    props = _write_props(tmp_path, n=10, line=250.0)
    result = market_benchmark.run_market_benchmark(
        2026,
        5,
        props,
        distributions=_distributions(n=10, median=250.0),
        actuals=_actuals(n=10, actual=250.0),
    )

    assert result.n_legs == 10
    assert result.verdict == market_benchmark.VERDICT_NO_COVERAGE
    rendered = market_benchmark.format_market_benchmark(result)
    assert "VERDICT: NO COVERAGE" in rendered


def test_no_joined_legs_is_no_coverage(tmp_path: Path):
    props = _write_props(tmp_path, n=40, line=250.0)
    result = market_benchmark.run_market_benchmark(
        2026,
        5,
        props,
        distributions=_distributions(n=40, median=250.0, player_key_prefix="other"),
        actuals=_actuals(n=40, actual=250.0),
    )

    assert result.n_legs == 0
    assert result.verdict == market_benchmark.VERDICT_NO_COVERAGE


def test_cli_missing_file_exits_non_zero(tmp_path: Path):
    exit_code = cli.main(
        [
            "market-benchmark",
            "--season",
            "2026",
            "--week",
            "5",
            "--closing-props",
            str(tmp_path / "missing.csv"),
        ]
    )

    assert exit_code == 1


def test_cli_empty_file_exits_non_zero(tmp_path: Path):
    path = tmp_path / "props.csv"
    path.write_text("player_key,stat_type,line\n", encoding="utf-8")

    exit_code = cli.main(
        [
            "market-benchmark",
            "--season",
            "2026",
            "--week",
            "5",
            "--closing-props",
            str(path),
        ]
    )

    assert exit_code == 1


def _write_props(tmp_path: Path, *, n: int, line: float) -> Path:
    path = tmp_path / "props.csv"
    body = "\n".join(f"p{i}|kc|qb,pass_yds,{line},over,prizepicks" for i in range(n))
    path.write_text("player_key,stat_type,line,side,platform\n" + body + "\n", encoding="utf-8")
    return path


def _distributions(
    *,
    n: int,
    median: float,
    player_key_prefix: str = "p",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_name": f"P{i}",
                "player_key": f"{player_key_prefix}{i}|kc|qb",
                "player_id": f"id{i}",
                "team": "KC",
                "stat_type": "pass_yds",
                "median": float(median),
                "sd": 40.0,
                "family": "lognormal",
            }
            for i in range(n)
        ]
    )


def _actuals(*, n: int, actual: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": f"id{i}", "pass_yds": float(actual), "rush_yds": 0.0, "rec_yds": 0.0}
            for i in range(n)
        ]
    )

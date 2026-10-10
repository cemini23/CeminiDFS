"""Research export: environment, injury status, and the parlays handoff."""

import csv
import json
from pathlib import Path

import pandas as pd

from ceminidfs.cli import _review_report_overrides, build_parser, main
from ceminidfs.export.optimize import LINEUP_HEADERS
from ceminidfs.export.research_export import (
    ENV_COLUMNS,
    validate_environment,
    write_environment_csv,
    write_status_csvs,
)
from ceminidfs.export.review_reports import (
    PARLAYS_HANDOFF_HEADER,
    load_player_index,
    write_parlays_handoff,
)

GAMES = [
    ("BUF", "KC"),
    ("GB", "DET"),
    ("SF", "LAC"),
    ("NYJ", "NYG"),
    ("DAL", "PHI"),
    ("MIA", "NE"),
    ("CIN", "BAL"),
    ("HOU", "JAX"),
    ("CHI", "MIN"),
    ("TB", "NO"),
    ("SEA", "ARI"),
    ("PIT", "CLE"),
]
HOURLY_URL = "https://api.weather.gov/gridpoints/TEST/1/1/forecast/hourly"
KICKOFF = "10/04/2026 01:00PM ET"


def _salary(path: Path, games: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Id", "Nickname", "Position", "Team", "Opponent", "Salary", "FPPG", "Game"],
        )
        writer.writeheader()
        index = 1
        for away, home in games:
            game = f"{away}@{home} {KICKOFF}"
            for team, opp in ((away, home), (home, away)):
                writer.writerow(
                    {
                        "Id": str(index),
                        "Nickname": f"Player {index}",
                        "Position": "WR",
                        "Team": team,
                        "Opponent": opp,
                        "Salary": "5000",
                        "FPPG": "10",
                        "Game": game,
                    }
                )
                index += 1
    return path


def _vegas() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "home_team": "KC",
                "away_team": "BUF",
                "spread_line": 3,
                "total_line": 47,
            }
        ]
    )


def _opener(calls: list[str]):
    def opener(url: str) -> bytes:
        calls.append(url)
        if "/points/" in url:
            body = {"properties": {"forecastHourly": HOURLY_URL}}
        else:
            body = {
                "properties": {
                    "periods": [
                        {
                            "startTime": "2026-10-04T13:00:00-04:00",
                            "endTime": "2026-10-04T14:00:00-04:00",
                            "windSpeed": "12 mph",
                            "probabilityOfPrecipitation": {"value": 40},
                        }
                    ]
                }
            }
        return json.dumps(body).encode()

    return opener


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_environment_has_one_row_per_slate_team_and_skips_indoor_weather(tmp_path: Path):
    salary = _salary(tmp_path / "salary.csv", GAMES)
    calls: list[str] = []
    out = write_environment_csv(
        salary,
        tmp_path / "environment.csv",
        season=2026,
        week=4,
        vegas_frame=_vegas(),
        opener=_opener(calls),
        retrieved_at="2026-10-04T12:00:00-04:00",
    )

    rows = _rows(out)
    assert len(rows) == 24
    assert list(rows[0]) == ENV_COLUMNS
    by_team = {row["team"]: row for row in rows}
    assert set(by_team) == {team for pair in GAMES for team in pair}
    kc = by_team["KC"]
    assert kc["game_id"] == "BUF@KC"
    assert kc["opp"] == "BUF"
    assert kc["implied_total"] == "25"
    assert kc["spread"] == "-3"
    assert kc["roof"] == "open"
    assert kc["weather_exposed"] == "true"
    assert kc["wind_mph"] == "12"
    assert kc["precip_pop"] == "40"
    assert kc["wind_source_url"] == HOURLY_URL
    assert kc["wind_retrieved_at"] == "2026-10-04T12:00:00-04:00"
    assert kc["precip_source_url"] == HOURLY_URL
    buf = by_team["BUF"]
    assert buf["implied_total"] == "22"
    assert buf["spread"] == "3"
    assert buf["wind_mph"] == "12"
    det = by_team["DET"]
    assert det["roof"] == "dome"
    assert det["weather_exposed"] == "false"
    assert det["wind_mph"] == ""
    assert det["precip_pop"] == ""
    assert det["implied_total"] == ""
    assert det["spread"] == ""
    lac = by_team["LAC"]
    assert lac["roof"] == "semi_open"
    assert lac["wind_mph"] == ""
    assert lac["precip_pop"] == ""
    assert "0" not in {det["wind_mph"], det["precip_pop"], lac["wind_mph"], lac["precip_pop"]}
    assert calls
    assert all("api.weather.gov" in url for url in calls)


def test_one_game_slate_is_two_rows_and_dome_does_not_call_nws(tmp_path: Path):
    salary = _salary(tmp_path / "salary.csv", [("GB", "DET")])
    calls: list[str] = []
    out = write_environment_csv(
        salary,
        tmp_path / "environment.csv",
        season=2026,
        week=4,
        vegas_frame=None,
        opener=_opener(calls),
        retrieved_at="2026-10-04T12:00:00-04:00",
    )
    rows = _rows(out)
    assert len(rows) == 2
    assert calls == []
    assert {row["team"] for row in rows} == {"GB", "DET"}


def test_status_maps_tokens_and_does_not_invent_one(tmp_path: Path):
    injuries = tmp_path / "injuries.parquet"
    pd.DataFrame(
        [
            {
                "week": 4,
                "full_name": "Out Back",
                "team": "KC",
                "report_status": "Out",
                "practice_status": "",
            },
            {
                "week": 4,
                "full_name": "Q Tee",
                "team": "BUF",
                "report_status": "Questionable",
                "practice_status": "Limited Participation in Practice",
            },
            {
                "week": 4,
                "full_name": "Prob Able",
                "team": "CIN",
                "report_status": "Probable",
                "practice_status": "",
            },
            {
                "week": 4,
                "full_name": "Dee Np",
                "team": "DET",
                "report_status": "",
                "practice_status": "Did Not Participate In Practice",
            },
            {
                "week": 3,
                "full_name": "Old Week",
                "team": "KC",
                "report_status": "Out",
                "practice_status": "",
            },
        ]
    ).to_parquet(injuries, index=False)

    dfs_path, parlay_path = write_status_csvs(
        injuries,
        tmp_path / "out",
        week=4,
        retrieved_at="2026-10-04T12:00:00-04:00",
    )
    dfs = {row["name"]: row for row in _rows(dfs_path)}
    parlays = {row["name"]: row for row in _rows(parlay_path)}
    assert "Old Week" not in dfs
    assert dfs["Out Back"]["exclude"] == "true"
    assert dfs["Out Back"]["lock"] == "false"
    assert dfs["Out Back"]["status"] == "out"
    assert dfs["Q Tee"]["status"] == "questionable"
    assert dfs["Q Tee"]["exclude"] == "false"
    assert dfs["Q Tee"]["lock"] == "false"
    assert dfs["Prob Able"]["status"] == "Probable"
    assert dfs["Prob Able"]["exclude"] == "false"
    assert dfs["Dee Np"]["status"] == "dnp"
    assert dfs["Dee Np"]["exclude"] == "false"
    for row in dfs.values():
        assert row["source"] == str(injuries)
        assert row["retrieved"] == "2026-10-04T12:00:00-04:00"
        assert row["lock"] == "false"
    for row in parlays.values():
        assert row["source"]
        assert row["retrieved"]
        assert "exclude" not in row


def test_validate_rejects_bad_team_game_citation_and_salary(tmp_path: Path):
    good = tmp_path / "good.csv"
    with good.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENV_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "slate_id": "2026_w4",
                "game_id": "BUF@KC",
                "team": "KC",
                "opp": "BUF",
                "implied_total": "25",
                "spread": "-3",
                "roof": "open",
                "weather_exposed": "true",
                "wind_mph": "12",
                "precip_pop": "40",
                "wind_source_url": HOURLY_URL,
                "wind_retrieved_at": "2026-10-04T12:00:00-04:00",
                "precip_source_url": HOURLY_URL,
                "precip_retrieved_at": "2026-10-04T12:00:00-04:00",
            }
        )
    assert validate_environment(good) == []

    bad = tmp_path / "bad.csv"
    with bad.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENV_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "slate_id": "2026_w4",
                "game_id": "XYZ@KC",
                "team": "XYZ",
                "opp": "KC",
                "implied_total": "",
                "spread": "",
                "roof": "",
                "weather_exposed": "false",
                "wind_mph": "9",
                "precip_pop": "",
                "wind_source_url": "",
                "wind_retrieved_at": "",
                "precip_source_url": "",
                "precip_retrieved_at": "",
            }
        )
        writer.writerow(
            {
                "slate_id": "2026_w4",
                "game_id": "KC@DET",
                "team": "KC",
                "opp": "BUF",
                "implied_total": "",
                "spread": "",
                "roof": "open",
                "weather_exposed": "true",
                "wind_mph": "",
                "precip_pop": "",
                "wind_source_url": "",
                "wind_retrieved_at": "",
                "precip_source_url": "",
                "precip_retrieved_at": "",
            }
        )
    errors = validate_environment(bad)
    assert any("unknown team code" in error for error in errors)
    assert any("game_id KC@DET" in error for error in errors)
    assert any("wind_mph is filled" in error for error in errors)

    salary = _salary(tmp_path / "salary.csv", [("BUF", "KC")])
    extra = tmp_path / "extra.csv"
    with extra.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENV_COLUMNS)
        writer.writeheader()
        for team, opp, game_id in (
            ("DAL", "PHI", "DAL@PHI"),
            ("PHI", "DAL", "DAL@PHI"),
        ):
            writer.writerow(
                {
                    "slate_id": "2026_w4",
                    "game_id": game_id,
                    "team": team,
                    "opp": opp,
                    "implied_total": "",
                    "spread": "",
                    "roof": "open",
                    "weather_exposed": "true",
                    "wind_mph": "",
                    "precip_pop": "",
                    "wind_source_url": "",
                    "wind_retrieved_at": "",
                    "precip_source_url": "",
                    "precip_retrieved_at": "",
                }
            )
    salary_errors = validate_environment(extra, salary_path=salary, season=2026, week=4)
    assert any("not on the salary file" in error for error in salary_errors)

    code = main(["research-export", "validate", "--slate", str(bad)])
    assert code == 1
    assert main(["research-export", "validate", "--slate", str(good)]) == 0


def _env_row(
    team: str,
    opp: str,
    game_id: str,
    *,
    exposed: bool,
    wind_mph: str = "",
    precip_pop: str = "",
) -> dict[str, str]:
    return {
        "slate_id": "2026_w4",
        "game_id": game_id,
        "team": team,
        "opp": opp,
        "implied_total": "",
        "spread": "",
        "roof": "open" if exposed else "dome",
        "weather_exposed": "true" if exposed else "false",
        "wind_mph": wind_mph,
        "precip_pop": precip_pop,
        "wind_source_url": "",
        "wind_retrieved_at": "",
        "precip_source_url": "",
        "precip_retrieved_at": "",
    }


def _write_env(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_validate_requires_salary_teams_and_rejects_blank_exposed_weather(tmp_path: Path):
    salary = _salary(tmp_path / "salary.csv", [("BUF", "KC")])
    partial = tmp_path / "partial.csv"
    _write_env(partial, [_env_row("KC", "BUF", "BUF@KC", exposed=False)])
    missing = validate_environment(partial, salary_path=salary, season=2026, week=4)
    assert any(error == "salary team BUF has no environment row" for error in missing)
    assert not any("wind_mph is blank" in error or "precip_pop is blank" in error for error in missing)

    exposed = tmp_path / "exposed.csv"
    _write_env(exposed, [_env_row("KC", "BUF", "BUF@KC", exposed=True)])
    blank = validate_environment(exposed)
    assert any("wind_mph is blank" in error for error in blank)
    assert any("precip_pop is blank" in error for error in blank)

    indoor = tmp_path / "indoor.csv"
    _write_env(indoor, [_env_row("DET", "GB", "GB@DET", exposed=False)])
    indoor_errors = validate_environment(indoor)
    assert indoor_errors == []


def test_research_export_commands_parse():
    parser = build_parser()
    env_args = parser.parse_args(
        [
            "research-export",
            "env",
            "--salary",
            "salary.csv",
            "--season",
            "2026",
            "--week",
            "4",
            "--out",
            "environment.csv",
        ]
    )
    assert env_args.research_command == "env"
    status_args = parser.parse_args(
        ["research-export", "status", "--season", "2026", "--week", "4", "--out", "out"]
    )
    assert status_args.research_command == "status"


def test_handoff_prefers_fd_projection_and_environment_total(tmp_path: Path):
    players = tmp_path / "players.csv"
    fieldnames = [
        "Id",
        "First Name",
        "Last Name",
        "Position",
        "Team",
        "Salary",
        "FPPG",
        "fd_projection",
        "Game",
        "Injury Indicator",
    ]
    with players.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "Id": "1",
                "First Name": "Brock",
                "Last Name": "Bowers",
                "Position": "TE",
                "Team": "KC",
                "Salary": "7000",
                "FPPG": "25.60",
                "fd_projection": "7.08",
                "Game": "BUF@KC 01:00PM ET",
                "Injury Indicator": "Q",
            }
        )
        writer.writerow(
            {
                "Id": "2",
                "First Name": "Kansas City",
                "Last Name": "Chiefs",
                "Position": "D",
                "Team": "KC",
                "Salary": "4000",
                "FPPG": "8",
                "fd_projection": "6",
                "Game": "BUF@KC 01:00PM ET",
                "Injury Indicator": "",
            }
        )
        writer.writerow(
            {
                "Id": "3",
                "First Name": "Josh",
                "Last Name": "Allen",
                "Position": "QB",
                "Team": "BUF",
                "Salary": "8000",
                "FPPG": "23",
                "fd_projection": "19.5",
                "Game": "BUF@KC 01:00PM ET",
                "Injury Indicator": "",
            }
        )
    environment = tmp_path / "environment.csv"
    with environment.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["team", "implied_total"])
        writer.writeheader()
        writer.writerow({"team": "KC", "implied_total": "25"})
    lineups = tmp_path / "lineups.csv"
    with lineups.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(LINEUP_HEADERS["fanduel"])
        writer.writerow(
            [
                "Josh Allen",
                "Brock Bowers",
                "Brock Bowers",
                "Brock Bowers",
                "Brock Bowers",
                "Brock Bowers",
                "Brock Bowers",
                "Brock Bowers",
                "Kansas City Chiefs",
            ]
        )

    from ceminidfs.export.review_reports import maybe_write_review_reports

    maybe_write_review_reports(lineups, players, environment=environment)
    header, body = _read(tmp_path / "ceminidfs_handoff.csv")
    assert header == PARLAYS_HANDOFF_HEADER
    by_name = {row[0]: row for row in body}
    assert "Kansas City Chiefs" not in by_name
    bowers = by_name["Brock Bowers"]
    assert bowers[2] == "7.08"
    assert bowers[5] == "25"
    assert bowers[6] == "Q"
    allen = by_name["Josh Allen"]
    assert allen[2] == "19.5"
    assert allen[5] == ""

    bare = load_player_index(players)
    direct = write_parlays_handoff(
        tmp_path / "direct.csv",
        [[("QB", "Josh Allen"), ("TE", "Brock Bowers"), ("DEF", "Kansas City Chiefs")]],
        bare,
    )
    _, direct_rows = _read(direct)
    assert all(row[0] != "Kansas City Chiefs" for row in direct_rows)
    assert direct_rows


def test_environment_flag_is_on_run_optimize_and_review():
    parser = build_parser()
    review = parser.parse_args(
        ["review", "--lineups", "l.csv", "--players", "p.csv", "--environment", "env.csv"]
    )
    run = parser.parse_args(
        [
            "run",
            "--season",
            "2026",
            "--week",
            "4",
            "--salary",
            "s.csv",
            "--environment",
            "env.csv",
        ]
    )
    optimize = parser.parse_args(
        ["optimize", "--csv", "p.csv", "--out", "o.csv", "--environment", "env.csv"]
    )
    assert _review_report_overrides(review)["environment"].endswith("env.csv")
    assert _review_report_overrides(run)["environment"].endswith("env.csv")
    assert _review_report_overrides(optimize)["environment"].endswith("env.csv")


def _read(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]

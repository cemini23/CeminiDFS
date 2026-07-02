"""Pipeline resilience tests for Workstream C (fixes #7, #9)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from urllib.error import URLError

import pandas as pd
import pytest

from ceminidfs.data.availability import resolve_unavailable_player_ids
from ceminidfs.pipeline.engine import salary_rows_to_roster
from ceminidfs.pipeline.project import _apply_optional_overlay


class TestApplyOptionalOverlay:
    """C4: Buzz/ESPN graceful degrade on network failures."""

    def test_overlay_degrade_on_network_error(self) -> None:
        """URLError should be caught and rows returned unchanged."""
        rows = [{"name": "Test", "fd_projection": "15.5"}]

        def fn_raising(*args: Any, **kwargs: Any) -> Any:
            raise URLError("offline")

        result = _apply_optional_overlay(rows, fn_raising, "buzz", {})
        assert result == rows

    def test_overlay_degrade_on_runtime_error(self) -> None:
        """RuntimeError (e.g., espn_api not installed) should be caught."""
        rows = [{"name": "Test", "fd_projection": "15.5"}]

        def fn_raising(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("espn_api not installed")

        result = _apply_optional_overlay(rows, fn_raising, "ESPN injury", {})
        assert result == rows

    def test_overlay_degrade_on_value_error(self) -> None:
        """ValueError (e.g., malformed API payload) should be caught."""
        rows = [{"name": "Test", "fd_projection": "15.5"}]

        def fn_raising(*args: Any, **kwargs: Any) -> Any:
            raise ValueError("malformed JSON")

        result = _apply_optional_overlay(rows, fn_raising, "buzz signal", {})
        assert result == rows

    def test_overlay_passthrough_on_success(self) -> None:
        """Successful overlay should modify rows normally."""
        rows = [{"name": "Test", "fd_projection": "15.5"}]

        def fn_appending(rows: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
            for row in rows:
                row["buzz_signal"] = "BUY"
            return rows

        result = _apply_optional_overlay(rows, fn_appending, "buzz", {})
        assert result[0]["buzz_signal"] == "BUY"

    def test_overlay_warning_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Warning should be printed to stderr on failure."""
        rows = [{"name": "Test"}]

        def fn_raising(*args: Any, **kwargs: Any) -> Any:
            raise URLError("connection refused")

        _apply_optional_overlay(rows, fn_raising, "buzz signal", {})
        captured = capsys.readouterr()
        assert "WARNING: buzz signal overlay failed" in captured.err
        assert "connection refused" in captured.err


class TestSalaryRowsToRoster:
    """C5: Keep injury_status in roster frame."""

    def test_roster_keeps_injury_status(self) -> None:
        """salary_rows_to_roster should include injury_status column."""
        rows = [
            {
                "name": "Patrick Mahomes",
                "player_name": "Patrick Mahomes",
                "team": "KC",
                "fd_position": "QB",
                "injury_status": "O",
            }
        ]
        roster = salary_rows_to_roster(rows)
        assert "injury_status" in roster.columns
        assert roster.iloc[0]["injury_status"] == "O"

    def test_roster_empty_injury_status(self) -> None:
        """Empty injury_status should be empty string."""
        rows = [
            {
                "name": "Patrick Mahomes",
                "player_name": "Patrick Mahomes",
                "team": "KC",
                "fd_position": "QB",
            }
        ]
        roster = salary_rows_to_roster(rows)
        assert roster.iloc[0]["injury_status"] == ""

    def test_roster_from_injury_indicator(self) -> None:
        """Should also read from Injury Indicator key."""
        rows = [
            {
                "name": "Player A",
                "player_name": "Player A",
                "team": "DAL",
                "fd_position": "RB",
                "Injury Indicator": "Q",
            }
        ]
        roster = salary_rows_to_roster(rows)
        assert roster.iloc[0]["injury_status"] == "Q"


class TestUnavailableIdsFromRoster:
    """C5: resolve_unavailable_player_ids uses roster injury_status."""

    def test_unavailable_ids_from_roster_injury_out(self, tmp_path: pytest.TempPathFactory) -> None:
        """Player with injury_status='O' should be in excluded set."""
        roster = pd.DataFrame(
            [
                {
                    "player_id": "mahomes-patrick",
                    "player_name": "Patrick Mahomes",
                    "team": "KC",
                    "position": "QB",
                    "injury_status": "O",
                }
            ]
        )

        # Empty week cache to ensure roster is the only source
        with patch("ceminidfs.data.availability.week_cache_dir") as mock_cache:
            mock_cache.return_value = tmp_path

            excluded = resolve_unavailable_player_ids(2026, 1, roster=roster)
            assert "mahomes-patrick" in excluded

    def test_unavailable_ids_not_marked_for_questionable(self, tmp_path: pytest.TempPathFactory) -> None:
        """Player with injury_status='Q' should NOT be in excluded set."""
        roster = pd.DataFrame(
            [
                {
                    "player_id": "player-q",
                    "player_name": "Questionable Player",
                    "team": "DAL",
                    "position": "RB",
                    "injury_status": "Q",
                }
            ]
        )

        with patch("ceminidfs.data.availability.week_cache_dir") as mock_cache:
            mock_cache.return_value = tmp_path

            excluded = resolve_unavailable_player_ids(2026, 1, roster=roster)
            assert "player-q" not in excluded

    def test_unavailable_ids_doubtful_included(self, tmp_path: pytest.TempPathFactory) -> None:
        """Player with injury_status='D' should be in excluded set."""
        roster = pd.DataFrame(
            [
                {
                    "player_id": "player-d",
                    "player_name": "Doubtful Player",
                    "team": "NYG",
                    "position": "WR",
                    "injury_status": "D",
                }
            ]
        )

        with patch("ceminidfs.data.availability.week_cache_dir") as mock_cache:
            mock_cache.return_value = tmp_path

            excluded = resolve_unavailable_player_ids(2026, 1, roster=roster)
            assert "player-d" in excluded

    def test_unavailable_ids_empty_roster_no_error(self, tmp_path: pytest.TempPathFactory) -> None:
        """Empty roster should not cause error."""
        empty_roster = pd.DataFrame()

        with patch("ceminidfs.data.availability.week_cache_dir") as mock_cache:
            mock_cache.return_value = tmp_path

            excluded = resolve_unavailable_player_ids(2026, 1, roster=empty_roster)
            assert excluded == set()

    def test_unavailable_ids_no_injury_column(self, tmp_path: pytest.TempPathFactory) -> None:
        """Roster without injury_status column should not error."""
        roster_no_injury = pd.DataFrame(
            [
                {
                    "player_id": "player1",
                    "player_name": "Healthy Player",
                    "team": "SF",
                    "position": "TE",
                }
            ]
        )

        with patch("ceminidfs.data.availability.week_cache_dir") as mock_cache:
            mock_cache.return_value = tmp_path

            excluded = resolve_unavailable_player_ids(2026, 1, roster=roster_no_injury)
            assert excluded == set()

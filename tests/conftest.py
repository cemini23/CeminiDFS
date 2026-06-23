"""Shared pytest hooks — keep CI offline unless a test opts into network I/O."""

from __future__ import annotations

import pytest


def _weather_cache_only(season: int, week: int, config=None):
    """Return cached week weather only; never call Open-Meteo in the test suite."""

    from ceminidfs.pipeline.backtest import load_week_artifacts

    _, _, weather = load_week_artifacts(season, week)
    if weather is not None and not weather.empty:
        return weather
    return None


@pytest.fixture(autouse=True)
def disable_open_meteo_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backtest/calibration paths must not hit Open-Meteo when weather cache is absent."""

    for module in (
        "ceminidfs.pipeline.backtest",
        "ceminidfs.pipeline.calibration",
        "ceminidfs.pipeline.coherence_eval",
        "ceminidfs.pipeline.lineup_backtest",
    ):
        monkeypatch.setattr(f"{module}.resolve_weather_for_week", _weather_cache_only)

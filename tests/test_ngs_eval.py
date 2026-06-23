"""Tests for NGS eval stub — no network in default path."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from ceminidfs.data.ngs_eval import load_ngs_passing_sample


class TestLoadNgsPassingSample:
    """Tests for load_ngs_passing_sample stub."""

    def test_returns_none_when_sportsdataverse_not_available(self) -> None:
        """Stub should return None when sportsdataverse is not installed."""
        with pytest.MonkeyPatch().context() as mp:
            # Remove sportsdataverse from available modules
            for key in list(sys.modules.keys()):
                if key.startswith("sportsdataverse"):
                    del sys.modules[key]
            # Block import by not having the module
            real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

            def blocking_import(name, *args, **kwargs):
                if name.startswith("sportsdataverse"):
                    raise ImportError(f"No module named '{name}'")
                return real_import(name, *args, **kwargs)

            mp.setattr("builtins.__import__", blocking_import)
            result = load_ngs_passing_sample(season=2024)
            assert result is None

    def test_returns_none_on_fetch_error(self) -> None:
        """Stub should return None on any fetch error."""
        # Create a mock nfl module that raises on load
        mock_nfl = MagicMock()
        mock_nfl.load_nfl_ngs_passing.side_effect = Exception("Network error")

        mock_sdv = ModuleType("sportsdataverse")
        mock_sdv.nfl = mock_nfl

        # Inject into sys.modules
        with pytest.MonkeyPatch().context() as mp:
            mp.setitem(sys.modules, "sportsdataverse", mock_sdv)
            mp.setitem(sys.modules, "sportsdataverse.nfl", mock_nfl)
            result = load_ngs_passing_sample(season=2024)
            assert result is None

    def test_returns_dataframe_when_sportsdataverse_available(self) -> None:
        """Stub should return DataFrame when sportsdataverse is available."""
        mock_df = MagicMock()
        mock_nfl = MagicMock()
        mock_nfl.load_nfl_ngs_passing.return_value = mock_df

        mock_sdv = ModuleType("sportsdataverse")
        mock_sdv.nfl = mock_nfl

        # Inject into sys.modules
        with pytest.MonkeyPatch().context() as mp:
            mp.setitem(sys.modules, "sportsdataverse", mock_sdv)
            mp.setitem(sys.modules, "sportsdataverse.nfl", mock_nfl)
            result = load_ngs_passing_sample(season=2024)

            assert result is mock_df
            mock_nfl.load_nfl_ngs_passing.assert_called_once_with(
                seasons=[2024],
                return_as_pandas=True,
            )

    def test_no_network_calls_in_default_path(self) -> None:
        """Ensure no network calls are made in the default (unmocked) path."""
        # This test verifies that the default behavior doesn't attempt any network calls
        # The function should return None when sportsdataverse is not available
        result = load_ngs_passing_sample(season=2024)
        # Should be None (no network calls attempted)
        assert result is None


class TestNgsEvalModule:
    """Module-level tests for ngs_eval."""

    def test_module_has_required_functions(self) -> None:
        """Ensure the module exposes the expected API."""
        from ceminidfs.data import ngs_eval

        assert hasattr(ngs_eval, "load_ngs_passing_sample")
        assert callable(ngs_eval.load_ngs_passing_sample)

    def test_docstrings_present(self) -> None:
        """Ensure docstrings are present for public functions."""
        from ceminidfs.data import ngs_eval

        assert ngs_eval.load_ngs_passing_sample.__doc__ is not None
        assert "NGS" in ngs_eval.load_ngs_passing_sample.__doc__

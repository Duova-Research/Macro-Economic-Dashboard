"""
tests/test_pipeline.py
───────────────────────
Unit + integration tests for the agent pipeline.

Run with: python -m pytest tests/ -v

These tests use mock data so they do NOT require a real FRED API key
or Anthropic API key. They verify:
  1. Each agent reads/writes the correct state keys
  2. SignalAgent correctly maps risk_level → signal color
  3. The full pipeline completes without crashing on good data
  4. The pipeline handles missing data gracefully (no crashes)
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.state import make_initial_state

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_mock_raw_data() -> dict:
    """Minimal FRED-style observations for testing."""
    obs = [{"date": f"2024-0{i}-01", "value": float(300 + i)} for i in range(1, 4)]
    return {
        "CPIAUCSL": {
            "series_id": "CPIAUCSL",
            "name": "CPI (All Urban Consumers)",
            "unit": "Index 1982-84=100",
            "frequency": "Monthly",
            "observations": obs,
            "latest_date": "2024-03-01",
            "latest_value": 302.0,
            "count": 3,
        },
        "UNRATE": {
            "series_id": "UNRATE",
            "name": "Unemployment Rate",
            "unit": "Percent",
            "frequency": "Monthly",
            "observations": obs,
            "latest_date": "2024-03-01",
            "latest_value": 3.9,
            "count": 3,
        },
    }


def _make_mock_analysis() -> dict:
    """Minimal analysis output matching AnalyzeAgent's contract."""
    return {
        "CPIAUCSL": {
            "series_id": "CPIAUCSL",
            "yoy_change": 3.5,
            "mom_change": 0.3,
            "trend": "decelerating",
            "context": "Inflation is above the Fed target but trending lower.",
            "risk_level": "moderate",
        },
        "UNRATE": {
            "series_id": "UNRATE",
            "yoy_change": -0.2,
            "mom_change": 0.1,
            "trend": "stable",
            "context": "The labor market remains tight near historical lows.",
            "risk_level": "low",
        },
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_make_initial_state():
    """State dict should have all required keys after initialization."""
    state = make_initial_state("test-run-001")
    assert state["run_id"] == "test-run-001"
    assert state["raw_data"] == {}
    assert state["analysis"] == {}
    assert state["signals"] == []
    assert state["report"] == ""
    assert state["errors"] == []
    print("✓ test_make_initial_state")


def test_signal_agent_risk_mapping():
    """
    SignalAgent should correctly map risk_level → signal color
    without calling any external API.
    """
    from agents.signal_agent import RISK_TO_SIGNAL

    assert RISK_TO_SIGNAL["low"]      == "green"
    assert RISK_TO_SIGNAL["moderate"] == "yellow"
    assert RISK_TO_SIGNAL["elevated"] == "yellow"
    assert RISK_TO_SIGNAL["high"]     == "red"
    print("✓ test_signal_agent_risk_mapping")


def test_signal_agent_with_mock_data(tmp_path):
    """
    SignalAgent should populate state['signals'] from mock data
    and write to an in-memory SQLite DB without errors.
    """
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"

    # Re-import after setting env var so the engine picks up the new URL
    import importlib
    import shared.state as ss
    importlib.reload(ss)
    import agents.signal_agent as sa
    importlib.reload(sa)

    state = make_initial_state("test-run-002")
    state["raw_data"] = _make_mock_raw_data()
    state["analysis"] = _make_mock_analysis()

    state = sa.run(state)

    assert len(state["signals"]) == 2
    assert not state["errors"]

    cpi_signal = next(s for s in state["signals"] if s["series_id"] == "CPIAUCSL")
    assert cpi_signal["signal"] == "yellow"  # moderate → yellow

    unrate_signal = next(s for s in state["signals"] if s["series_id"] == "UNRATE")
    assert unrate_signal["signal"] == "green"   # low → green

    print("✓ test_signal_agent_with_mock_data")


def test_pipeline_handles_empty_raw_data():
    """
    Pipeline should add an error and return early if FetchAgent
    returns no data, without crashing.
    """
    state = make_initial_state("test-run-empty")
    # raw_data is empty — simulate a total FetchAgent failure

    # AnalyzeAgent should skip gracefully
    import agents.analyze_agent as aa
    state = aa.run(state)
    assert "AnalyzeAgent" in state["errors"][0]

    print("✓ test_pipeline_handles_empty_raw_data")


def test_tool_handler_unknown_series():
    """
    fetch_fred_series tool handler should return an error dict
    for an unknown series_id rather than raising an exception.
    """
    from tools.fred_tools import handle_fetch_fred_series
    result = handle_fetch_fred_series("UNKNOWN_SERIES_XYZ")
    assert "error" in result
    print("✓ test_tool_handler_unknown_series")


def test_tool_handler_missing_api_key(monkeypatch):
    """
    fetch_fred_series tool handler should return an error dict
    when FRED_API_KEY is not set.
    """
    import tools.fred_tools as ft
    original_key = ft.FRED_API_KEY
    ft.FRED_API_KEY = ""  # simulate missing key

    result = ft.handle_fetch_fred_series("CPIAUCSL")
    assert "error" in result

    ft.FRED_API_KEY = original_key  # restore
    print("✓ test_tool_handler_missing_api_key")


# ── Run directly ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile, types

    # Minimal monkeypatch shim for running without pytest
    class FakeMonkeypatch:
        pass

    test_make_initial_state()
    test_signal_agent_risk_mapping()

    with tempfile.TemporaryDirectory() as tmp:
        class FakePath:
            def __truediv__(self, name):
                return os.path.join(tmp, name)
        test_signal_agent_with_mock_data(FakePath())

    test_pipeline_handles_empty_raw_data()
    test_tool_handler_unknown_series()
    test_tool_handler_missing_api_key(FakeMonkeypatch())

    print("\n✓ All tests passed.")

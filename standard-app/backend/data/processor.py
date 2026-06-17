"""
backend/data/processor.py
──────────────────────────
Takes raw FRED DataFrames and produces structured indicator records
ready for database insertion and API response.

Responsibilities:
  1. Calculate year-over-year (YoY) and month-over-month (MoM) changes
  2. Assign signal color (green / yellow / red) based on per-indicator thresholds
  3. Merge series config metadata into each record
  4. Return a list of dicts that map cleanly to the ORM models
"""

from __future__ import annotations

import pandas as pd

from fetcher import SERIES_CONFIG

# ── Signal threshold definitions ──────────────────────────────────────────────
# Each series has its own business logic for what constitutes a healthy vs
# stressed reading. Thresholds are set relative to common market conventions.
#
# Format: { series_id: { "green": (min, max), "yellow": (min, max) } }
# Anything outside green/yellow bands is automatically "red".
#
# Note: For indicators where HIGHER is worse (unemployment, inflation),
# the green range is the lower end. For yield, it's more nuanced.

SIGNAL_THRESHOLDS: dict[str, dict] = {
    "CPIAUCSL": {
        # CPI is stored as an index level; we use YoY % change for signaling.
        # Fed target is ~2%. >4% = hot. <1% = deflation risk (yellow).
        "use_yoy": True,
        "green":  (1.0, 3.0),
        "yellow": (0.0, 4.5),
        # Outside yellow = red
    },
    "UNRATE": {
        # Unemployment rate in percent.
        # Pre-pandemic full employment ~3.5-4%. >5.5% = elevated.
        "use_yoy": False,
        "green":  (0.0, 4.5),
        "yellow": (4.5, 5.5),
    },
    "A191RL1Q225SBEA": {
        # Real GDP growth (QoQ annualized percent change).
        # Negative = contraction. <1% = sluggish.
        "use_yoy": False,
        "green":  (2.0, float("inf")),
        "yellow": (0.0, 2.0),
    },
    "DGS10": {
        # 10-Year Treasury yield in percent.
        # >5% is considered restrictive. <3% = very accommodative (not always good).
        "use_yoy": False,
        "green":  (2.5, 4.5),
        "yellow": (4.5, 5.5),
    },
}


def _assign_signal(series_id: str, value: float, yoy: float | None) -> str:
    """
    Determine signal color for a single observation.

    Args:
        series_id : FRED series identifier
        value     : latest raw observation value
        yoy       : year-over-year percent change (used for CPI)

    Returns:
        "green" | "yellow" | "red"
    """
    thresholds = SIGNAL_THRESHOLDS.get(series_id)
    if thresholds is None:
        return "yellow"  # Unknown series → neutral

    # Some indicators (CPI) are better judged by their YoY rate of change
    signal_value = yoy if (thresholds.get("use_yoy") and yoy is not None) else value

    g_min, g_max = thresholds["green"]
    y_min, y_max = thresholds["yellow"]

    if g_min <= signal_value <= g_max:
        return "green"
    elif y_min <= signal_value <= y_max:
        return "yellow"
    else:
        return "red"


def _calculate_changes(df: pd.DataFrame, series_id: str) -> tuple[float | None, float | None]:
    """
    Calculate YoY and MoM percentage changes from a time series DataFrame.

    For quarterly series (GDP), MoM is not meaningful and returns None.
    For daily series (DGS10), YoY is calculated against the value ~252 rows ago.

    Args:
        df        : DataFrame with columns [date, value], sorted ascending
        series_id : FRED series identifier (used to apply frequency-appropriate logic)

    Returns:
        (yoy_change, mom_change) — floats as percent change, or None if insufficient data
    """
    if df.empty or len(df) < 2:
        return None, None

    latest = df.iloc[-1]["value"]

    # ── Year-over-year ────────────────────────────────────────────────────────
    # Look back ~12 monthly obs (or 4 quarterly, or 252 daily trading days)
    freq_lookback = {
        "CPIAUCSL":           12,   # monthly
        "UNRATE":             12,   # monthly
        "A191RL1Q225SBEA":    4,    # quarterly
        "DGS10":              252,  # daily (approx 1 trading year)
    }
    yoy_lookback = freq_lookback.get(series_id, 12)

    if len(df) > yoy_lookback:
        prior_yoy = df.iloc[-(yoy_lookback + 1)]["value"]
        yoy = round(((latest - prior_yoy) / prior_yoy) * 100, 2) if prior_yoy else None
    else:
        yoy = None

    # ── Month-over-month (skip for quarterly GDP) ─────────────────────────────
    if series_id == "A191RL1Q225SBEA":
        mom = None
    elif len(df) > 1:
        prior_mom = df.iloc[-2]["value"]
        mom = round(((latest - prior_mom) / prior_mom) * 100, 2) if prior_mom else None
    else:
        mom = None

    return yoy, mom


def process_series(series_id: str, df: pd.DataFrame) -> dict:
    """
    Process a single FRED series into a structured indicator record.

    Args:
        series_id : FRED series identifier
        df        : Raw DataFrame(date, value) from the fetcher

    Returns:
        Dict matching the Indicator ORM model fields, plus a "history" list
        for bulk-inserting into IndicatorHistory.
    """
    # Pull metadata from the config registry
    config = next((c for c in SERIES_CONFIG if c["series_id"] == series_id), {})

    if df.empty:
        return {
            "series_id": series_id,
            "name": config.get("name", series_id),
            "value": None,
            "unit": config.get("unit"),
            "frequency": config.get("frequency"),
            "observation_date": None,
            "signal": "red",
            "yoy_change": None,
            "mom_change": None,
            "history": [],
        }

    latest_row = df.iloc[-1]
    latest_value = float(latest_row["value"])
    latest_date = str(latest_row["date"])

    yoy, mom = _calculate_changes(df, series_id)
    signal = _assign_signal(series_id, latest_value, yoy)

    # Build history list — convert to plain dicts for easy DB insertion
    history = df[["date", "value"]].rename(columns={"value": "value"}).to_dict("records")
    history = [{"date": str(r["date"]), "value": float(r["value"])} for r in history]

    return {
        "series_id": series_id,
        "name": config.get("name", series_id),
        "value": round(latest_value, 4),
        "unit": config.get("unit"),
        "frequency": config.get("frequency"),
        "observation_date": latest_date,
        "signal": signal,
        "yoy_change": yoy,
        "mom_change": mom,
        "history": history,
    }


def process_all(raw: dict[str, pd.DataFrame]) -> list[dict]:
    """
    Process all fetched series.

    Args:
        raw : dict mapping series_id → raw DataFrame from fetcher.fetch_all()

    Returns:
        List of processed indicator dicts (one per series)
    """
    results = []
    for series_id, df in raw.items():
        print(f"[PROCESS] Processing {series_id}…")
        record = process_series(series_id, df)
        results.append(record)
        print(f"[PROCESS] {series_id}: value={record['value']}, signal={record['signal']}")

    return results

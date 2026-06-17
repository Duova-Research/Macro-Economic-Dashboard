"""
backend/data/fetcher.py
────────────────────────
FRED API client.

Responsibilities:
  1. Define which series to track and their metadata
  2. Hit the FRED observations endpoint for each series
  3. Return raw DataFrames for the processor to clean

FRED API docs: https://fred.stlouisfed.org/docs/api/fred/
Rate limit   : 120 requests/minute (well within our usage)

Run standalone for a manual data pull:
    python backend/data/fetcher.py
"""

import os
import sys
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# ── FRED API config ───────────────────────────────────────────────────────────
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# How many years of history to pull for each series
HISTORY_YEARS = 5

# ── Series registry ───────────────────────────────────────────────────────────
# Each entry defines a FRED series and the metadata we want to store alongside it.
# series_id  : Official FRED identifier
# name       : Human-readable label shown in the dashboard
# unit       : Display unit (informational only)
# frequency  : Data release frequency (informational only)
SERIES_CONFIG: list[dict] = [
    {
        "series_id": "CPIAUCSL",
        "name": "CPI (All Urban Consumers)",
        "unit": "Index 1982-84=100",
        "frequency": "Monthly",
    },
    {
        "series_id": "UNRATE",
        "name": "Unemployment Rate",
        "unit": "Percent",
        "frequency": "Monthly",
    },
    {
        "series_id": "A191RL1Q225SBEA",
        "name": "Real GDP Growth (QoQ)",
        "unit": "Percent Change",
        "frequency": "Quarterly",
    },
    {
        "series_id": "DGS10",
        "name": "10-Year Treasury Yield",
        "unit": "Percent",
        "frequency": "Daily",
    },
]


# ── Core fetch function ───────────────────────────────────────────────────────
def fetch_series(series_id: str, observation_start: Optional[str] = None) -> pd.DataFrame:
    """
    Fetch observations for a single FRED series.

    Args:
        series_id        : FRED series identifier (e.g. "CPIAUCSL")
        observation_start: ISO date string "YYYY-MM-DD"; defaults to 5 years ago

    Returns:
        DataFrame with columns: date (str), value (float)
        Missing values ('.') are replaced with NaN and rows are dropped.

    Raises:
        RuntimeError: if FRED API returns a non-200 response
    """
    if not FRED_API_KEY:
        raise EnvironmentError(
            "FRED_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )

    # Default start date: HISTORY_YEARS years of data
    if observation_start is None:
        start_year = pd.Timestamp.now().year - HISTORY_YEARS
        observation_start = f"{start_year}-01-01"

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": observation_start,
        "sort_order": "asc",
    }

    print(f"[FRED] Fetching {series_id} from {observation_start}…")
    response = requests.get(FRED_BASE_URL, params=params, timeout=15)

    if response.status_code != 200:
        raise RuntimeError(
            f"[FRED] Error {response.status_code} for {series_id}: {response.text}"
        )

    data = response.json()
    observations = data.get("observations", [])

    if not observations:
        print(f"[FRED] No data returned for {series_id}")
        return pd.DataFrame(columns=["date", "value"])

    df = pd.DataFrame(observations)[["date", "value"]]

    # FRED uses "." to represent missing values — convert to NaN and drop
    df["value"] = pd.to_numeric(df["value"].replace(".", float("nan")), errors="coerce")
    df = df.dropna(subset=["value"]).reset_index(drop=True)

    print(f"[FRED] {series_id}: {len(df)} observations, latest = {df.iloc[-1]['date']}")
    return df


# ── Fetch all series ──────────────────────────────────────────────────────────
def fetch_all() -> dict[str, pd.DataFrame]:
    """
    Fetch all configured FRED series.

    Returns:
        dict mapping series_id → DataFrame(date, value)
        Failed series are skipped with a warning (graceful degradation).
    """
    results: dict[str, pd.DataFrame] = {}

    for config in SERIES_CONFIG:
        sid = config["series_id"]
        try:
            df = fetch_series(sid)
            results[sid] = df
        except Exception as exc:
            print(f"[FETCH] WARNING: Skipping {sid} — {exc}")

    print(f"[FETCH] Done. {len(results)}/{len(SERIES_CONFIG)} series fetched.")
    return results


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    """
    Manual data pull — run from the repo root:
        python backend/data/fetcher.py

    Also triggers the processor and writes to the database so you can verify
    everything works end-to-end before deploying.
    """
    # Inline import here so this file stays importable without circular deps
    from processor import process_all
    from database import init_db, SessionLocal
    from database import Indicator, IndicatorHistory

    init_db()
    raw = fetch_all()
    processed = process_all(raw)

    db = SessionLocal()
    try:
        for item in processed:
            # Upsert into indicators (latest snapshot)
            existing = db.get(Indicator, item["series_id"])
            if existing:
                for k, v in item.items():
                    setattr(existing, k, v)
            else:
                db.add(Indicator(**{k: v for k, v in item.items()
                                    if k != "history"}))

            # Insert history rows (skip duplicates via merge)
            for row in item.get("history", []):
                existing_hist = db.get(
                    IndicatorHistory, (item["series_id"], row["date"])
                )
                if not existing_hist:
                    db.add(IndicatorHistory(
                        series_id=item["series_id"],
                        date=row["date"],
                        value=row["value"],
                    ))

        db.commit()
        print("[DB] Data written successfully.")
    finally:
        db.close()

    sys.exit(0)

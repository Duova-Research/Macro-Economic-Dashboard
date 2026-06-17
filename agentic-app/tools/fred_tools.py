"""
tools/fred_tools.py
────────────────────
Tool definitions for the FetchAgent.

In the Anthropic API, "tools" are functions that Claude can decide to call.
We define each tool in two parts:
  1. A JSON schema (the "tool spec") that tells Claude what the function does
     and what arguments it takes.
  2. A Python implementation (the "tool handler") that actually executes the
     function when Claude decides to call it.

The FetchAgent sends these specs to Claude, and Claude responds with a
tool_use block whenever it wants to call one. The agent then executes the
matching handler and sends the result back as a tool_result block.

This file defines:
  - fetch_fred_series  : Pull observations for one FRED series
  - list_fred_series   : Return the list of configured series IDs

Both are pure data-fetch tools — no side effects, no DB writes.
DB writes happen in SignalAgent.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
HISTORY_YEARS = 5

# ── Series registry (same as in the non-agent version) ────────────────────────
SERIES_CONFIG = {
    "CPIAUCSL": {
        "name": "CPI (All Urban Consumers)",
        "unit": "Index 1982-84=100",
        "frequency": "Monthly",
    },
    "UNRATE": {
        "name": "Unemployment Rate",
        "unit": "Percent",
        "frequency": "Monthly",
    },
    "A191RL1Q225SBEA": {
        "name": "Real GDP Growth (QoQ)",
        "unit": "Percent Change",
        "frequency": "Quarterly",
    },
    "DGS10": {
        "name": "10-Year Treasury Yield",
        "unit": "Percent",
        "frequency": "Daily",
    },
}


# ── Tool 1: fetch_fred_series ─────────────────────────────────────────────────
FETCH_FRED_SERIES_SPEC = {
    "name": "fetch_fred_series",
    "description": (
        "Fetch historical observations for a single FRED economic series. "
        "Returns a list of {date, value} objects sorted oldest-first. "
        "Use this to retrieve CPI, unemployment, GDP, or Treasury yield data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "series_id": {
                "type": "string",
                "description": (
                    "The FRED series identifier. "
                    "Examples: CPIAUCSL, UNRATE, A191RL1Q225SBEA, DGS10."
                ),
            },
            "observation_start": {
                "type": "string",
                "description": (
                    "Start date in YYYY-MM-DD format. "
                    "Defaults to 5 years before today if omitted."
                ),
            },
        },
        "required": ["series_id"],
    },
}


def handle_fetch_fred_series(series_id: str, observation_start: str | None = None) -> dict:
    """
    Execute the fetch_fred_series tool call.

    Returns:
        {
            "series_id": "CPIAUCSL",
            "name": "CPI (All Urban Consumers)",
            "unit": "Index 1982-84=100",
            "frequency": "Monthly",
            "observations": [ {"date": "2024-01-01", "value": 308.4}, ... ],
            "count": 60,
            "latest_date": "2024-03-01",
            "latest_value": 314.8
        }

    On failure, returns: { "error": "..." }
    """
    import pandas as pd

    if not FRED_API_KEY:
        return {"error": "FRED_API_KEY not set in environment."}

    if series_id not in SERIES_CONFIG:
        return {"error": f"Unknown series_id '{series_id}'. Use list_fred_series to see available IDs."}

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

    try:
        resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json().get("observations", [])
    except requests.RequestException as e:
        return {"error": f"HTTP request failed: {e}"}

    # Clean FRED's '.' placeholder for missing values
    observations = []
    for obs in raw:
        try:
            v = float(obs["value"])
            observations.append({"date": obs["date"], "value": v})
        except (ValueError, KeyError):
            continue  # skip missing entries

    if not observations:
        return {"error": f"No valid observations returned for {series_id}"}

    config = SERIES_CONFIG[series_id]
    return {
        "series_id": series_id,
        "name": config["name"],
        "unit": config["unit"],
        "frequency": config["frequency"],
        "observations": observations,
        "count": len(observations),
        "latest_date": observations[-1]["date"],
        "latest_value": observations[-1]["value"],
    }


# ── Tool 2: list_fred_series ──────────────────────────────────────────────────
LIST_FRED_SERIES_SPEC = {
    "name": "list_fred_series",
    "description": (
        "Returns the list of FRED series this system is configured to track. "
        "Use this first if you are unsure which series IDs are available."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def handle_list_fred_series() -> dict:
    """Return the configured series metadata."""
    return {
        "available_series": [
            {"series_id": sid, **meta}
            for sid, meta in SERIES_CONFIG.items()
        ]
    }


# ── Tool dispatcher ────────────────────────────────────────────────────────────
# Maps tool name → handler function. Used by the agent loop to route
# tool_use blocks from Claude to the correct Python function.

ALL_TOOL_SPECS = [FETCH_FRED_SERIES_SPEC, LIST_FRED_SERIES_SPEC]

TOOL_HANDLERS = {
    "fetch_fred_series": lambda args: handle_fetch_fred_series(**args),
    "list_fred_series":  lambda args: handle_list_fred_series(),
}

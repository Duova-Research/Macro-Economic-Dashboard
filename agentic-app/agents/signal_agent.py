"""
agents/signal_agent.py
───────────────────────
SignalAgent: Merges raw data + Claude's analysis, applies signal thresholds,
and writes the final records to SQLite.

This agent does NOT call the Claude API. It is the "executor" step —
pure deterministic logic that:
  1. Takes the latest value from raw_data
  2. Uses yoy_change and risk_level from analysis
  3. Maps risk_level → signal color (green / yellow / red)
  4. Upserts an IndicatorRecord row for this run

Design note: We deliberately keep threshold logic out of AnalyzeAgent.
AnalyzeAgent is free to reason about the data. SignalAgent is the gatekeeper
that enforces the dashboard's display rules with deterministic code.
"""

import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.state import IndicatorRecord, MacroReport, SessionLocal, init_db
from tools.fred_tools import SERIES_CONFIG

# ── Risk level → signal color mapping ────────────────────────────────────────
# Uses AnalyzeAgent's risk_level field as a semantic proxy for signal.
# Fallback is "yellow" for any unrecognized value.
RISK_TO_SIGNAL = {
    "low":      "green",
    "moderate": "yellow",
    "elevated": "yellow",
    "high":     "red",
}


def run(state: dict) -> dict:
    """
    SignalAgent entry point.

    Reads from state:  state["raw_data"], state["analysis"]
    Writes to state:   state["signals"]  (list of dicts for ReportAgent)
    Side effects:      Upserts IndicatorRecord rows into SQLite

    Args:
        state: shared pipeline state dict

    Returns:
        Updated state dict with signals populated
    """
    print("\n[SignalAgent] Starting…")
    init_db()

    raw_data: dict = state.get("raw_data", {})
    analysis: dict = state.get("analysis", {})
    run_id: str = state.get("run_id", datetime.utcnow().isoformat())

    signals = []
    db = SessionLocal()

    try:
        for series_id, raw in raw_data.items():
            config = SERIES_CONFIG.get(series_id, {})
            interp = analysis.get(series_id, {})

            latest_value = raw.get("latest_value")
            latest_date  = raw.get("latest_date")
            yoy_change   = interp.get("yoy_change")
            risk_level   = interp.get("risk_level", "moderate")
            signal       = RISK_TO_SIGNAL.get(risk_level, "yellow")
            interpretation = interp.get("context", "")

            print(
                f"[SignalAgent] {series_id}: value={latest_value}, "
                f"risk={risk_level} → signal={signal}"
            )

            # ── Build the signal record ───────────────────────────────────────
            record_data = {
                "series_id":   series_id,
                "name":        config.get("name", series_id),
                "value":       round(latest_value, 4) if latest_value is not None else None,
                "unit":        config.get("unit"),
                "observation_date": latest_date,
                "signal":      signal,
                "yoy_change":  round(yoy_change, 4) if yoy_change is not None else None,
                "agent_interpretation": interpretation,
            }

            # Append to state["signals"] for ReportAgent to read
            signals.append(record_data)

            # ── Upsert into SQLite ────────────────────────────────────────────
            existing = db.get(IndicatorRecord, (run_id, series_id))
            if existing:
                for k, v in record_data.items():
                    setattr(existing, k, v)
            else:
                db.add(IndicatorRecord(run_id=run_id, **record_data))

        db.commit()
        print(f"[SignalAgent] Wrote {len(signals)} records to DB (run_id={run_id}).")

    except Exception as exc:
        db.rollback()
        error_msg = f"SignalAgent DB write failed: {exc}"
        print(f"[SignalAgent] ERROR: {error_msg}")
        state["errors"].append(error_msg)
    finally:
        db.close()

    state["signals"] = signals
    return state

"""
orchestrator/pipeline.py
─────────────────────────
The pipeline orchestrator. Runs all four agents in sequence, passing
shared state between them.

This is the single entry point for:
  - Manual runs:   python orchestrator/pipeline.py
  - Lambda invoke: handler.handler(event, context) calls run_pipeline()
  - n8n HTTP:      POST /run-pipeline endpoint calls run_pipeline()

Pipeline sequence:
  FetchAgent → AnalyzeAgent → SignalAgent → ReportAgent

Error handling strategy:
  - Each agent appends to state["errors"] instead of raising exceptions.
  - The orchestrator continues running subsequent agents even if one fails,
    so partial results are still stored (e.g. if AnalyzeAgent fails, the
    raw data is still written by SignalAgent using defaults).
  - A full pipeline run summary is printed at the end.

Retry policy:
  - FetchAgent has internal retries via Claude's tool-use loop.
  - If FetchAgent returns empty raw_data, the orchestrator aborts early
    (no point running AnalyzeAgent on nothing).
  - Other agents run regardless of upstream partial failures.
"""

import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Make sure sibling packages are importable when running from any directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import fetch_agent, analyze_agent, signal_agent, report_agent
from shared.state import make_initial_state


def run_pipeline(run_id: str | None = None) -> dict:
    """
    Execute the full macro data pipeline.

    Args:
        run_id: optional identifier for this run (defaults to current UTC ISO time)

    Returns:
        The final shared state dict after all agents have run.
        Inspect state["errors"] to check for partial failures.
    """
    start = time.time()
    state = make_initial_state(run_id)

    print(f"\n{'='*60}")
    print(f"  Macro Agent Pipeline — run_id: {state['run_id']}")
    print(f"{'='*60}")

    # ── Step 1: FetchAgent ────────────────────────────────────────────────────
    state = fetch_agent.run(state)

    if not state["raw_data"]:
        state["errors"].append("Pipeline aborted: FetchAgent returned no data.")
        _print_summary(state, start)
        return state

    # ── Step 2: AnalyzeAgent ──────────────────────────────────────────────────
    state = analyze_agent.run(state)

    # ── Step 3: SignalAgent ───────────────────────────────────────────────────
    state = signal_agent.run(state)

    # ── Step 4: ReportAgent ───────────────────────────────────────────────────
    state = report_agent.run(state)

    # ── Done ──────────────────────────────────────────────────────────────────
    _print_summary(state, start)
    return state


def _print_summary(state: dict, start: float) -> None:
    """Print a formatted pipeline run summary to stdout."""
    elapsed = round(time.time() - start, 1)
    errors = state.get("errors", [])
    signals = state.get("signals", [])

    print(f"\n{'='*60}")
    print(f"  Pipeline Complete — {elapsed}s elapsed")
    print(f"{'='*60}")
    print(f"  Series fetched  : {len(state.get('raw_data', {}))}")
    print(f"  Series analyzed : {len(state.get('analysis', {}))}")
    print(f"  Signals written : {len(signals)}")

    if signals:
        print(f"\n  Signal summary:")
        for s in signals:
            dot = {"green": "●", "yellow": "◑", "red": "○"}.get(s["signal"], "?")
            print(f"    {dot} {s['name']:<40} {str(s.get('value', 'N/A')):<10} {s['signal']}")

    if state.get("report"):
        preview = state["report"][:200].replace("\n", " ")
        print(f"\n  Report preview: {preview}…")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors:
            print(f"    ✗ {e}")
    else:
        print(f"\n  ✓ No errors.")
    print()


# ── Standalone entry point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    """
    Run the full pipeline manually:
        python orchestrator/pipeline.py
    """
    final_state = run_pipeline()
    sys.exit(1 if final_state["errors"] else 0)

"""
agents/analyze_agent.py
────────────────────────
AnalyzeAgent: Uses Claude to interpret the raw FRED observations.

This agent does NOT use tool calls. Instead, it sends all the raw data
to Claude in a single prompt and asks for a structured JSON interpretation
of each series.

This is the "reasoning" step — Claude brings economic knowledge to the
numbers. The output becomes the agent_interpretation field stored by
SignalAgent and surfaced in the dashboard.

What Claude produces for each series:
  {
    "series_id": "CPIAUCSL",
    "yoy_change": 3.48,
    "mom_change": 0.38,
    "trend": "accelerating" | "decelerating" | "stable",
    "context": "A 1-2 sentence plain English interpretation",
    "risk_level": "low" | "moderate" | "elevated" | "high"
  }

Note on token cost:
  We send all observations in the prompt. For daily series like DGS10 this
  can be 1000+ rows. We therefore trim each series to the last 60 observations
  before sending, which is sufficient for YoY/MoM calculation.
"""

import json
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# How many recent observations to include in the prompt
# (keeps the context window manageable for daily series)
MAX_OBS_IN_PROMPT = 60


def _trim_observations(observations: list) -> list:
    """Return at most MAX_OBS_IN_PROMPT most-recent observations."""
    return observations[-MAX_OBS_IN_PROMPT:] if len(observations) > MAX_OBS_IN_PROMPT else observations


def run(state: dict) -> dict:
    """
    AnalyzeAgent entry point.

    Reads from state:  state["raw_data"]
    Writes to state:   state["analysis"] = { series_id: interpretation_dict }

    Args:
        state: shared pipeline state dict

    Returns:
        Updated state dict with analysis populated
    """
    print("\n[AnalyzeAgent] Starting…")

    raw_data: dict = state.get("raw_data", {})
    if not raw_data:
        state["errors"].append("AnalyzeAgent: raw_data is empty; skipping analysis.")
        return state

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ── Build a compact JSON payload of all series for the prompt ─────────────
    series_payloads = []
    for sid, data in raw_data.items():
        series_payloads.append({
            "series_id": sid,
            "name": data.get("name"),
            "unit": data.get("unit"),
            "frequency": data.get("frequency"),
            "latest_date": data.get("latest_date"),
            "latest_value": data.get("latest_value"),
            "recent_observations": _trim_observations(data.get("observations", [])),
        })

    # ── Prompt ────────────────────────────────────────────────────────────────
    system_prompt = """
You are a quantitative macroeconomic analyst.
You will receive recent observations for several U.S. economic indicators.

For each series, calculate and return a structured analysis.
You MUST return a valid JSON array — no markdown fences, no extra text.
Each element must have exactly these fields:
  - series_id       (string)
  - yoy_change      (float, percent; null if insufficient data)
  - mom_change      (float, percent; null if not applicable for this frequency)
  - trend           ("accelerating" | "decelerating" | "stable")
  - context         (string, 1-2 sentences, plain English, no jargon)
  - risk_level      ("low" | "moderate" | "elevated" | "high")

Definition of trend:
  - accelerating: the rate of change is increasing (getting larger in abs value)
  - decelerating: the rate of change is decreasing
  - stable: the value is moving within a narrow range

Calibration for risk_level:
  - CPI YoY:  <2% or >5% = high; 2-3% = low; else moderate/elevated
  - UNRATE:   <4% = low; 4-5% = moderate; 5-6% = elevated; >6% = high
  - GDP QoQ:  <0% = high; 0-1% = elevated; 1-3% = moderate; >3% = low
  - DGS10:    <2.5% = elevated; 2.5-4.5% = low; 4.5-5.5% = moderate; >5.5% = high
""".strip()

    user_message = (
        "Analyze the following FRED economic series and return the JSON array.\n\n"
        + json.dumps(series_payloads, indent=2)
    )

    print(f"[AnalyzeAgent] Sending {len(series_payloads)} series to Claude for interpretation…")

    # ── Single API call (no tool use needed here) ─────────────────────────────
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text.strip() if response.content else ""

    # ── Parse the JSON response ───────────────────────────────────────────────
    analysis: dict = {}
    try:
        # Strip any accidental markdown fences Claude might have added
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.DOTALL).strip()
        parsed: list = json.loads(clean)

        for item in parsed:
            sid = item.get("series_id")
            if sid:
                analysis[sid] = item
                print(
                    f"[AnalyzeAgent] {sid}: yoy={item.get('yoy_change')}, "
                    f"risk={item.get('risk_level')}, trend={item.get('trend')}"
                )
    except (json.JSONDecodeError, AttributeError) as exc:
        error_msg = f"AnalyzeAgent: failed to parse Claude response — {exc}"
        print(f"[AnalyzeAgent] ERROR: {error_msg}")
        print(f"[AnalyzeAgent] Raw response: {raw_text[:400]}")
        state["errors"].append(error_msg)

    state["analysis"] = analysis
    print(f"[AnalyzeAgent] Done. Interpreted {len(analysis)} series.")
    return state

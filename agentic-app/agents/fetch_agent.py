"""
agents/fetch_agent.py
──────────────────────
FetchAgent: Uses Claude in an agentic tool-use loop to pull FRED data.

Why use an agent here instead of calling the FRED API directly?

  1. Retry logic — if a tool call returns an error (e.g. rate limit, bad
     series ID), Claude can decide to call the tool again with adjusted
     parameters rather than crashing the pipeline.

  2. Selective fetching — Claude can call list_fred_series first, then
     decide which series to fetch based on the instructions. This makes
     the agent extensible: you can add new series to the registry and
     Claude will pick them up without code changes.

  3. Validation — Claude can inspect the returned data and flag anomalies
     ("the latest value for UNRATE is 45.2, which seems wrong") before
     passing the data downstream.

Agent loop pattern (standard for all agents in this system):
  ┌───────────────────────────────────────────────────────┐
  │  1. Build a messages list with a system + user prompt  │
  │  2. Call Claude API with tool specs                    │
  │  3. If response is tool_use:                           │
  │       a. Execute the tool                              │
  │       b. Append the result to messages                 │
  │       c. Go back to step 2                             │
  │  4. If response is end_turn: extract final output      │
  └───────────────────────────────────────────────────────┘

The loop exits when Claude returns stop_reason == "end_turn", meaning
it has finished calling tools and is giving a final text response.
"""

import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

from tools.fred_tools import ALL_TOOL_SPECS, TOOL_HANDLERS

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 12   # Safety cap: stop the loop after this many tool calls


def run(state: dict) -> dict:
    """
    FetchAgent entry point.

    Reads from state: nothing (this is the first agent)
    Writes to state: state["raw_data"] = { series_id: tool_result_dict }

    Args:
        state: shared pipeline state dict

    Returns:
        Updated state dict with raw_data populated
    """
    print("\n[FetchAgent] Starting…")
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ── Build the initial prompt ──────────────────────────────────────────────
    system_prompt = """
You are a data retrieval agent for a macroeconomic dashboard.

Your job is to fetch the latest FRED economic data using the tools provided.

Instructions:
1. Call list_fred_series to discover which series are available.
2. Call fetch_fred_series for EACH series in the list.
3. After fetching all series, respond with a JSON object summarizing what
   you collected, in this format:
   {
     "fetched": ["CPIAUCSL", "UNRATE", ...],
     "failed": [],
     "notes": "any observations about data quality"
   }

If a fetch_fred_series call returns an error, try it once more before
marking it as failed. Do not stop early — fetch every available series.
""".strip()

    user_message = (
        "Please fetch all configured FRED series now. "
        "The pipeline is waiting for the data."
    )

    messages = [{"role": "user", "content": user_message}]

    # ── Agent loop ────────────────────────────────────────────────────────────
    raw_data: dict = {}
    iterations = 0

    while iterations < MAX_ITERATIONS:
        iterations += 1
        print(f"[FetchAgent] Iteration {iterations}…")

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=ALL_TOOL_SPECS,
            messages=messages,
        )

        # Append Claude's response to the conversation history
        messages.append({"role": "assistant", "content": response.content})

        # ── Check stop reason ─────────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            # Claude is done calling tools. Extract any text content.
            print("[FetchAgent] Completed.")
            break

        if response.stop_reason != "tool_use":
            # Unexpected stop reason — bail out
            state["errors"].append(
                f"FetchAgent: unexpected stop_reason={response.stop_reason}"
            )
            break

        # ── Process tool calls ────────────────────────────────────────────────
        # Claude may call multiple tools in a single response turn.
        # We process all of them and add all results before the next API call.
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            tool_use_id = block.id

            print(f"[FetchAgent] Tool call: {tool_name}({json.dumps(tool_input)[:80]})")

            # Execute the tool
            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                result = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    result = handler(tool_input)
                except Exception as exc:
                    result = {"error": str(exc)}

            # If this was a successful fetch_fred_series call, store the data
            if tool_name == "fetch_fred_series" and "error" not in result:
                sid = result["series_id"]
                raw_data[sid] = result
                print(f"[FetchAgent] Stored {sid}: {result['count']} obs, latest={result['latest_date']}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(result),
            })

        # Append all tool results as the next user turn
        messages.append({"role": "user", "content": tool_results})

    # ── Write to shared state ─────────────────────────────────────────────────
    state["raw_data"] = raw_data
    print(f"[FetchAgent] Done. Fetched {len(raw_data)} series: {list(raw_data.keys())}")
    return state

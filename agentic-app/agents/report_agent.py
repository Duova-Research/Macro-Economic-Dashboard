"""
agents/report_agent.py
───────────────────────
ReportAgent: Asks Claude to synthesize all signals into a short macro
narrative paragraph displayed at the top of the dashboard.

This agent receives the full signals list and the individual
agent_interpretation strings from AnalyzeAgent, then asks Claude to
write a coherent, jargon-free summary of the current macro environment.

Output contract:
  A single string, 3-5 sentences, plain English.
  No headers, no bullets, no markdown.
  Suitable for display as a dashboard "macro summary" card.

Example output:
  "Inflation remains above the Fed's 2% target at 3.5% YoY, though the
   pace of price increases has decelerated over the past three months.
   The labor market continues to show resilience, with unemployment at
   3.9% — near a 50-year low. GDP growth of 2.8% in Q4 suggests the
   economy has avoided a recession despite elevated borrowing costs.
   The 10-year Treasury yield at 4.8% reflects ongoing expectations of
   higher-for-longer Fed policy."
"""

import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


def run(state: dict) -> dict:
    """
    ReportAgent entry point.

    Reads from state:  state["signals"]
    Writes to state:   state["report"] (string)
    Side effects:      Persists the report to the macro_reports table

    Args:
        state: shared pipeline state dict

    Returns:
        Updated state dict with report populated
    """
    print("\n[ReportAgent] Starting…")

    signals = state.get("signals", [])
    if not signals:
        state["errors"].append("ReportAgent: signals list is empty; skipping report.")
        return state

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ── Build a concise signal summary for the prompt ─────────────────────────
    signal_lines = []
    for s in signals:
        yoy_str = f", YoY {s['yoy_change']:+.2f}%" if s.get("yoy_change") is not None else ""
        signal_lines.append(
            f"- {s['name']}: {s['value']} {s.get('unit', '')}{yoy_str} "
            f"[signal={s['signal']}] — {s.get('agent_interpretation', '')}"
        )
    signal_summary = "\n".join(signal_lines)

    # ── Prompt ────────────────────────────────────────────────────────────────
    system_prompt = """
You are an economic commentator writing for a professional macro dashboard.
Write a 3-5 sentence plain English summary of the current U.S. macroeconomic
environment based on the indicators provided.

Rules:
- No bullet points, no headers, no markdown formatting
- Use specific numbers from the data
- Connect the indicators to each other where relevant (e.g. inflation vs rate expectations)
- Neutral, analytical tone — not alarmist, not cheerleading
- End the paragraph on the most important forward-looking point
""".strip()

    user_message = (
        "Here are the current macro indicator readings:\n\n"
        + signal_summary
        + "\n\nPlease write the macro summary paragraph."
    )

    print("[ReportAgent] Requesting narrative summary from Claude…")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    report_text = response.content[0].text.strip() if response.content else ""
    print(f"[ReportAgent] Report ({len(report_text)} chars):\n  {report_text[:200]}…")

    # ── Persist report to database ────────────────────────────────────────────
    try:
        from shared.state import MacroReport, SessionLocal

        db = SessionLocal()
        run_id = state.get("run_id", "unknown")
        existing = db.get(MacroReport, run_id)
        if existing:
            existing.report = report_text
        else:
            db.add(MacroReport(run_id=run_id, report=report_text))
        db.commit()
        db.close()
        print("[ReportAgent] Report saved to DB.")
    except Exception as exc:
        state["errors"].append(f"ReportAgent DB write failed: {exc}")

    state["report"] = report_text
    return state

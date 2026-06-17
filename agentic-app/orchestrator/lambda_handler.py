"""
orchestrator/lambda_handler.py
───────────────────────────────
AWS Lambda entry point for the AI agent pipeline.

Invoked daily by EventBridge. Runs the full 4-agent pipeline
and returns a summary of the run.

Deploy with: cd infrastructure && ./deploy_agent.sh
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def handler(event, context):
    """Lambda entry point."""
    print(f"[Lambda] Agent pipeline invoked. Event: {json.dumps(event)}")

    try:
        from orchestrator.pipeline import run_pipeline
        state = run_pipeline()

        result = {
            "statusCode": 200,
            "body": json.dumps({
                "run_id":       state["run_id"],
                "series_count": len(state.get("signals", [])),
                "errors":       state.get("errors", []),
                "success":      len(state.get("errors", [])) == 0,
            }),
        }
        print(f"[Lambda] Pipeline complete: {result['body']}")
        return result

    except Exception as exc:
        print(f"[Lambda] Fatal error: {exc}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }

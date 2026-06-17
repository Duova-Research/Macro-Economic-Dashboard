"""
infrastructure/lambda/handler.py
──────────────────────────────────
AWS Lambda entry point for scheduled FRED data pulls.

Triggered by an EventBridge rule (see eventbridge.json) daily at 06:00 UTC.
Connects to the same SQLite database used by the FastAPI server (via a shared
EFS mount or an RDS endpoint in production).

Architecture note:
  For a simple deployment, the Lambda writes to an SQLite file on Amazon EFS
  (Elastic File System) mounted at /mnt/efs/macro_data.db.
  The FastAPI server (on EC2 or ECS) also mounts the same EFS path.

  For a more robust setup, swap SQLite for RDS PostgreSQL and update
  DATABASE_URL in both the Lambda and FastAPI environments.

Environment variables (set in Lambda config, not .env):
  FRED_API_KEY    : FRED API key
  DATABASE_URL    : sqlite:////mnt/efs/macro_data.db  (EFS path)
  API_REFRESH_URL : (optional) URL to call the FastAPI /refresh endpoint instead
  API_SECRET      : (optional) REFRESH_SECRET from FastAPI .env
"""

import json
import os
import sys
import urllib.request
import urllib.error

# Lambda includes /var/task in sys.path; add sibling backend directory
# Structure expected: lambda_package/handler.py + lambda_package/data/...
sys.path.insert(0, os.path.dirname(__file__))


def handler(event, context):
    """
    Lambda handler — called by EventBridge on schedule.

    Two modes:
      1. Direct mode : Import fetcher/processor/database and write to SQLite on EFS.
      2. HTTP mode   : Call the FastAPI /refresh endpoint (simpler, avoids EFS).

    Mode is selected by the presence of API_REFRESH_URL in environment.

    Args:
        event   : EventBridge scheduled event (not used directly)
        context : Lambda context object

    Returns:
        dict with statusCode and body for CloudWatch logging
    """
    print(f"[Lambda] Invoked. Event: {json.dumps(event)}")

    # ── Mode 2: HTTP refresh call (preferred for simple deployments) ──────────
    api_url = os.getenv("API_REFRESH_URL")
    api_secret = os.getenv("API_SECRET", "")

    if api_url:
        return _http_refresh(api_url, api_secret)

    # ── Mode 1: Direct DB write (requires EFS or RDS) ─────────────────────────
    return _direct_refresh()


def _http_refresh(api_url: str, api_secret: str) -> dict:
    """
    Call the FastAPI /refresh endpoint to trigger a data pull.
    This is the simpler approach — the Lambda just acts as a scheduler,
    and the FastAPI server does all the heavy lifting.
    """
    try:
        req = urllib.request.Request(
            url=f"{api_url.rstrip('/')}/refresh",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Refresh-Secret": api_secret,
            },
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            print(f"[Lambda] HTTP refresh success: {body}")
            return {"statusCode": 200, "body": json.dumps(body)}

    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}: {e.read().decode()}"
        print(f"[Lambda] HTTP refresh failed: {msg}")
        return {"statusCode": e.code, "body": msg}

    except Exception as exc:
        print(f"[Lambda] Unexpected error: {exc}")
        return {"statusCode": 500, "body": str(exc)}


def _direct_refresh() -> dict:
    """
    Directly import and run the fetcher + processor + database writer.
    Used when the Lambda has EFS access to the SQLite file.
    """
    try:
        from data.fetcher import fetch_all
        from data.processor import process_all
        from data.database import init_db, SessionLocal, Indicator, IndicatorHistory
        from datetime import datetime

        init_db()
        raw = fetch_all()
        processed = process_all(raw)

        db = SessionLocal()
        count = 0
        try:
            for item in processed:
                existing = db.get(Indicator, item["series_id"])
                if existing:
                    for k, v in item.items():
                        if k != "history":
                            setattr(existing, k, v)
                    existing.fetched_at = datetime.utcnow()
                else:
                    db.add(Indicator(**{k: v for k, v in item.items() if k != "history"}))

                for row in item.get("history", []):
                    if not db.get(IndicatorHistory, (item["series_id"], row["date"])):
                        db.add(IndicatorHistory(
                            series_id=item["series_id"],
                            date=row["date"],
                            value=row["value"],
                        ))
                count += 1

            db.commit()
        finally:
            db.close()

        result = {"refreshed": count, "timestamp": datetime.utcnow().isoformat()}
        print(f"[Lambda] Direct refresh success: {result}")
        return {"statusCode": 200, "body": json.dumps(result)}

    except Exception as exc:
        print(f"[Lambda] Direct refresh failed: {exc}")
        return {"statusCode": 500, "body": str(exc)}

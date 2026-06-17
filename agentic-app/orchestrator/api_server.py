"""
orchestrator/api_server.py
───────────────────────────
FastAPI server that exposes the agent pipeline output to the React frontend.

This replaces the original non-agent backend/api/main.py.
Key differences:
  - /indicators reads from indicator_records table (written by SignalAgent)
  - /report     returns the latest MacroReport (written by ReportAgent)
  - /run-pipeline triggers a full agent pipeline run synchronously
    (use with caution — a full run takes ~15-30s)

For production, move /run-pipeline to a background task or Lambda,
and serve the React frontend against this API.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

load_dotenv()

from shared.state import IndicatorRecord, MacroReport, SessionLocal, init_db

app = FastAPI(
    title="Macro Agent Dashboard API",
    description="Serves AI-agent-generated macro indicator data to the React frontend.",
    version="2.0.0",
)

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
REFRESH_SECRET  = os.getenv("REFRESH_SECRET", "dev-secret-change-me")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/indicators")
def get_indicators(db: Session = Depends(get_db)):
    """
    Return the latest run's indicator records.
    Picks the most recent run_id and returns all rows for it.
    """
    # Get the most recent run_id
    latest = (
        db.query(IndicatorRecord.run_id)
        .order_by(IndicatorRecord.created_at.desc())
        .first()
    )
    if not latest:
        raise HTTPException(
            status_code=404,
            detail="No data yet. Run: python orchestrator/pipeline.py"
        )

    rows = (
        db.query(IndicatorRecord)
        .filter(IndicatorRecord.run_id == latest[0])
        .all()
    )

    return [
        {
            "series_id":    r.series_id,
            "name":         r.name,
            "value":        r.value,
            "unit":         r.unit,
            "observation_date": r.observation_date,
            "signal":       r.signal,
            "yoy_change":   r.yoy_change,
            "agent_interpretation": r.agent_interpretation,
            "run_id":       r.run_id,
            "fetched_at":   r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.get("/report")
def get_report(db: Session = Depends(get_db)):
    """Return the latest macro narrative report from ReportAgent."""
    row = db.query(MacroReport).order_by(MacroReport.created_at.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="No report available yet.")
    return {
        "run_id":     row.run_id,
        "report":     row.report,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.post("/run-pipeline")
def run_pipeline_endpoint(x_refresh_secret: str = Header(default="")):
    """
    Trigger a full agent pipeline run.
    Protected by X-Refresh-Secret header.

    Warning: This is synchronous and takes ~15-30s.
    For production, use a background task or invoke via Lambda.
    """
    if x_refresh_secret != REFRESH_SECRET:
        raise HTTPException(status_code=401, detail="Invalid refresh secret.")

    from orchestrator.pipeline import run_pipeline
    state = run_pipeline()

    return {
        "run_id":       state["run_id"],
        "series_count": len(state.get("signals", [])),
        "errors":       state.get("errors", []),
        "report_preview": state.get("report", "")[:200],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)

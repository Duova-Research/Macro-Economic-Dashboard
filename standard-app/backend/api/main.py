"""
backend/api/main.py
────────────────────
FastAPI REST server.

Endpoints:
  GET /health                  → liveness probe for AWS ALB / Lambda
  GET /indicators              → latest snapshot of all KPIs (for the card row)
  GET /history/{series_id}     → full time series for a given indicator (for charts)
  POST /refresh                → manually trigger a data pull (protected by a secret)

Run locally:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

The React frontend hits this API. CORS is configured via FRONTEND_ORIGIN in .env.
"""

import os
import sys
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Add the parent directory to sys.path so we can import from data/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import Indicator, IndicatorHistory, get_db, init_db

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Macro Economic Dashboard API",
    description="Serves FRED economic indicators to the React frontend.",
    version="1.0.0",
)

# CORS — allow the React dev server and production frontend origin
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secret for the /refresh endpoint — set REFRESH_SECRET in .env for prod
REFRESH_SECRET = os.getenv("REFRESH_SECRET", "dev-secret-change-me")


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    """Initialize database tables when the server starts."""
    init_db()


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Meta"])
def health():
    """
    Simple liveness probe.
    Used by AWS Application Load Balancer and Lambda health checks.
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ── GET /indicators ───────────────────────────────────────────────────────────
@app.get("/indicators", tags=["Data"])
def get_indicators(db: Session = Depends(get_db)):
    """
    Return the latest snapshot for all tracked indicators.

    Used by the React KPI card row — one call loads all four cards.

    Response shape:
    [
      {
        "series_id": "CPIAUCSL",
        "name": "CPI (All Urban Consumers)",
        "value": 314.8,
        "unit": "Index 1982-84=100",
        "frequency": "Monthly",
        "observation_date": "2024-03-01",
        "signal": "yellow",
        "yoy_change": 3.48,
        "mom_change": 0.38,
        "fetched_at": "2024-04-15T06:01:22"
      },
      ...
    ]
    """
    rows = db.query(Indicator).all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No indicators found. Run the fetcher first: python backend/data/fetcher.py"
        )

    return [
        {
            "series_id": r.series_id,
            "name": r.name,
            "value": r.value,
            "unit": r.unit,
            "frequency": r.frequency,
            "observation_date": r.observation_date,
            "signal": r.signal,
            "yoy_change": r.yoy_change,
            "mom_change": r.mom_change,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


# ── GET /history/{series_id} ──────────────────────────────────────────────────
@app.get("/history/{series_id}", tags=["Data"])
def get_history(
    series_id: str,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Return the full time series for a single indicator.

    Used by Recharts line charts. Pass ?limit=60 to cap the number of data points
    (useful for quarterly GDP which has many decades of history).

    Args:
        series_id : FRED series ID (e.g. "CPIAUCSL")
        limit     : optional — max number of most-recent observations to return

    Response shape:
    {
      "series_id": "CPIAUCSL",
      "history": [
        { "date": "2019-04-01", "value": 255.7 },
        { "date": "2019-05-01", "value": 256.1 },
        ...
      ]
    }
    """
    query = (
        db.query(IndicatorHistory)
        .filter(IndicatorHistory.series_id == series_id)
        .order_by(IndicatorHistory.date.asc())
    )

    rows = query.all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No history found for series_id='{series_id}'. "
                   "Check that the series ID is correct and the fetcher has been run."
        )

    history = [{"date": r.date, "value": r.value} for r in rows]

    # Apply limit to the most recent N observations
    if limit:
        history = history[-limit:]

    return {"series_id": series_id, "history": history}


# ── POST /refresh ─────────────────────────────────────────────────────────────
@app.post("/refresh", tags=["Admin"])
def refresh_data(x_refresh_secret: str = Header(default=""), db: Session = Depends(get_db)):
    """
    Manually trigger a fresh data pull from FRED.

    Protected by a shared secret header: X-Refresh-Secret.
    This is the same endpoint that n8n or a Lambda layer can call to
    trigger updates without needing direct server access.

    Headers:
        X-Refresh-Secret: <value of REFRESH_SECRET in .env>

    Returns:
        { "refreshed": 4, "timestamp": "..." }
    """
    if x_refresh_secret != REFRESH_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing refresh secret.")

    # Import here to avoid circular imports at module load time
    from data.fetcher import fetch_all
    from data.processor import process_all

    raw = fetch_all()
    processed = process_all(raw)

    count = 0
    for item in processed:
        # Upsert latest indicator snapshot
        existing = db.get(Indicator, item["series_id"])
        if existing:
            for k, v in item.items():
                if k != "history":
                    setattr(existing, k, v)
            existing.fetched_at = datetime.utcnow()
        else:
            db.add(Indicator(**{k: v for k, v in item.items() if k != "history"}))

        # Insert new history rows (ignore existing dates)
        for row in item.get("history", []):
            if not db.get(IndicatorHistory, (item["series_id"], row["date"])):
                db.add(IndicatorHistory(
                    series_id=item["series_id"],
                    date=row["date"],
                    value=row["value"],
                ))
        count += 1

    db.commit()
    return {"refreshed": count, "timestamp": datetime.utcnow().isoformat()}

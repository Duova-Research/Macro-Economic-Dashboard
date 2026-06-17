"""
backend/data/database.py
────────────────────────
SQLAlchemy ORM setup for SQLite.

Two tables:
  - indicators      : latest snapshot per series (one row per indicator)
  - indicator_history: full time series for charting

Usage:
    from data.database import SessionLocal, init_db
    init_db()                        # creates tables if they don't exist
    db = SessionLocal()
    db.add(...)
    db.commit()
    db.close()
"""

import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# ── Database connection ───────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./macro_data.db")

engine = create_engine(
    DATABASE_URL,
    # check_same_thread=False is required for SQLite when used with FastAPI
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── ORM Base ──────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Table: indicators (latest value per series) ───────────────────────────────
class Indicator(Base):
    """
    Stores the most recent data point for each FRED series.
    Upserted on every fetch cycle so this always reflects current values.
    """

    __tablename__ = "indicators"

    series_id: str = Column(String, primary_key=True, index=True)
    name: str = Column(String, nullable=False)          # Human-readable label
    value: float = Column(Float, nullable=True)         # Latest observation value
    unit: str = Column(String, nullable=True)           # e.g. "Percent", "Index"
    frequency: str = Column(String, nullable=True)      # Monthly, Quarterly, Daily
    observation_date: str = Column(String, nullable=True)  # Date of latest value
    signal: str = Column(String, nullable=True)         # "green" | "yellow" | "red"
    yoy_change: float = Column(Float, nullable=True)    # Year-over-year delta
    mom_change: float = Column(Float, nullable=True)    # Month-over-month delta
    fetched_at: datetime = Column(DateTime, default=datetime.utcnow)


# ── Table: indicator_history (time series for charting) ───────────────────────
class IndicatorHistory(Base):
    """
    Stores all historical data points for each series.
    Used to render the time series line charts in the React frontend.
    Primary key is (series_id, date) to prevent duplicate rows.
    """

    __tablename__ = "indicator_history"

    series_id: str = Column(String, primary_key=True)
    date: str = Column(String, primary_key=True)   # YYYY-MM-DD
    value: float = Column(Float, nullable=True)


# ── Init helper ───────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables initialized.")


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """
    Yields a SQLAlchemy session for use as a FastAPI dependency.
    Ensures the session is always closed after the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

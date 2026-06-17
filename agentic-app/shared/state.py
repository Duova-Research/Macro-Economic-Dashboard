"""
shared/state.py
────────────────
Defines the shared state object that flows through the agent pipeline,
and the SQLAlchemy ORM models that SignalAgent writes to.

The shared state is a plain Python dict. Each agent receives it,
adds its own output key, and passes the updated dict forward.

State shape after a full pipeline run:
{
    "run_id":    "2024-04-15T06:00:00",   # ISO timestamp of the run
    "raw_data":  { series_id: [...] },     # populated by FetchAgent
    "analysis":  { series_id: {...} },     # populated by AnalyzeAgent
    "signals":   [ {...}, ... ],           # populated by SignalAgent
    "report":    "string",                 # populated by ReportAgent
    "errors":    [ "..." ],               # any agent can append here
}
"""

import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./macro_agent.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class IndicatorRecord(Base):
    """
    Final processed indicator — written by SignalAgent after the full pipeline.
    One row per series per run_id (so we keep a history of pipeline runs).
    """
    __tablename__ = "indicator_records"

    run_id: str        = Column(String, primary_key=True)
    series_id: str     = Column(String, primary_key=True)
    name: str          = Column(String)
    value: float       = Column(Float)
    unit: str          = Column(String)
    observation_date: str = Column(String)
    signal: str        = Column(String)        # green / yellow / red
    yoy_change: float  = Column(Float)
    agent_interpretation: str = Column(Text)  # AnalyzeAgent's Claude output
    created_at: datetime = Column(DateTime, default=datetime.utcnow)


class MacroReport(Base):
    """
    The narrative macro summary produced by ReportAgent.
    One row per pipeline run.
    """
    __tablename__ = "macro_reports"

    run_id: str     = Column(String, primary_key=True)
    report: str     = Column(Text)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)


def make_initial_state(run_id: str | None = None) -> dict:
    """
    Return a fresh pipeline state dict.
    run_id defaults to the current UTC ISO timestamp.
    """
    return {
        "run_id":   run_id or datetime.utcnow().isoformat(),
        "raw_data":  {},
        "analysis":  {},
        "signals":   [],
        "report":    "",
        "errors":    [],
    }

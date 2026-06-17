# Macro Economic Dashboard — AI Agent System

## What This Is

A multi-agent pipeline that replaces the manual fetch/process/store cycle
with autonomous AI agents. Each agent has a single responsibility, uses
the Anthropic Claude API as its reasoning core, and communicates through
a shared state object.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR                                   │
│  orchestrator/pipeline.py                                               │
│  - Boots the pipeline on a schedule (or on-demand)                      │
│  - Passes shared state between agents in sequence                       │
│  - Handles failures with retry and fallback logic                       │
└───────┬─────────────┬──────────────┬──────────────┬────────────────────┘
        │             │              │              │
        ▼             ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐
  │  FETCH   │  │ ANALYZE  │  │ SIGNAL   │  │   REPORT AGENT   │
  │  AGENT   │  │  AGENT   │  │  AGENT   │  │                  │
  │          │  │          │  │          │  │ Generates a plain │
  │ Pulls    │  │ Asks     │  │ Applies  │  │ English macro     │
  │ FRED API │  │ Claude   │  │ signal   │  │ summary via       │
  │ data via │  │ what the │  │ logic +  │  │ Claude API        │
  │ tools    │  │ numbers  │  │ stores   │  │                   │
  │          │  │ mean     │  │ to DB    │  │                   │
  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘
        │             │              │              │
        └─────────────┴──────────────┴──────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   SHARED STATE     │
                    │  (Python dict)     │
                    │  raw_data          │
                    │  analysis          │
                    │  signals           │
                    │  report            │
                    └────────────────────┘
```

---

## Agent Roles

| Agent | File | What Claude Does |
|---|---|---|
| FetchAgent | agents/fetch_agent.py | Uses a `fetch_fred_series` tool to pull FRED data; retries on failure |
| AnalyzeAgent | agents/analyze_agent.py | Reasons over raw numbers; returns structured JSON interpretation |
| SignalAgent | agents/signal_agent.py | Applies threshold logic; writes final records to SQLite |
| ReportAgent | agents/report_agent.py | Writes a short macro commentary paragraph for the dashboard |

---

## Why Agents Instead of Plain Scripts?

A plain script runs fixed logic. An agent loop runs until the task is done.

Key differences in this system:
- FetchAgent can retry a failed series by calling the tool again with adjusted params
- AnalyzeAgent can ask a follow-up question of itself if the first analysis is incomplete
- ReportAgent can decide to call a search tool if it needs context (e.g. recent Fed news)
- The orchestrator can detect a stale AnalyzeAgent output and re-run it

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # Add ANTHROPIC_API_KEY and FRED_API_KEY
python orchestrator/pipeline.py
```

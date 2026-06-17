# Macro Economic Dashboard

A full-stack macro data system that pulls live economic indicators from the FRED API,
stores them in SQLite, serves them via FastAPI, and displays them in a React dashboard.
Includes AWS Lambda + EventBridge for scheduled cloud updates, and an n8n alternative.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                               │
│  FRED API (Federal Reserve Economic Data)                       │
│  Indicators: CPI, Unemployment Rate, GDP Growth, 10Y Yield      │
└────────────────────────┬────────────────────────────────────────┘
                         │ Python fetch script
┌────────────────────────▼────────────────────────────────────────┐
│                     PROCESSING LAYER                            │
│  backend/data/fetcher.py   → Pulls raw data from FRED API       │
│  backend/data/processor.py → Cleans, calculates YoY/MoM delta  │
│  backend/data/database.py  → Stores time series in SQLite       │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────────┐
│                       API LAYER                                 │
│  backend/api/main.py       → FastAPI server (port 8000)         │
│  Endpoints: /indicators, /history/{series_id}                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP fetch
┌────────────────────────▼────────────────────────────────────────┐
│                     FRONTEND LAYER                              │
│  React + Recharts                                               │
│  - KPI cards with signal lights (green/yellow/red)              │
│  - Time series line charts per indicator                        │
│  - Auto-refresh every 60 seconds                                │
└─────────────────────────────────────────────────────────────────┘

                     SCHEDULING LAYER
┌──────────────────────────────┐  ┌──────────────────────────────┐
│  AWS Lambda + EventBridge    │  │  n8n (self-hosted alternative)│
│  Runs fetcher daily at 6AM   │  │  HTTP Request → Python script │
│  infrastructure/lambda/      │  │  infrastructure/n8n/         │
└──────────────────────────────┘  └──────────────────────────────┘
```

---

## FRED Indicators Tracked

| Series ID     | Indicator             | Signal Logic                    |
|---------------|-----------------------|---------------------------------|
| CPIAUCSL      | CPI (YoY)             | >4% = Red, 2-4% = Yellow, <2% = Green |
| UNRATE        | Unemployment Rate     | >5% = Red, 4-5% = Yellow, <4% = Green |
| A191RL1Q225SBEA | Real GDP Growth (QoQ) | <0% = Red, 0-2% = Yellow, >2% = Green |
| DGS10         | 10Y Treasury Yield    | >5% = Red, 4-5% = Yellow, <4% = Green |

---

## Setup

### 1. Get FRED API Key
Free at: https://fred.stlouisfed.org/docs/api/api_key.html

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # Add your FRED_API_KEY
python data/fetcher.py        # Initial data pull
uvicorn api.main:app --reload # Start API on port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm start                     # React dev server on port 3000
```

### 4. AWS Lambda Deployment
```bash
cd infrastructure/lambda
./deploy.sh                   # Packages + deploys to Lambda
```

### 5. n8n Alternative
Import `infrastructure/n8n/workflow.json` into your n8n instance.

---

## Project Structure

```
macro-dashboard/
├── backend/
│   ├── api/
│   │   └── main.py             # FastAPI server + CORS + endpoints
│   ├── data/
│   │   ├── fetcher.py          # FRED API client
│   │   ├── processor.py        # Data cleaning + signal calculation
│   │   └── database.py         # SQLite ORM (SQLAlchemy)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── KPICard.jsx     # Signal-light indicator card
│   │   │   ├── LineChart.jsx   # Recharts time series wrapper
│   │   │   └── Dashboard.jsx   # Main layout
│   │   ├── hooks/
│   │   │   └── useIndicators.js # Data fetching + auto-refresh
│   │   ├── utils/
│   │   │   └── signals.js      # Signal color logic
│   │   ├── App.jsx
│   │   └── index.js
│   └── package.json
└── infrastructure/
    ├── lambda/
    │   ├── handler.py          # Lambda entry point
    │   ├── deploy.sh           # AWS CLI deployment script
    │   └── eventbridge.json    # Daily schedule rule
    └── n8n/
        └── workflow.json       # n8n workflow import file
```

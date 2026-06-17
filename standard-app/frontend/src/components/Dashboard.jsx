/**
 * frontend/src/components/Dashboard.jsx
 * ───────────────────────────────────────
 * Root layout component. Composes all visual sections:
 *
 *   ┌─────────────────────────────────────────┐
 *   │  Header: title + last-updated + refresh  │
 *   ├─────────────────────────────────────────┤
 *   │  KPI Cards (4 columns)                   │
 *   ├─────────────────────────────────────────┤
 *   │  Line Charts (2 columns × 2 rows)        │
 *   └─────────────────────────────────────────┘
 *
 * Relies on useIndicators hook for data fetching and auto-refresh.
 */

import React from "react";
import { KPICard } from "./KPICard";
import { LineChart } from "./LineChart";
import { useIndicators } from "../hooks/useIndicators";
import { getSignalStyle } from "../utils/signals";

export function Dashboard() {
  const { indicators, history, loading, error, lastUpdated, refresh } = useIndicators();

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={centerStyle}>
        <div style={{ color: "#64748b", fontSize: "16px" }}>
          Loading macro data…
        </div>
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div style={centerStyle}>
        <div style={{ color: "#ef4444", fontSize: "15px", maxWidth: "480px", textAlign: "center" }}>
          <strong>Could not load data.</strong>
          <br />
          <span style={{ color: "#94a3b8", fontSize: "13px" }}>{error}</span>
          <br /><br />
          <button onClick={refresh} style={refreshBtnStyle}>Retry</button>
        </div>
      </div>
    );
  }

  // ── Build chart config from indicators so signal color matches the card ──
  const chartConfigs = indicators.map((ind) => ({
    series_id: ind.series_id,
    name: ind.name,
    unit: ind.unit,
    color: getSignalStyle(ind.signal).dot,
  }));

  // ── Format last-updated timestamp ─────────────────────────────────────────
  const updatedLabel = lastUpdated
    ? `Updated ${lastUpdated.toLocaleTimeString()}`
    : "Never";

  return (
    <div style={pageStyle}>

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div style={headerStyle}>
        <div>
          <h1 style={{ color: "#f1f5f9", fontSize: "22px", fontWeight: 700, margin: 0 }}>
            Macro Economic Dashboard
          </h1>
          <p style={{ color: "#475569", fontSize: "12px", margin: "4px 0 0" }}>
            FRED Data · Auto-refresh every 60s · {updatedLabel}
          </p>
        </div>
        <button onClick={refresh} style={refreshBtnStyle} title="Refresh now">
          ↺ Refresh
        </button>
      </div>

      {/* ── KPI Cards ───────────────────────────────────────────────────── */}
      <section style={sectionStyle}>
        <div style={cardRowStyle}>
          {indicators.map((ind) => (
            <KPICard key={ind.series_id} indicator={ind} />
          ))}
        </div>
      </section>

      {/* ── Time Series Charts ───────────────────────────────────────────── */}
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Historical Trends</h2>
        <div style={chartGridStyle}>
          {chartConfigs.map((cfg) => (
            <LineChart
              key={cfg.series_id}
              title={cfg.name}
              data={history[cfg.series_id] ?? []}
              signalColor={cfg.color}
              unit={cfg.unit}
            />
          ))}
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer style={{ color: "#334155", fontSize: "11px", textAlign: "center", padding: "24px 0" }}>
        Data sourced from the Federal Reserve Bank of St. Louis (FRED) via public API.
        Not financial advice.
      </footer>

    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const pageStyle = {
  background: "#0d0d1a",
  minHeight: "100vh",
  padding: "32px 40px",
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  boxSizing: "border-box",
};

const headerStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  marginBottom: "32px",
};

const sectionStyle = {
  marginBottom: "32px",
};

const sectionTitleStyle = {
  color: "#64748b",
  fontSize: "12px",
  fontWeight: 600,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  margin: "0 0 16px",
};

const cardRowStyle = {
  display: "flex",
  gap: "16px",
  flexWrap: "wrap",
};

const chartGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
  gap: "16px",
};

const centerStyle = {
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#0d0d1a",
};

const refreshBtnStyle = {
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: "8px",
  color: "#94a3b8",
  cursor: "pointer",
  fontSize: "13px",
  fontWeight: 500,
  padding: "8px 16px",
};

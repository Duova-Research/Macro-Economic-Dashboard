/**
 * frontend/src/components/LineChart.jsx
 * ───────────────────────────────────────
 * Thin wrapper around Recharts <LineChart> for rendering
 * a single FRED indicator's time series.
 *
 * Props:
 *   title      {string}  - display title for the chart
 *   data       {Array}   - array of { date: string, value: number }
 *   signalColor{string}  - hex color matching the indicator's signal (e.g. "#22c55e")
 *   unit       {string}  - unit label for the Y-axis tooltip suffix
 */

import React, { useMemo } from "react";
import {
  LineChart as ReLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// ── Custom Tooltip ─────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: "#0f172a",
        border: "1px solid #334155",
        borderRadius: "8px",
        padding: "10px 14px",
        fontSize: "13px",
        color: "#f1f5f9",
      }}
    >
      <div style={{ color: "#64748b", marginBottom: "4px" }}>{label}</div>
      <div style={{ fontWeight: 700 }}>
        {payload[0].value?.toFixed(2)}
        {unit?.toLowerCase().includes("percent") ? "%" : ""}
      </div>
    </div>
  );
}

export function LineChart({ title, data, signalColor = "#3b82f6", unit = "" }) {
  // Sub-sample very dense daily series (DGS10) for clean rendering
  // Show at most 120 data points; for shorter series show all.
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return [];
    if (data.length <= 120) return data;
    const step = Math.ceil(data.length / 120);
    return data.filter((_, i) => i % step === 0);
  }, [data]);

  // Format X-axis dates — show year only to avoid label clutter
  const formatXAxis = (dateStr) => {
    if (!dateStr) return "";
    return dateStr.slice(0, 7);  // "YYYY-MM"
  };

  if (!chartData.length) {
    return (
      <div style={cardStyle}>
        <h3 style={titleStyle}>{title}</h3>
        <div style={{ color: "#475569", padding: "40px 0", textAlign: "center" }}>
          No data available
        </div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      {/* Chart title */}
      <h3 style={titleStyle}>{title}</h3>

      {/* Recharts container — always set width to 100% for responsiveness */}
      <ResponsiveContainer width="100%" height={220}>
        <ReLineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />

          <XAxis
            dataKey="date"
            tickFormatter={formatXAxis}
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={{ stroke: "#1e293b" }}
            tickLine={false}
            interval="preserveStartEnd"
          />

          <YAxis
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={45}
            tickFormatter={(v) => v.toFixed(1)}
          />

          <Tooltip
            content={<CustomTooltip unit={unit} />}
            cursor={{ stroke: "#334155", strokeWidth: 1 }}
          />

          <Line
            type="monotone"
            dataKey="value"
            stroke={signalColor}
            strokeWidth={2}
            dot={false}             // No dots for dense time series
            activeDot={{ r: 4, fill: signalColor }}
          />
        </ReLineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Shared styles ──────────────────────────────────────────────────────────────
const cardStyle = {
  background: "#1a1a2e",
  border: "1px solid #1e293b",
  borderRadius: "12px",
  padding: "20px 24px",
  flex: "1",
  minWidth: "280px",
};

const titleStyle = {
  color: "#94a3b8",
  fontSize: "13px",
  fontWeight: 500,
  marginBottom: "16px",
  margin: "0 0 16px 0",
};

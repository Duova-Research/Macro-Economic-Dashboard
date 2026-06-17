/**
 * frontend/src/components/KPICard.jsx
 * ─────────────────────────────────────
 * A single indicator card displaying:
 *   - Indicator name and latest value
 *   - Signal color dot (green / yellow / red)
 *   - YoY and MoM change deltas
 *   - Observation date and data frequency
 *
 * Props:
 *   indicator {object} - one item from the /indicators API response
 */

import React from "react";
import { getSignalStyle, formatValue, formatChange } from "../utils/signals";

export function KPICard({ indicator }) {
  const {
    name,
    value,
    unit,
    signal,
    yoy_change,
    mom_change,
    observation_date,
    frequency,
  } = indicator;

  const style = getSignalStyle(signal);

  return (
    <div
      style={{
        background: "#1a1a2e",
        border: `1px solid ${style.dot}33`,   // 20% opacity border matches signal
        borderRadius: "12px",
        padding: "24px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        minWidth: "220px",
        flex: "1",
        boxShadow: "0 4px 24px rgba(0,0,0,0.3)",
        transition: "border-color 0.3s ease",
      }}
    >
      {/* ── Header: name + signal dot ──────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <span style={{ color: "#94a3b8", fontSize: "13px", fontWeight: 500, lineHeight: 1.4 }}>
          {name}
        </span>
        <div
          title={`Signal: ${style.label}`}
          style={{
            width: "10px",
            height: "10px",
            borderRadius: "50%",
            background: style.dot,
            boxShadow: `0 0 8px ${style.dot}`,
            flexShrink: 0,
            marginTop: "2px",
          }}
        />
      </div>

      {/* ── Main value ────────────────────────────────────────────────── */}
      <div style={{ color: "#f1f5f9", fontSize: "32px", fontWeight: 700, letterSpacing: "-0.5px" }}>
        {formatValue(value, unit)}
      </div>

      {/* ── Signal badge ──────────────────────────────────────────────── */}
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          background: style.badge,
          borderRadius: "6px",
          padding: "4px 10px",
          width: "fit-content",
        }}
      >
        <span style={{ color: style.dot, fontSize: "12px", fontWeight: 600 }}>
          ● {style.label.toUpperCase()}
        </span>
      </div>

      {/* ── Change deltas ─────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: "16px" }}>
        {yoy_change !== null && (
          <div>
            <div style={{ color: "#64748b", fontSize: "11px", marginBottom: "2px" }}>YoY</div>
            <div
              style={{
                color: yoy_change >= 0 ? "#f97316" : "#22c55e",  // orange = up, green = down
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              {formatChange(yoy_change)}
            </div>
          </div>
        )}
        {mom_change !== null && (
          <div>
            <div style={{ color: "#64748b", fontSize: "11px", marginBottom: "2px" }}>MoM</div>
            <div
              style={{
                color: mom_change >= 0 ? "#f97316" : "#22c55e",
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              {formatChange(mom_change)}
            </div>
          </div>
        )}
      </div>

      {/* ── Footer: date + frequency ──────────────────────────────────── */}
      <div style={{ color: "#475569", fontSize: "11px", marginTop: "auto" }}>
        {frequency} · {observation_date ?? "N/A"}
      </div>
    </div>
  );
}

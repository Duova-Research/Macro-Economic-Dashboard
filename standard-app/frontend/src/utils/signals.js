/**
 * frontend/src/utils/signals.js
 * ──────────────────────────────
 * Maps the signal string returned by the API ("green" | "yellow" | "red")
 * to visual tokens used throughout the dashboard.
 *
 * All color decisions are centralized here so the signal logic lives
 * in one place and component code stays clean.
 */

/** @type {{ [signal: string]: { dot: string, badge: string, label: string } }} */
export const SIGNAL_STYLES = {
  green: {
    dot: "#22c55e",        // Tailwind green-500
    badge: "rgba(34, 197, 94, 0.12)",
    label: "Normal",
  },
  yellow: {
    dot: "#eab308",        // Tailwind yellow-500
    badge: "rgba(234, 179, 8, 0.12)",
    label: "Watch",
  },
  red: {
    dot: "#ef4444",        // Tailwind red-500
    badge: "rgba(239, 68, 68, 0.12)",
    label: "Alert",
  },
};

/**
 * Get the visual style tokens for a given signal string.
 * Falls back to yellow/neutral for unknown values.
 *
 * @param {string} signal - "green" | "yellow" | "red"
 * @returns {{ dot: string, badge: string, label: string }}
 */
export function getSignalStyle(signal) {
  return SIGNAL_STYLES[signal] ?? SIGNAL_STYLES.yellow;
}

/**
 * Format a numeric value with the appropriate display suffix.
 * FRED returns raw index values (CPI) and percent values (UNRATE, DGS10).
 * We display everything as a clean number with 2 decimal places.
 *
 * @param {number|null} value
 * @param {string} unit  - the unit string from the API
 * @returns {string}
 */
export function formatValue(value, unit = "") {
  if (value === null || value === undefined) return "N/A";
  const isPercent = unit.toLowerCase().includes("percent") ||
                    unit.toLowerCase().includes("change");
  return isPercent
    ? `${value.toFixed(2)}%`
    : value.toFixed(2);
}

/**
 * Format a YoY or MoM change value as a signed percent string.
 * e.g. 3.48 → "+3.48%", -0.5 → "-0.50%"
 *
 * @param {number|null} change
 * @returns {string}
 */
export function formatChange(change) {
  if (change === null || change === undefined) return "—";
  const sign = change >= 0 ? "+" : "";
  return `${sign}${change.toFixed(2)}%`;
}

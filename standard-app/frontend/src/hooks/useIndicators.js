/**
 * frontend/src/hooks/useIndicators.js
 * ─────────────────────────────────────
 * Custom hook that fetches indicator data from the FastAPI backend
 * and keeps it fresh with a configurable auto-refresh interval.
 *
 * Returns:
 *   indicators  : array of indicator objects (for KPI cards)
 *   history     : object mapping series_id → array of { date, value }
 *   loading     : boolean — true on initial load
 *   error       : error message string or null
 *   lastUpdated : Date of the most recent successful fetch
 *   refresh     : function to manually trigger a re-fetch
 */

import { useState, useEffect, useCallback, useRef } from "react";

// Series IDs to fetch history for (must match SERIES_CONFIG in fetcher.py)
const SERIES_IDS = ["CPIAUCSL", "UNRATE", "A191RL1Q225SBEA", "DGS10"];

// Auto-refresh interval in milliseconds (60 seconds)
const REFRESH_INTERVAL_MS = 60_000;

const API_BASE = process.env.REACT_APP_API_URL ?? "http://localhost:8000";

export function useIndicators() {
  const [indicators, setIndicators] = useState([]);
  const [history, setHistory] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Ref to hold the interval ID so we can clear it on unmount
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);

      // ── 1. Fetch all latest indicator snapshots in parallel with history ──
      const [indicatorsRes, ...historyRes] = await Promise.all([
        fetch(`${API_BASE}/indicators`),
        ...SERIES_IDS.map((id) => fetch(`${API_BASE}/history/${id}?limit=60`)),
      ]);

      // Check for HTTP errors on the indicators endpoint
      if (!indicatorsRes.ok) {
        const body = await indicatorsRes.json().catch(() => ({}));
        throw new Error(body.detail ?? `API error ${indicatorsRes.status}`);
      }

      const indicatorsData = await indicatorsRes.json();

      // ── 2. Parse history responses (gracefully skip any that failed) ───────
      const historyData = {};
      for (let i = 0; i < SERIES_IDS.length; i++) {
        const res = historyRes[i];
        const id = SERIES_IDS[i];
        if (res.ok) {
          const body = await res.json();
          historyData[id] = body.history ?? [];
        } else {
          console.warn(`[useIndicators] History fetch failed for ${id}`);
          historyData[id] = [];
        }
      }

      // ── 3. Update state ────────────────────────────────────────────────────
      setIndicators(indicatorsData);
      setHistory(historyData);
      setLastUpdated(new Date());
    } catch (err) {
      console.error("[useIndicators] Fetch error:", err);
      setError(err.message ?? "Failed to fetch data from the API.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch + set up auto-refresh interval
  useEffect(() => {
    fetchData();

    intervalRef.current = setInterval(() => {
      console.log("[useIndicators] Auto-refresh triggered");
      fetchData();
    }, REFRESH_INTERVAL_MS);

    // Cleanup on unmount
    return () => clearInterval(intervalRef.current);
  }, [fetchData]);

  return {
    indicators,
    history,
    loading,
    error,
    lastUpdated,
    refresh: fetchData,  // expose for the manual refresh button
  };
}

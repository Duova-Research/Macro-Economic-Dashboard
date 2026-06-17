// frontend/src/App.jsx
// Root React component — simply mounts the Dashboard.
// Global CSS resets are applied here.

import React from "react";
import { Dashboard } from "./components/Dashboard";

// Global CSS reset injected via JS for portability (no separate .css file needed)
const globalStyles = `
  *, *::before, *::after { box-sizing: border-box; }
  body { margin: 0; padding: 0; background: #0d0d1a; }
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
`;

export default function App() {
  return (
    <>
      <style>{globalStyles}</style>
      <Dashboard />
    </>
  );
}

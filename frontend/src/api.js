// Thin fetch wrapper around the RescueOps FastAPI backend.
// In dev, vite proxies /api -> http://localhost:8000 (see vite.config.js).
const BASE = import.meta.env.VITE_API_URL || "/api";

async function req(path, options) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  listIncidents: () => req("/incidents"),
  startRun: (incident_id, chaos_config) =>
    req("/runs", {
      method: "POST",
      body: JSON.stringify({ incident_id, chaos_config }),
    }),
  approve: (run_id, approved, note) =>
    req(`/runs/${run_id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved, approver: "human-ui", note }),
    }),
  latestEval: () => req("/eval"),
  runEval: () => req("/eval", { method: "POST" }),
};

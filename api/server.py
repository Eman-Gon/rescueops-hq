"""FastAPI backend for RescueOps — progressive autonomy, request/response.

Run from the repo root:
    uvicorn api.server:app --reload

All API routes live under the /api prefix so a single service can serve both the
JSON API and the built React frontend (mounted at / from frontend/dist). The same
frontend code works in dev (vite proxies /api -> here) and in production (same
origin), so deploying is one container with one URL and no CORS.

API endpoints (all prefixed /api):
    GET  /api/health                -> liveness probe
    GET  /api/incidents             -> list selectable incidents (no ground_truth)
    POST /api/runs                  -> run to approval; safe actions auto-execute.
                                       Returns a RunResult: status="resolved" when
                                       there were no risky actions (fully autonomous),
                                       or status="awaiting_approval" with pending risky.
    POST /api/runs/{run_id}/approve -> resume: execute approved risky actions, then
                                       verification..postmortem; returns resolved RunResult.
    GET  /api/runs/{run_id}         -> fetch the current RunResult for a run_id.
    GET  /api/eval                  -> latest persisted eval summary (or null)
    POST /api/eval                  -> run evaluate_all() over all 5 incidents, return summary

Run-state (the RunResult) is held in memory keyed by run_id. The audit trail still
persists to SQLite via pipeline's per-stage logging, so a server restart loses
in-flight runs but never the recorded history.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import incidents
from evaluation import evaluate_all, get_latest_eval
from pipeline import resume_after_approval, run_until_approval
from schemas import ApprovalDecision, RunResult

app = FastAPI(title="RescueOps API", version="1.0")
api = APIRouter(prefix="/api")

# Demo-only: wide-open CORS so a separately-hosted frontend can also call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory run-state, keyed by run_id. A single dict holds the RunResult through
# its whole lifecycle (awaiting_approval -> resolved). Audit history persists
# separately in SQLite, so a restart loses in-flight runs but never the history.
_RUNS: Dict[str, RunResult] = {}


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    incident_id: str
    chaos_config: Optional[Dict[str, Any]] = None


class ApproveRequest(BaseModel):
    approved: bool
    approver: str = "human-ui"
    note: str = ""


class IncidentSummary(BaseModel):
    id: str
    title: str = ""
    alert: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@api.get("/health")
def health() -> dict:
    return {"status": "ok"}


@api.get("/incidents", response_model=list[IncidentSummary])
def list_incidents() -> list[IncidentSummary]:
    """Selectable incidents for the picker. Never exposes ground_truth."""
    return [
        IncidentSummary(
            id=inc["id"], title=inc.get("title", ""), alert=inc.get("alert", "")
        )
        for inc in incidents.load_incidents()
    ]


@api.post("/runs", response_model=RunResult)
def start_run(req: RunRequest) -> RunResult:
    """Run to approval: triage -> diagnosis -> remediation, auto-executing safe
    actions. Returns a resolved RunResult when there were no risky actions (fully
    autonomous), or status="awaiting_approval" with the pending risky actions held
    in memory so the HTTP request never blocks on a human."""
    try:
        incidents.get_incident(req.incident_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown incident: {req.incident_id}")

    result = run_until_approval(req.incident_id, req.chaos_config)
    _RUNS[result.run_id] = result
    return result


@api.post("/runs/{run_id}/approve", response_model=RunResult)
def approve_run(run_id: str, req: ApproveRequest) -> RunResult:
    """Apply the human decision on the pending risky actions, then run
    verification -> postmortem and return the resolved RunResult."""
    result = _RUNS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown or expired run: {run_id}")
    if result.status != "awaiting_approval":
        # Already resolved (e.g. the autonomous path) — nothing to approve.
        return result

    decision = ApprovalDecision(
        approved=req.approved, approver=req.approver, note=req.note
    )
    resolved = resume_after_approval(result, decision)
    _RUNS[run_id] = resolved
    return resolved


@api.get("/runs/{run_id}", response_model=RunResult)
def get_run_result(run_id: str) -> RunResult:
    """Fetch the current RunResult for a run_id (awaiting_approval or resolved)."""
    result = _RUNS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown or expired run: {run_id}")
    return result


@api.get("/eval")
def latest_eval() -> dict | None:
    """Most recently persisted eval summary, or null if never run."""
    return get_latest_eval()


@api.post("/eval")
def run_eval() -> dict:
    """Run evaluate_all() over all 5 incidents, persist, and return the summary.
    Slow (full pipeline per incident) — the UI should show a spinner."""
    return evaluate_all()


# Register API routes BEFORE the catch-all static mount so /api/* always wins.
app.include_router(api)

# Serve the built React app at / in production (single-service deploy). In dev
# this dir may be absent or stale — the vite dev server serves the UI instead.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

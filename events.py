"""Minimal append-only event producer used by the Track A model layer."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
_lock = Lock()

_ACTORS = {
    "commander",
    "triage",
    "diagnosis",
    "remediation",
    "verification",
    "postmortem",
    "human",
    "chaos",
    "gateway",
    "system",
}
_EVENT_TYPES = {
    "incident_opened",
    "agent_dispatched",
    "agent_started",
    "tool_call",
    "tool_result",
    "tool_failed",
    "finding",
    "action_proposed",
    "approval_requested",
    "approval_granted",
    "approval_denied",
    "action_executed",
    "verification_passed",
    "verification_failed",
    "commander_decision",
    "commander_overruled",
    "model_fallback",
    "chaos_injected",
    "chaos_cleared",
    "incident_resolved",
    "postmortem_ready",
    "oncall_notified",
    "oncall_reply",
}


def append_event(
    *,
    incident_id: str,
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Append one event with the Architecture §4 envelope."""
    if actor not in _ACTORS:
        raise ValueError(f"unknown event actor: {actor}")
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        raise ValueError("event payload.summary must be a non-empty human sentence")
    with _lock:
        event = {
            "seq": len(_events[incident_id]) + 1,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "incident_id": incident_id,
            "actor": actor,
            "type": event_type,
            "payload": deepcopy(payload),
            "trace_id": trace_id,
        }
        _events[incident_id].append(event)
        return deepcopy(event)


def list_events(incident_id: str) -> list[dict[str, Any]]:
    """Return a snapshot of locally produced events."""
    with _lock:
        return deepcopy(_events.get(incident_id, []))


def clear_events(incident_id: str | None = None) -> None:
    """Clear local events; intended for isolated tests."""
    with _lock:
        if incident_id is None:
            _events.clear()
        else:
            _events.pop(incident_id, None)

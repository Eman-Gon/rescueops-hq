"""Chaos injection — degrade the observable BEFORE any agent sees it.

This is the reliability story for the demo: a judge disables a telemetry source
(or flags the primary model as broken) and the system keeps running on degraded
data. Track A calls `apply_chaos` inside `run_incident`; this module owns the
degradation logic so the pipeline never reimplements it.

Contract (see README):
  chaos_config = {
      "disable_sources": ["logs", "metrics", "deploys"],  # any subset
      "break_primary_model": bool,
  }
- None or {} -> observable returned unchanged.
- Each disabled source is replaced with its empty equivalent ([] or {}).
- break_primary_model does NOT touch the observable; the pipeline reads the flag
  and routes through a fallback model via build_llm().
- Never raises. Degraded data is valid data.
"""
from copy import deepcopy

# Empty equivalent for each telemetry source, matching incidents.json shapes.
_EMPTY_BY_SOURCE = {
    "logs": [],
    "metrics": {},
    "deploys": [],
}


def apply_chaos(observable: dict, chaos_config: dict | None) -> dict:
    if not chaos_config:
        return observable

    disable_sources = chaos_config.get("disable_sources") or []
    if not disable_sources:
        return observable

    degraded = deepcopy(observable)
    telemetry = degraded.get("telemetry", {})
    for source in disable_sources:
        if source in telemetry:
            telemetry[source] = deepcopy(_EMPTY_BY_SOURCE.get(source, []))
    return degraded

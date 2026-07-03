"""Pipeline control-flow tests, driven by IncidentStateMachine + the Commander.

These monkeypatch pipeline's small per-stage seam functions directly (never
CrewAI/LLM internals) — the same "mock at a clean boundary" style already used in
tests/test_llm_client.py. LLM/gateway integration itself is covered there and by the
live A2 verify gate (needs real Makers credentials; not run headlessly here).
"""
from __future__ import annotations

import pipeline
from events import clear_events, list_events
from schemas import (
    ApprovalDecision,
    CommanderDecision,
    DiagnosisReport,
    PostmortemReport,
    RemediationAction,
    RemediationPlan,
    TriageReport,
    VerificationReport,
)

INCIDENT_ID = "INC-001-checkout-db-pool"


def _triage(severity: str = "SEV-2") -> TriageReport:
    return TriageReport(
        severity=severity,
        customer_facing=True,
        summary="Checkout DB pool exhausted.",
        route_to="Diagnosis",
        reason="matched SEV rule",
    )


def _diagnosis(confidence: float = 0.9) -> DiagnosisReport:
    return DiagnosisReport(
        root_cause="Connection pool exhausted under load.",
        cited_evidence=["db.pool.active=100"],
        confidence=confidence,
        reasoning="Pool saturation matches the error spike.",
    )


def _plan(risky: bool = False) -> RemediationPlan:
    risky_actions = (
        [RemediationAction(action="Roll back deploy", rationale="bad deploy", destructive=True)]
        if risky
        else []
    )
    return RemediationPlan(
        safe=[RemediationAction(action="Scale up pool size", rationale="relieve pressure", destructive=False)],
        risky=risky_actions,
    )


def _verification(recovered: bool) -> VerificationReport:
    return VerificationReport(
        recovered=recovered,
        metric_name="error_rate",
        observed_value=0.01 if recovered else 0.5,
        threshold=0.05,
        note="projected",
    )


def _postmortem() -> PostmortemReport:
    return PostmortemReport(
        summary="Resolved.",
        timeline=["pool exhausted", "scaled up", "recovered"],
        root_cause="Connection pool exhausted under load.",
        actions_taken=["Scale up pool size"],
        follow_ups=["Add pool-size alert"],
    )


def _patch_common(monkeypatch, *, triage=None, diagnosis=None, verification_sequence=None, postmortem=None):
    monkeypatch.setattr(pipeline, "_run_triage", lambda obs, rubric: triage or _triage())
    if diagnosis is not None:
        monkeypatch.setattr(pipeline, "_run_diagnosis", lambda *a, **k: diagnosis)
    else:
        def _boom(*a, **k):
            raise AssertionError("_run_diagnosis should not be called on the fast path")
        monkeypatch.setattr(pipeline, "_run_diagnosis", _boom)

    if verification_sequence is not None:
        seq = iter(verification_sequence)
        monkeypatch.setattr(pipeline, "_run_verification", lambda *a, **k: next(seq))
    monkeypatch.setattr(pipeline, "_run_postmortem", lambda *a, **k: postmortem or _postmortem())


def test_sev3_fast_path_skips_diagnosis(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(monkeypatch, triage=_triage("SEV-3"), verification_sequence=[_verification(True)])
    monkeypatch.setattr(pipeline, "_run_remediation", lambda *a, **k: _plan())
    monkeypatch.setattr(
        pipeline, "_get_commander_decision",
        lambda ctx: CommanderDecision(move="fast_path", rationale="SEV-3, no customer impact"),
    )

    result = pipeline.run_until_approval(INCIDENT_ID)

    assert result.status == pipeline.STATUS_RESOLVED
    assert result.diagnosis is None
    assert result.postmortem is not None


def test_diagnosis_escalation_stops_before_remediation(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(monkeypatch, diagnosis=_diagnosis(confidence=0.2))

    def _boom(*a, **k):
        raise AssertionError("_run_remediation should not be called after escalation")
    monkeypatch.setattr(pipeline, "_run_remediation", _boom)

    decisions = iter([
        CommanderDecision(move="deep_diagnosis", rationale="needs investigation"),
        CommanderDecision(move="escalate_to_human", rationale="confidence too low"),
    ])
    monkeypatch.setattr(pipeline, "_get_commander_decision", lambda ctx: next(decisions))

    result = pipeline.run_until_approval(INCIDENT_ID)

    assert result.status == pipeline.STATUS_ESCALATED
    assert result.remediation is None
    assert result.postmortem is None
    assert result.diagnosis is not None


def test_illegal_triage_move_falls_back_and_pipeline_still_completes(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(monkeypatch, diagnosis=_diagnosis(), verification_sequence=[_verification(True)])
    monkeypatch.setattr(pipeline, "_run_remediation", lambda *a, **k: _plan())

    decisions = iter([
        CommanderDecision(move="launch_missiles", rationale="illegal"),
        CommanderDecision(move="dispatch_remediation", rationale="proceed"),
    ])
    monkeypatch.setattr(pipeline, "_get_commander_decision", lambda ctx: next(decisions))

    result = pipeline.run_until_approval(INCIDENT_ID)

    assert result.status == pipeline.STATUS_RESOLVED
    events = list_events(INCIDENT_ID)
    assert any(e["type"] == "commander_overruled" for e in events)


def test_no_risky_actions_resolves_autonomously_with_gapless_events(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(monkeypatch, diagnosis=_diagnosis(), verification_sequence=[_verification(True)])
    monkeypatch.setattr(pipeline, "_run_remediation", lambda *a, **k: _plan(risky=False))
    monkeypatch.setattr(
        pipeline, "_get_commander_decision",
        lambda ctx: CommanderDecision(move="dispatch_remediation", rationale="proceed"),
    )

    result = pipeline.run_until_approval(INCIDENT_ID)

    assert result.status == pipeline.STATUS_RESOLVED
    assert result.verification.recovered is True
    assert result.postmortem is not None

    events = list_events(INCIDENT_ID)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["payload"]["summary"].strip() for e in events)
    assert events[-1]["type"] == "incident_resolved"


def test_risky_actions_pause_then_resume_resolves(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(monkeypatch, diagnosis=_diagnosis(), verification_sequence=[_verification(True)])
    monkeypatch.setattr(pipeline, "_run_remediation", lambda *a, **k: _plan(risky=True))
    monkeypatch.setattr(
        pipeline, "_get_commander_decision",
        lambda ctx: CommanderDecision(move="dispatch_remediation", rationale="proceed"),
    )

    paused = pipeline.run_until_approval(INCIDENT_ID)

    assert paused.status == pipeline.STATUS_AWAITING
    assert paused.state_snapshot
    assert paused.remediation.risky

    decision = ApprovalDecision(approved=True, approver="human-ui", note="looks safe")
    resolved = pipeline.resume_after_approval(paused, decision)

    assert resolved.status == pipeline.STATUS_RESOLVED
    assert resolved.postmortem is not None
    events = list_events(INCIDENT_ID)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


def _commander_decision_for(ctx: dict) -> CommanderDecision:
    state = ctx["current_state"]
    if state == "triage":
        return CommanderDecision(move="deep_diagnosis", rationale="investigate")
    if state == "diagnosis":
        return CommanderDecision(move="dispatch_remediation", rationale="proceed")
    if state == "verification_decision":
        return CommanderDecision(move="retry_remediation", rationale="try again")
    raise AssertionError(f"unexpected commander context state: {state}")


def test_verification_retries_once_then_recovers(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(
        monkeypatch,
        diagnosis=_diagnosis(),
        verification_sequence=[_verification(False), _verification(True)],
    )
    plans = iter([_plan(risky=False), _plan(risky=False)])
    monkeypatch.setattr(pipeline, "_run_remediation", lambda *a, **k: next(plans))
    monkeypatch.setattr(pipeline, "_get_commander_decision", _commander_decision_for)

    result = pipeline.run_until_approval(INCIDENT_ID)

    assert result.status == pipeline.STATUS_RESOLVED
    assert result.verification.recovered is True


def test_verification_retries_exceed_cap_then_escalates(monkeypatch) -> None:
    clear_events(INCIDENT_ID)
    _patch_common(
        monkeypatch,
        diagnosis=_diagnosis(),
        verification_sequence=[_verification(False), _verification(False)],
    )
    monkeypatch.setattr(pipeline, "_run_remediation", lambda *a, **k: _plan(risky=False))
    monkeypatch.setattr(pipeline, "_get_commander_decision", _commander_decision_for)

    result = pipeline.run_until_approval(INCIDENT_ID)

    assert result.status == pipeline.STATUS_ESCALATED
    assert result.postmortem is None
    events = list_events(INCIDENT_ID)
    assert events[-1]["type"] == "commander_overruled"
    assert events[-1]["payload"]["applied_move"] == "escalate"

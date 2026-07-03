"""Incident response pipeline — sequential CrewAI crews with progressive autonomy.

Core behavior after remediation produces safe[] and risky[]:
  (a) every SAFE action is auto-executed with no human — that's the autonomy;
  (b) if risky[] is EMPTY -> continue straight to verification + postmortem and
      return a RESOLVED result with no pause — fully autonomous;
  (c) if risky[] is non-empty -> stop and surface them for human approve/deny —
      that's the governance.

Public API:
    run_until_approval(incident_id, chaos_config=None, on_stage=None) -> RunResult
        Triage -> diagnosis -> remediation, then auto-executes safe actions and
        either RESOLVES (no risky actions) or returns status="awaiting_approval"
        with the pending risky actions. The HTTP backend holds the returned
        RunResult in memory so the request never blocks on a human.

    resume_after_approval(result, decision, on_stage=None) -> RunResult
        Executes approved risky actions, then verification -> postmortem; returns
        a resolved RunResult. Only called when status was "awaiting_approval".

    run_incident(incident_id, chaos_config=None, approval_callback=None) -> RunResult
        CLI/eval convenience wrapper: runs to approval; if already resolved
        (autonomous path) returns it, otherwise applies a synchronous approval
        callback (auto-approves if none supplied) and resumes.

`on_stage(stage, artifact)` is an optional progress hook (used by the SSE stream in
Phase 9). It is called with each pydantic artifact as it is produced; default no-op.

Every incident-model binding routes through `llm_client`.
Confidence is computed deterministically from telemetry coverage, never by an LLM.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple

from crewai import Crew, Process, Task

from agents import (
    build_diagnosis_agent,
    build_postmortem_agent,
    build_remediation_agent,
    build_triage_agent,
    build_verification_agent,
)
from incidents import get_incident, load_rubric, observable
from llm_client import begin_model_run
from policy import load_policy
from schemas import (
    ApprovalDecision,
    DiagnosisReport,
    PostmortemReport,
    RemediationAction,
    RemediationPlan,
    RunResult,
    TriageReport,
    VerificationReport,
)

# Run-status values carried on RunResult.status.
STATUS_AWAITING = "awaiting_approval"
STATUS_RESOLVED = "resolved"

# Policy errors must stop the process during import rather than surfacing mid-incident.
POLICY = load_policy()

# ---------------------------------------------------------------------------
# Optional Track-B dependencies — no-op if not yet available
# ---------------------------------------------------------------------------
try:
    from audit import log_event as _log_event, init_db as _init_db
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

try:
    from chaos import apply_chaos as _apply_chaos
    _CHAOS_AVAILABLE = True
except ImportError:
    _CHAOS_AVAILABLE = False


def _log(run_id: str, stage: str, payload: dict) -> None:
    if _AUDIT_AVAILABLE:
        _log_event(run_id, stage, payload)


_NOOP_STAGE = lambda stage, artifact: None  # noqa: E731 — trivial default hook


# ---------------------------------------------------------------------------
# Confidence computed deterministically from telemetry coverage (never by LLM)
# ---------------------------------------------------------------------------
def _compute_confidence(telemetry: dict) -> Tuple[float, str]:
    confidence = 1.0
    missing = []
    if not telemetry.get("logs"):
        confidence -= 0.30
        missing.append("logs (-0.30)")
    if not telemetry.get("metrics"):
        confidence -= 0.40
        missing.append("metrics (-0.40)")
    if not telemetry.get("deploys"):
        confidence -= 0.20
        missing.append("deploys (-0.20)")
    confidence = round(max(0.0, confidence), 2)
    note = ("missing: " + ", ".join(missing)) if missing else "all telemetry sources present"
    return confidence, note


def _prepare_observable(incident_id: str, chaos_config: Optional[Dict[str, Any]]) -> dict:
    """Load the incident and apply chaos. Pure given (incident_id, chaos_config),
    so both phases reconstruct the same observable without passing it around."""
    obs = observable(get_incident(incident_id))
    if _CHAOS_AVAILABLE and chaos_config:
        try:
            obs = _apply_chaos(obs, chaos_config)
        except Exception:
            pass
    return obs


# ---------------------------------------------------------------------------
# Task prompt builders
# ---------------------------------------------------------------------------
def _triage_prompt(obs: dict, rubric: str) -> str:
    return (
        "A production alert has just fired. Classify it by severity and route it "
        "to the right specialist.\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        f"SEVERITY RUBRIC (single source of truth — classify strictly by this):\n{rubric}\n\n"
        "Pick the single best-fitting level and set `reason` to name the matched rule explicitly.\n"
        "Set route_to to \"Diagnosis\" unless this is a confirmed false alarm."
    )


def _diagnosis_prompt(obs: dict, confidence: float, coverage_note: str) -> str:
    return (
        "The Triage Engineer has classified this incident — see context above. "
        "Your job is to diagnose the root cause.\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        f"CONFIDENCE (pipeline-computed, read-only): {confidence:.2f}\n"
        f"  Basis: {coverage_note}\n"
        f"  You MUST set confidence to exactly {confidence:.2f} — do not change it.\n\n"
        "Output requirements:\n"
        "  root_cause   — one precise sentence naming the specific failure cause\n"
        "  cited_evidence — list the exact telemetry keys and values that support your diagnosis\n"
        f"  confidence   — {confidence:.2f} (this exact value)\n"
        "  reasoning    — narrative connecting the evidence to the root cause"
    )


def _remediation_prompt(obs: dict, diagnosis: dict) -> str:
    return (
        "An incident has been diagnosed. Produce a remediation plan that directly addresses "
        "the confirmed root cause.\n\n"
        f"CONFIRMED DIAGNOSIS:\n{json.dumps(diagnosis, indent=2)}\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        "Split your actions into two lists:\n"
        "  safe[]  — non-destructive, easily reversible (config tweaks, scaling, adding alerts, "
        "re-enabling a flag). These execute immediately without approval.\n"
        "  risky[] — destructive or hard to reverse (rolling back a deploy, restarting/deleting "
        "resources, failing over, rotating credentials, changing data). These require human approval.\n\n"
        "For EACH action provide: action (imperative), rationale (tie it to the root cause), "
        "and destructive (true for risky, false for safe).\n"
        "Include ONLY the actions you are actually executing now to resolve THIS incident. Do NOT add "
        "speculative, contingency, or 'if the safe fix doesn't work then…' fallback actions — those do "
        "not belong in the plan. An action is risky only if the real remediation genuinely requires a "
        "destructive or irreversible step. If safe, reversible actions fully resolve the incident, then "
        "risky[] MUST be empty — never manufacture risky actions to look thorough.\n"
        "Prefer the least-destructive action that fixes the root cause. Every action must be specific "
        "to THIS incident — no generic boilerplate."
    )


def _verification_prompt(obs: dict, diagnosis: dict, remediation: dict, approval: dict) -> str:
    return (
        "Remediation has been proposed and an approval decision made. Decide whether the incident "
        "recovers.\n\n"
        f"DIAGNOSIS:\n{json.dumps(diagnosis, indent=2)}\n\n"
        f"REMEDIATION PLAN:\n{json.dumps(remediation, indent=2)}\n\n"
        f"APPROVAL DECISION (risky actions approved = {approval.get('approved')}):\n"
        f"{json.dumps(approval, indent=2)}\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        "Report a verification result:\n"
        "  metric_name   — the single key metric that proves recovery for THIS incident "
        "(choose from the telemetry/alert)\n"
        "  threshold     — the value the metric must beat to be healthy (from the alert/telemetry)\n"
        "  observed_value— the PROJECTED value of that metric after the APPROVED actions are applied\n"
        "  recovered     — true only if the approved actions are sufficient to cross the threshold. "
        "If the real fix is a risky action that was NOT approved, recovered must be false.\n"
        "  note          — one line; state explicitly this is a projected post-remediation check over "
        "simulated telemetry, not a live re-measurement.\n"
        "metric_name must be a string; threshold and observed_value must be numbers."
    )


def _postmortem_prompt(
    obs: dict, triage: dict, diagnosis: dict, remediation: dict, approval: dict, verification: dict
) -> str:
    return (
        "The incident response is complete. Write a blameless postmortem from the artifacts below.\n\n"
        f"TRIAGE:\n{json.dumps(triage, indent=2)}\n\n"
        f"DIAGNOSIS:\n{json.dumps(diagnosis, indent=2)}\n\n"
        f"REMEDIATION PLAN:\n{json.dumps(remediation, indent=2)}\n\n"
        f"APPROVAL DECISION:\n{json.dumps(approval, indent=2)}\n\n"
        f"VERIFICATION:\n{json.dumps(verification, indent=2)}\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        "Produce:\n"
        "  summary       — one-paragraph executive summary of what happened and the outcome\n"
        "  timeline      — ordered events with timestamps drawn from the logs and deploys\n"
        "  root_cause    — the confirmed root cause\n"
        "  actions_taken — actions actually applied: ALL safe actions, plus risky actions ONLY if "
        "the approval decision approved them\n"
        "  follow_ups    — specific preventive measures to stop recurrence"
    )


# ---------------------------------------------------------------------------
# Crew runners — each stage is a sequential single-/dual-agent crew
# ---------------------------------------------------------------------------
def _run_single_agent(agent, description: str, expected_output: str, output_pydantic):
    """Run one agent as a single-task sequential crew; return its parsed pydantic output (or None)."""
    task = Task(
        description=description,
        expected_output=expected_output,
        agent=agent,
        output_pydantic=output_pydantic,
    )
    result = Crew(
        agents=[agent], tasks=[task], process=Process.sequential, verbose=True
    ).kickoff()
    return getattr(result.tasks_output[0], "pydantic", None)


def _run_triage_diagnosis(
    obs: dict, rubric: str, confidence: float, coverage_note: str
) -> Tuple[TriageReport, DiagnosisReport]:
    triage_agent = build_triage_agent(rubric=rubric)
    diagnosis_agent = build_diagnosis_agent()

    triage_task = Task(
        description=_triage_prompt(obs, rubric),
        expected_output="Structured triage report classifying this incident.",
        agent=triage_agent,
        output_pydantic=TriageReport,
    )
    diagnosis_task = Task(
        description=_diagnosis_prompt(obs, confidence, coverage_note),
        expected_output="Structured diagnosis report identifying the root cause.",
        agent=diagnosis_agent,
        output_pydantic=DiagnosisReport,
        context=[triage_task],
    )

    result = Crew(
        agents=[triage_agent, diagnosis_agent],
        tasks=[triage_task, diagnosis_task],
        process=Process.sequential,
        verbose=True,
    ).kickoff()

    triage = getattr(result.tasks_output[0], "pydantic", None) or TriageReport(
        severity="SEV-2",
        customer_facing=True,
        summary="(parse error — see crew logs)",
        route_to="Diagnosis",
        reason="parse error",
    )
    raw_diag = getattr(result.tasks_output[1], "pydantic", None) or DiagnosisReport(
        root_cause="(parse error — see crew logs)",
        cited_evidence=[],
        confidence=confidence,
        reasoning="parse error",
    )
    # Override confidence with the deterministic pipeline value — never the LLM's number.
    diagnosis = raw_diag.model_copy(update={"confidence": confidence})
    return triage, diagnosis


# ---------------------------------------------------------------------------
# Parse-error fallbacks — generic and labelled, never incident-specific canned
# answers, so a parse failure can't masquerade as a real result.
# ---------------------------------------------------------------------------
def _fallback_plan() -> RemediationPlan:
    return RemediationPlan(
        safe=[
            RemediationAction(
                action="Escalate to on-call owner for manual remediation",
                rationale="Remediation agent output could not be parsed — see crew logs",
                destructive=False,
            )
        ],
        risky=[],
    )


def _fallback_verification() -> VerificationReport:
    return VerificationReport(
        recovered=False,
        metric_name="unknown",
        observed_value=0.0,
        threshold=0.0,
        note="(parse error — verification agent output could not be parsed; see crew logs)",
    )


def _fallback_postmortem(root_cause: str) -> PostmortemReport:
    return PostmortemReport(
        summary="(parse error — postmortem agent output could not be parsed; see crew logs)",
        timeline=["See audit log for the ordered stage events"],
        root_cause=root_cause or "unknown",
        actions_taken=["See remediation and approval artifacts"],
        follow_ups=["Re-run the postmortem stage"],
    )


# ---------------------------------------------------------------------------
# Simulated action execution. Per the hard constraints there are no real cloud
# integrations — "executing" an ops/runbook action means recording it to the
# audit trail and surfacing it via on_stage. Safe actions run automatically;
# risky ones only after approval.
# ---------------------------------------------------------------------------
def _execute_actions(
    run_id: str,
    actions: list[RemediationAction],
    kind: str,
    on_stage: Callable[[str, Any], None],
) -> list[RemediationAction]:
    for action in actions:
        _log(run_id, f"execute_{kind}", action.model_dump())
    on_stage(f"executed_{kind}", actions)
    return list(actions)


# ---------------------------------------------------------------------------
# Shared tail: verification -> postmortem. Used by both the autonomous-resolve
# path (no risky actions) and the resume-after-approval path.
# ---------------------------------------------------------------------------
def _run_verification_postmortem(
    run_id: str,
    obs: dict,
    triage: TriageReport,
    diagnosis: DiagnosisReport,
    plan: RemediationPlan,
    decision: ApprovalDecision,
    on_stage: Callable[[str, Any], None],
) -> Tuple[VerificationReport, PostmortemReport]:
    diagnosis_d = diagnosis.model_dump()
    remediation_d = plan.model_dump()
    approval_d = decision.model_dump()

    verification = (
        _run_single_agent(
            build_verification_agent(),
            _verification_prompt(obs, diagnosis_d, remediation_d, approval_d),
            "A verification report stating the recovery metric, threshold, projected value, and recovered flag.",
            VerificationReport,
        )
        or _fallback_verification()
    )
    _log(run_id, "verification", verification.model_dump())
    on_stage("verification", verification)

    postmortem = (
        _run_single_agent(
            build_postmortem_agent(),
            _postmortem_prompt(
                obs, triage.model_dump(), diagnosis_d, remediation_d,
                approval_d, verification.model_dump(),
            ),
            "A blameless postmortem with summary, timeline, root_cause, actions_taken, and follow_ups.",
            PostmortemReport,
        )
        or _fallback_postmortem(diagnosis_d.get("root_cause", ""))
    )
    _log(run_id, "postmortem", postmortem.model_dump())
    on_stage("postmortem", postmortem)
    return verification, postmortem


# ---------------------------------------------------------------------------
# Phase 1 — triage -> diagnosis -> remediation -> auto-execute safe; then either
# resolve autonomously (no risky actions) or stop awaiting human approval.
# ---------------------------------------------------------------------------
def run_until_approval(
    incident_id: str,
    chaos_config: Optional[Dict[str, Any]] = None,
    on_stage: Optional[Callable[[str, Any], None]] = None,
) -> RunResult:
    on_stage = on_stage or _NOOP_STAGE
    run_id = str(uuid.uuid4())

    if _AUDIT_AVAILABLE:
        _init_db()  # idempotent, per contract

    obs = _prepare_observable(incident_id, chaos_config)
    rubric = load_rubric()
    confidence, coverage_note = _compute_confidence(obs["telemetry"])
    begin_model_run(
        incident_id,
        force_primary_failure=bool(
            chaos_config and chaos_config.get("break_primary_model")
        ),
    )

    _log(run_id, "start", {"incident_id": incident_id, "chaos_config": chaos_config})

    triage, diagnosis = _run_triage_diagnosis(
        obs, rubric, confidence, coverage_note
    )
    _log(run_id, "triage", triage.model_dump())
    on_stage("triage", triage)
    _log(run_id, "diagnosis", diagnosis.model_dump())
    on_stage("diagnosis", diagnosis)

    plan = (
        _run_single_agent(
            build_remediation_agent(),
            _remediation_prompt(obs, diagnosis.model_dump()),
            "A remediation plan with safe[] and risky[] actions addressing the root cause.",
            RemediationPlan,
        )
        or _fallback_plan()
    )
    _log(run_id, "remediation", plan.model_dump())
    on_stage("remediation", plan)

    # (a) Auto-execute every safe action — no human in the loop. That's the autonomy.
    executed_safe = _execute_actions(run_id, plan.safe, "safe", on_stage)

    result = RunResult(
        run_id=run_id,
        incident_id=incident_id,
        status=STATUS_AWAITING,
        triage=triage,
        diagnosis=diagnosis,
        remediation=plan,
        executed_safe=executed_safe,
        chaos_config=chaos_config,
    )

    # (b) No risky actions -> resolve autonomously, no pause.
    if not plan.risky:
        decision = ApprovalDecision(
            approved=True,
            approver="auto",
            note="No risky actions proposed; resolved autonomously",
        )
        _log(run_id, "approval", decision.model_dump())
        on_stage("approval", decision)
        verification, postmortem = _run_verification_postmortem(
            run_id, obs, triage, diagnosis, plan, decision, on_stage
        )
        _log(run_id, "complete", {"status": STATUS_RESOLVED, "recovered": verification.recovered})
        return result.model_copy(update={
            "status": STATUS_RESOLVED,
            "approval": decision,
            "verification": verification,
            "postmortem": postmortem,
        })

    # (c) Risky actions present -> stop and surface them for a human decision.
    _log(run_id, "awaiting_approval", {"risky_count": len(plan.risky)})
    return result


# ---------------------------------------------------------------------------
# Phase 2 — apply the human decision, execute approved risky actions, then
# verification -> postmortem. Only called when status was "awaiting_approval".
# ---------------------------------------------------------------------------
def resume_after_approval(
    result: RunResult,
    decision: ApprovalDecision,
    on_stage: Optional[Callable[[str, Any], None]] = None,
) -> RunResult:
    on_stage = on_stage or _NOOP_STAGE
    run_id = result.run_id

    _log(run_id, "approval", decision.model_dump())
    on_stage("approval", decision)

    # Reconstruct the same observable the agents saw in phase 1 (pure transform).
    obs = _prepare_observable(result.incident_id, result.chaos_config)
    begin_model_run(
        result.incident_id,
        force_primary_failure=bool(
            result.chaos_config
            and result.chaos_config.get("break_primary_model")
        ),
    )

    # Execute approved risky actions (simulated); skip them entirely on denial.
    if decision.approved:
        _execute_actions(run_id, result.remediation.risky, "risky", on_stage)

    verification, postmortem = _run_verification_postmortem(
        run_id, obs, result.triage, result.diagnosis, result.remediation,
        decision, on_stage,
    )
    _log(run_id, "complete", {"status": STATUS_RESOLVED, "recovered": verification.recovered})

    return result.model_copy(update={
        "status": STATUS_RESOLVED,
        "approval": decision,
        "verification": verification,
        "postmortem": postmortem,
    })


# ---------------------------------------------------------------------------
# CLI / eval convenience wrapper — autonomous when possible, else auto-approve
# ---------------------------------------------------------------------------
def run_incident(
    incident_id: str,
    chaos_config: Optional[Dict[str, Any]] = None,
    approval_callback: Optional[Callable[[RemediationPlan], ApprovalDecision]] = None,
) -> RunResult:
    """Run the full pipeline end-to-end. If remediation produces no risky actions
    the run resolves autonomously. Otherwise `approval_callback` is called with the
    RemediationPlan; if None, risky actions are auto-approved."""
    result = run_until_approval(incident_id, chaos_config)
    if result.status == STATUS_RESOLVED:
        return result  # fully autonomous — no risky actions to decide on

    if approval_callback is not None:
        decision = approval_callback(result.remediation)
    else:
        decision = ApprovalDecision(
            approved=True,
            approver="auto-cli",
            note="No approval_callback supplied; auto-approved per contract",
        )

    return resume_after_approval(result, decision)

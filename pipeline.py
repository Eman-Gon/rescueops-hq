"""Incident response pipeline — a Commander-driven state machine over sequential
CrewAI crews, parameterized by policy.json (ARCHITECTURE §3.2 / §9 phase A4).

Control flow, driven by `state_machine.IncidentStateMachine`:
  Triage -> Commander decides fast_path (skip diagnosis) vs deep_diagnosis.
  [Diagnosis ->] Commander decides dispatch_remediation vs escalate_to_human.
  Remediation -> code (not the Commander) forces request_approval whenever a risky
    action is proposed; safe actions always auto-execute first — that's the autonomy.
  Verification -> on failure, the Commander decides retry_remediation (bounded by the
    policy's retry cap) vs escalate; a successful verification proceeds to postmortem.
  Illegal Commander output, at any decision point, falls back to the policy's
  deterministic default and is recorded as a `commander_overruled` event — the
  Commander never free-routes (ARCHITECTURE §3.2).

Public API:
    run_until_approval(incident_id, chaos_config=None, on_stage=None) -> RunResult
        Runs from triage through to one of: RESOLVED (no risky actions anywhere),
        ESCALATED (Commander escalated from diagnosis, or verification exhausted its
        retries), or "awaiting_approval" with pending risky actions. The HTTP backend
        holds the returned RunResult in memory so the request never blocks on a human.

    resume_after_approval(result, decision, on_stage=None) -> RunResult
        Reconstructs the paused IncidentStateMachine from `result.state_snapshot`,
        applies the human decision, executes approved risky actions, then continues
        the same verification/retry/postmortem tail as the autonomous path. Only
        called when status was "awaiting_approval".

    run_incident(incident_id, chaos_config=None, approval_callback=None) -> RunResult
        CLI/eval convenience wrapper: runs to approval; if already resolved or
        escalated (no approval needed) returns it, otherwise applies a synchronous
        approval callback (auto-approves if none supplied) and resumes.

`on_stage(stage, artifact)` is an optional progress hook (used by the SSE stream in
Phase 9). It is called with each pydantic artifact as it is produced; default no-op.

Every incident-model binding routes through `llm_client`.
Confidence is computed deterministically from telemetry coverage, never by an LLM.

Paused-run resume is in-memory only via `RunResult.state_snapshot` for now — durable
cross-process persistence into Makers context.store is deferred pending Track B's
Phase-0 recon (ARCHITECTURE §7); see TRACK-A.md A4.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple

from crewai import Crew, Process, Task

from agents import (
    build_commander_agent,
    build_diagnosis_agent,
    build_postmortem_agent,
    build_remediation_agent,
    build_triage_agent,
    build_verification_agent,
)
from events import append_event
from incidents import get_incident, load_rubric, observable
from llm_client import begin_model_run
from policy import load_policy
from schemas import (
    ApprovalDecision,
    CommanderDecision,
    DiagnosisReport,
    PostmortemReport,
    RemediationAction,
    RemediationPlan,
    RunResult,
    TriageReport,
    VerificationReport,
)
from state_machine import IncidentStateMachine

# Run-status values carried on RunResult.status.
STATUS_AWAITING = "awaiting_approval"
STATUS_RESOLVED = "resolved"
STATUS_ESCALATED = "escalated"

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


def _commander_prompt(context: dict) -> str:
    return (
        "You are the Incident Commander. The state machine below is the sole authority "
        "on what you may choose — pick exactly one move from LEGAL MOVES and explain "
        "your choice in one sentence. Never invent a move outside that list.\n\n"
        f"CURRENT STATE: {context['current_state']}\n"
        f"LEGAL MOVES: {context['legal_moves']}\n\n"
        f"LATEST SPECIALIST OUTPUT:\n{json.dumps(context['latest_specialist_output'], indent=2)}"
    )


# ---------------------------------------------------------------------------
# Crew runners — each stage is a single-agent sequential crew
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


def _fallback_commander_decision() -> CommanderDecision:
    # A deliberately illegal move: it flows through IncidentStateMachine.apply_move's
    # existing illegal-move -> policy-default -> commander_overruled path, so a parse
    # failure gets an honest event trail instead of silently taking the default.
    return CommanderDecision(
        move="__parse_error__",
        rationale="Commander agent output could not be parsed; see crew logs",
    )


# ---------------------------------------------------------------------------
# Specialist + Commander seams — kept small and individually monkeypatchable so
# pipeline control-flow tests never need to mock CrewAI/LLM internals.
# ---------------------------------------------------------------------------
def _run_triage(obs: dict, rubric: str) -> TriageReport:
    return (
        _run_single_agent(
            build_triage_agent(rubric=rubric),
            _triage_prompt(obs, rubric),
            "Structured triage report classifying this incident.",
            TriageReport,
        )
        or TriageReport(
            severity="SEV-2",
            customer_facing=True,
            summary="(parse error — see crew logs)",
            route_to="Diagnosis",
            reason="parse error",
        )
    )


def _run_diagnosis(obs: dict, confidence: float, coverage_note: str) -> DiagnosisReport:
    raw = _run_single_agent(
        build_diagnosis_agent(),
        _diagnosis_prompt(obs, confidence, coverage_note),
        "Structured diagnosis report identifying the root cause.",
        DiagnosisReport,
    ) or DiagnosisReport(
        root_cause="(parse error — see crew logs)",
        cited_evidence=[],
        confidence=confidence,
        reasoning="parse error",
    )
    # Override confidence with the deterministic pipeline value — never the LLM's number.
    return raw.model_copy(update={"confidence": confidence})


def _run_remediation(obs: dict, diagnosis_d: dict) -> RemediationPlan:
    return (
        _run_single_agent(
            build_remediation_agent(),
            _remediation_prompt(obs, diagnosis_d),
            "A remediation plan with safe[] and risky[] actions addressing the root cause.",
            RemediationPlan,
        )
        or _fallback_plan()
    )


def _run_verification(
    obs: dict, diagnosis_d: dict, remediation_d: dict, approval_d: dict
) -> VerificationReport:
    return (
        _run_single_agent(
            build_verification_agent(),
            _verification_prompt(obs, diagnosis_d, remediation_d, approval_d),
            "A verification report stating the recovery metric, threshold, projected value, and recovered flag.",
            VerificationReport,
        )
        or _fallback_verification()
    )


def _run_postmortem(
    obs: dict,
    triage_d: dict,
    diagnosis_d: dict,
    remediation_d: dict,
    approval_d: dict,
    verification_d: dict,
) -> PostmortemReport:
    return (
        _run_single_agent(
            build_postmortem_agent(),
            _postmortem_prompt(obs, triage_d, diagnosis_d, remediation_d, approval_d, verification_d),
            "A blameless postmortem with summary, timeline, root_cause, actions_taken, and follow_ups.",
            PostmortemReport,
        )
        or _fallback_postmortem(diagnosis_d.get("root_cause", ""))
    )


def _get_commander_decision(context: dict) -> CommanderDecision:
    return (
        _run_single_agent(
            build_commander_agent(),
            _commander_prompt(context),
            "A CommanderDecision naming exactly one legal move and a one-sentence rationale.",
            CommanderDecision,
        )
        or _fallback_commander_decision()
    )


# ---------------------------------------------------------------------------
# Simulated action execution. Per the hard constraints there are no real cloud
# integrations — "executing" an ops/runbook action means recording it to the
# audit trail and the event log. Safe actions run automatically; risky ones
# only after approval.
# ---------------------------------------------------------------------------
def _execute_actions(
    run_id: str,
    incident_id: str,
    actions: list[RemediationAction],
    kind: str,
    on_stage: Callable[[str, Any], None],
) -> list[RemediationAction]:
    for action in actions:
        _log(run_id, f"execute_{kind}", action.model_dump())
        append_event(
            incident_id=incident_id,
            actor="remediation",
            event_type="action_executed",
            payload={
                "summary": action.action,
                "destructive": action.destructive,
                "kind": kind,
            },
        )
    on_stage(f"executed_{kind}", actions)
    return list(actions)


# ---------------------------------------------------------------------------
# Shared tail: from "verification" through the bounded retry loop to postmortem
# (or escalation). Precondition: machine.current_state == "verification". Used by
# both the autonomous-resolve path (no risky actions) and resume_after_approval.
# ---------------------------------------------------------------------------
def _advance_from_verification(
    machine: IncidentStateMachine,
    run_id: str,
    incident_id: str,
    obs: dict,
    triage: TriageReport,
    diagnosis: Optional[DiagnosisReport],
    plan: RemediationPlan,
    executed_safe: list[RemediationAction],
    decision: ApprovalDecision,
    chaos_config: Optional[Dict[str, Any]],
    on_stage: Callable[[str, Any], None],
) -> RunResult:
    diagnosis_d = diagnosis.model_dump() if diagnosis else {}

    while True:
        _log(run_id, "approval", decision.model_dump())
        on_stage("approval", decision)

        remediation_d = plan.model_dump()
        approval_d = decision.model_dump()
        verification = _run_verification(obs, diagnosis_d, remediation_d, approval_d)
        _log(run_id, "verification", verification.model_dump())
        on_stage("verification", verification)

        if verification.recovered:
            machine.after_verification(True)
            break  # -> postmortem, outside the loop

        # Failed: the Commander owns retry_remediation vs escalate (policy.json
        # "verification_decision", commander_decides=true). The machine only enters
        # that state formally inside after_verification, so the legal moves are
        # taken directly from the loaded policy rather than machine.commander_context.
        vd_context = {
            "current_state": "verification_decision",
            "legal_moves": list(POLICY.states["verification_decision"].transitions),
            "latest_specialist_output": verification.model_dump(),
        }
        retry_decision = _get_commander_decision(vd_context)
        move = machine.after_verification(False, retry_decision)

        if move == "escalate":
            return RunResult(
                run_id=run_id,
                incident_id=incident_id,
                status=STATUS_ESCALATED,
                triage=triage,
                diagnosis=diagnosis,
                remediation=plan,
                executed_safe=executed_safe,
                approval=decision,
                verification=verification,
                postmortem=None,
                chaos_config=chaos_config,
                state_snapshot=machine.to_json(),
            )

        # move == "retry_remediation": current_state is now "remediation" — produce a
        # fresh plan and re-execute safe actions before verifying again.
        plan = _run_remediation(obs, diagnosis_d)
        _log(run_id, "remediation", plan.model_dump())
        on_stage("remediation", plan)
        append_event(
            incident_id=incident_id,
            actor="remediation",
            event_type="action_proposed",
            payload={
                "summary": f"Proposed {len(plan.safe)} safe and {len(plan.risky)} risky action(s)."
            },
        )
        executed_safe = _execute_actions(run_id, incident_id, plan.safe, "safe", on_stage)

        action_classes = (["safe"] if plan.safe else []) + (["risky"] if plan.risky else [])
        remediation_move = machine.after_remediation(action_classes)
        if remediation_move == "request_approval":
            return RunResult(
                run_id=run_id,
                incident_id=incident_id,
                status=STATUS_AWAITING,
                triage=triage,
                diagnosis=diagnosis,
                remediation=plan,
                executed_safe=executed_safe,
                chaos_config=chaos_config,
                state_snapshot=machine.to_json(),
            )

        # remediation_move == "dispatch_verification": no risky actions on the retry.
        decision = ApprovalDecision(
            approved=True,
            approver="auto",
            note="No risky actions proposed; resolved autonomously",
        )

    postmortem = _run_postmortem(
        obs,
        triage.model_dump(),
        diagnosis_d,
        plan.model_dump(),
        decision.model_dump(),
        verification.model_dump(),
    )
    _log(run_id, "postmortem", postmortem.model_dump())
    on_stage("postmortem", postmortem)
    machine.after_postmortem()
    _log(run_id, "complete", {"status": STATUS_RESOLVED, "recovered": verification.recovered})

    return RunResult(
        run_id=run_id,
        incident_id=incident_id,
        status=STATUS_RESOLVED,
        triage=triage,
        diagnosis=diagnosis,
        remediation=plan,
        executed_safe=executed_safe,
        approval=decision,
        verification=verification,
        postmortem=postmortem,
        chaos_config=chaos_config,
        state_snapshot=machine.to_json(),
    )


# ---------------------------------------------------------------------------
# Phase 1 — triage -> [diagnosis] -> remediation -> auto-execute safe; then either
# resolve autonomously, escalate, or stop awaiting human approval.
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

    machine = IncidentStateMachine(incident_id)
    machine.start()  # -> triage; emits incident_opened

    triage = _run_triage(obs, rubric)
    _log(run_id, "triage", triage.model_dump())
    on_stage("triage", triage)
    append_event(
        incident_id=incident_id,
        actor="triage",
        event_type="finding",
        payload={"summary": triage.summary},
    )

    triage_decision = _get_commander_decision(
        machine.commander_context(triage.model_dump())
    )
    move = machine.after_triage(triage.severity, triage_decision)

    diagnosis: Optional[DiagnosisReport] = None
    if move == "deep_diagnosis":
        diagnosis = _run_diagnosis(obs, confidence, coverage_note)
        _log(run_id, "diagnosis", diagnosis.model_dump())
        on_stage("diagnosis", diagnosis)
        append_event(
            incident_id=incident_id,
            actor="diagnosis",
            event_type="finding",
            payload={"summary": f"Root cause: {diagnosis.root_cause}"},
        )

        diagnosis_decision = _get_commander_decision(
            machine.commander_context(diagnosis.model_dump())
        )
        move = machine.after_diagnosis(diagnosis_decision)

        if move == "escalate_to_human":
            _log(run_id, "escalated", {"reason": "diagnosis escalation"})
            return RunResult(
                run_id=run_id,
                incident_id=incident_id,
                status=STATUS_ESCALATED,
                triage=triage,
                diagnosis=diagnosis,
                remediation=None,
                executed_safe=[],
                chaos_config=chaos_config,
                state_snapshot=machine.to_json(),
            )

    # move is now "dispatch_remediation" (from diagnosis) or "fast_path" (SEV-3).
    diagnosis_d = diagnosis.model_dump() if diagnosis else {}
    plan = _run_remediation(obs, diagnosis_d)
    _log(run_id, "remediation", plan.model_dump())
    on_stage("remediation", plan)
    append_event(
        incident_id=incident_id,
        actor="remediation",
        event_type="action_proposed",
        payload={
            "summary": f"Proposed {len(plan.safe)} safe and {len(plan.risky)} risky action(s)."
        },
    )

    # (a) Auto-execute every safe action — no human in the loop. That's the autonomy.
    executed_safe = _execute_actions(run_id, incident_id, plan.safe, "safe", on_stage)

    action_classes = (["safe"] if plan.safe else []) + (["risky"] if plan.risky else [])
    remediation_move = machine.after_remediation(action_classes)

    # (c) Risky actions present -> code forces request_approval; stop and surface them.
    if remediation_move == "request_approval":
        return RunResult(
            run_id=run_id,
            incident_id=incident_id,
            status=STATUS_AWAITING,
            triage=triage,
            diagnosis=diagnosis,
            remediation=plan,
            executed_safe=executed_safe,
            chaos_config=chaos_config,
            state_snapshot=machine.to_json(),
        )

    # (b) No risky actions -> resolve autonomously, no pause.
    decision = ApprovalDecision(
        approved=True,
        approver="auto",
        note="No risky actions proposed; resolved autonomously",
    )
    return _advance_from_verification(
        machine, run_id, incident_id, obs, triage, diagnosis, plan,
        executed_safe, decision, chaos_config, on_stage,
    )


# ---------------------------------------------------------------------------
# Phase 2 — apply the human decision, execute approved risky actions, then continue
# the shared verification/retry/postmortem tail. Only called when status was
# "awaiting_approval".
# ---------------------------------------------------------------------------
def resume_after_approval(
    result: RunResult,
    decision: ApprovalDecision,
    on_stage: Optional[Callable[[str, Any], None]] = None,
) -> RunResult:
    on_stage = on_stage or _NOOP_STAGE
    run_id = result.run_id
    incident_id = result.incident_id

    machine = IncidentStateMachine.from_json(result.state_snapshot)
    machine.after_approval(decision.approved)  # -> verification; emits approval_granted/denied

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
        _execute_actions(run_id, incident_id, result.remediation.risky, "risky", on_stage)

    return _advance_from_verification(
        machine, run_id, incident_id, obs, result.triage, result.diagnosis,
        result.remediation, list(result.executed_safe), decision,
        result.chaos_config, on_stage,
    )


# ---------------------------------------------------------------------------
# CLI / eval convenience wrapper — autonomous when possible, else auto-approve
# ---------------------------------------------------------------------------
def run_incident(
    incident_id: str,
    chaos_config: Optional[Dict[str, Any]] = None,
    approval_callback: Optional[Callable[[RemediationPlan], ApprovalDecision]] = None,
) -> RunResult:
    """Run the full pipeline end-to-end. If the run resolves or escalates without
    ever pausing, that result is returned directly. Otherwise `approval_callback` is
    called with the RemediationPlan; if None, risky actions are auto-approved."""
    result = run_until_approval(incident_id, chaos_config)
    if result.status != STATUS_AWAITING:
        return result  # resolved or escalated — nothing to approve

    if approval_callback is not None:
        decision = approval_callback(result.remediation)
    else:
        decision = ApprovalDecision(
            approved=True,
            approver="auto-cli",
            note="No approval_callback supplied; auto-approved per contract",
        )

    return resume_after_approval(result, decision)

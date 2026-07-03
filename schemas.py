"""Structured artifacts each agent emits into the incident timeline.

Every stage produces a distinct, typed artifact — this file is the complete
integration contract between Track A (agents) and Track B (UI/audit/chaos).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TriageReport(BaseModel):
    severity: str = Field(description="One of: SEV-1 (highest), SEV-2, SEV-3")
    customer_facing: bool = Field(description="True if end users are affected")
    summary: str = Field(description="One-line description of what is happening")
    route_to: str = Field(description="Which specialist handles this next, e.g. 'Diagnosis'")
    reason: str = Field(description="Why this severity and routing")


class CommanderDecision(BaseModel):
    move: str = Field(description="One of the legal moves supplied by the state machine")
    rationale: str = Field(
        min_length=1,
        description="One human-readable sentence explaining the move",
    )


class DiagnosisReport(BaseModel):
    root_cause: str = Field(description="One-sentence root-cause statement")
    cited_evidence: list[str] = Field(description="Telemetry keys / values that support the diagnosis")
    confidence: float = Field(description="0.0–1.0; computed deterministically from telemetry coverage, not by LLM")
    reasoning: str = Field(description="Narrative connecting evidence to root cause")


class RemediationAction(BaseModel):
    action: str = Field(description="Imperative description of what to do")
    rationale: str = Field(description="Why this action addresses the root cause")
    destructive: bool = Field(description="True if the action is hard to reverse (rollback, restart, etc.)")


class RemediationPlan(BaseModel):
    safe: list[RemediationAction] = Field(description="Non-destructive actions; execute without approval gate")
    risky: list[RemediationAction] = Field(description="Destructive actions; require approval before execution")


class ApprovalDecision(BaseModel):
    approved: bool = Field(description="Whether the risky actions are approved to execute")
    approver: str = Field(description="Who or what approved: 'human-ui' | 'auto-cli' | 'auto-reject'")
    note: str = Field(description="Optional human-readable justification")


class VerificationReport(BaseModel):
    recovered: bool = Field(description="True if the incident signal returned to normal")
    metric_name: str = Field(description="The key metric checked post-remediation")
    observed_value: float = Field(description="Metric value at verification time")
    threshold: float = Field(description="The recovery threshold the metric must beat")
    note: str = Field(description="Any additional context about the recovery check")


class PostmortemReport(BaseModel):
    summary: str = Field(description="Executive one-paragraph summary")
    timeline: list[str] = Field(description="Ordered list of timestamped events")
    root_cause: str = Field(description="Confirmed root cause (may refine DiagnosisReport)")
    actions_taken: list[str] = Field(description="Remediation steps that were executed")
    follow_ups: list[str] = Field(description="Action items to prevent recurrence")


class RunResult(BaseModel):
    """The full state of an incident run at whatever stage it has reached.

    The Commander, constrained by the policy-parameterized state machine, drives a
    run to one of three terminal/paused shapes:
      - status="resolved"          — fully done; verification + postmortem present.
                                      Reached AUTONOMOUSLY when remediation produced
                                      no risky actions, or after a human decides on
                                      the risky ones.
      - status="awaiting_approval" — safe actions have already been auto-executed
                                      (see `executed_safe`); one or more risky
                                      actions are pending a human decision.
                                      `approval`/`verification`/`postmortem` are null.
      - status="escalated"         — the Commander escalated to a human instead of
                                      routing onward: either straight from Diagnosis
                                      (low confidence; `remediation` is null because
                                      it never ran) or after Verification failed and
                                      the policy's retry cap was exhausted (`postmortem`
                                      stays null; nothing further runs automatically).
    `diagnosis` is null when the Commander fast-paths a SEV-3 incident (ARCHITECTURE
    §3.2: fast_path skips deep diagnosis entirely — no artifact is fabricated for it).
    """
    run_id: str = Field(description="UUID for this pipeline run")
    incident_id: str = Field(description="The incident that was processed")
    status: str = Field(description='"awaiting_approval" | "resolved" | "escalated"')
    triage: TriageReport
    diagnosis: Optional[DiagnosisReport] = Field(
        default=None, description="Null when the Commander fast-paths a SEV-3 incident"
    )
    remediation: Optional[RemediationPlan] = Field(
        default=None,
        description="Null when the Commander escalates straight from diagnosis (remediation never ran)",
    )
    executed_safe: list[RemediationAction] = Field(
        default_factory=list,
        description="Safe actions auto-executed without a human approval gate",
    )
    approval: Optional[ApprovalDecision] = Field(
        default=None,
        description="Null until a risky-action decision is made (auto when no risky actions)",
    )
    verification: Optional[VerificationReport] = Field(
        default=None, description="Null until the run is resolved or escalated post-verification"
    )
    postmortem: Optional[PostmortemReport] = Field(
        default=None, description="Null until the run is resolved"
    )
    chaos_config: Optional[Dict[str, Any]] = Field(default=None, description="Chaos parameters injected for this run, if any")
    state_snapshot: Optional[str] = Field(
        default=None,
        description=(
            "IncidentStateMachine.to_json() captured at pause/terminal, so "
            "resume_after_approval can reconstruct the exact machine (state + retry "
            "counts). In-memory only for now — not yet persisted to Makers storage; "
            "see ARCHITECTURE §7."
        ),
    )

"""Policy-parameterized incident state machine for offline and runtime use."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

from events import append_event
from policy import Policy, load_policy
from schemas import CommanderDecision


class MachineSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    current_state: str
    retry_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("retry_counts")
    @classmethod
    def validate_retry_counts(cls, value: dict[str, int]) -> dict[str, int]:
        if any(count < 0 for count in value.values()):
            raise ValueError("retry counts cannot be negative")
        return value


class IncidentStateMachine:
    """Apply Commander choices only after the loaded policy permits them."""

    def __init__(
        self,
        incident_id: str,
        policy: Policy | None = None,
        snapshot: MachineSnapshot | None = None,
    ) -> None:
        self.policy = policy or load_policy()
        self.snapshot = snapshot or MachineSnapshot(
            incident_id=incident_id,
            current_state=self.policy.initial_state,
        )
        if self.snapshot.incident_id != incident_id:
            raise ValueError("snapshot incident_id does not match requested incident")
        if self.snapshot.current_state not in self.policy.states:
            raise ValueError("snapshot contains a state absent from the loaded policy")

    @property
    def incident_id(self) -> str:
        return self.snapshot.incident_id

    @property
    def current_state(self) -> str:
        return self.snapshot.current_state

    def legal_moves(self) -> list[str]:
        return list(self.policy.states[self.current_state].transitions)

    def commander_context(self, latest_specialist_output: dict) -> dict:
        """Return the complete, deliberately scoped input for a Commander decision."""
        return {
            "current_state": self.current_state,
            "legal_moves": self.legal_moves(),
            "latest_specialist_output": latest_specialist_output,
        }

    def start(self) -> str:
        append_event(
            incident_id=self.incident_id,
            actor="system",
            event_type="incident_opened",
            payload={"summary": f"Incident {self.incident_id} opened."},
        )
        return self.apply_move(None)

    def apply_move(
        self,
        decision: CommanderDecision | None,
        *,
        forced_move: str | None = None,
        forced_reason: str | None = None,
    ) -> str:
        rule = self.policy.states[self.current_state]
        if rule.terminal:
            raise RuntimeError(f"cannot transition terminal state {self.current_state!r}")

        candidate = forced_move or (decision.move if decision else rule.default_move)
        rationale = forced_reason or (
            decision.rationale if decision else "Applied the policy default."
        )
        if candidate not in rule.transitions:
            fallback = rule.default_move
            append_event(
                incident_id=self.incident_id,
                actor="commander",
                event_type="commander_overruled",
                payload={
                    "summary": (
                        f"Illegal move {candidate!r} was replaced by policy default "
                        f"{fallback!r}."
                    ),
                    "state": self.current_state,
                    "requested_move": candidate,
                    "applied_move": fallback,
                },
            )
            candidate = fallback
        elif decision is not None:
            append_event(
                incident_id=self.incident_id,
                actor="commander",
                event_type="commander_decision",
                payload={
                    "summary": rationale.rstrip(".") + ".",
                    "state": self.current_state,
                    "move": candidate,
                },
            )

        self.snapshot.current_state = rule.transitions[candidate]
        return candidate

    def after_triage(
        self,
        severity: str,
        decision: CommanderDecision | None = None,
    ) -> str:
        if self.current_state != "triage":
            raise RuntimeError("after_triage requires the triage state")
        if decision is None and severity == "SEV-3":
            decision = CommanderDecision(
                move="fast_path",
                rationale="SEV-3 has no customer impact, so deep diagnosis is skipped",
            )
        return self.apply_move(decision)

    def after_remediation(
        self,
        action_classes: list[str],
        decision: CommanderDecision | None = None,
    ) -> str:
        if self.current_state != "remediation":
            raise RuntimeError("after_remediation requires the remediation state")
        forced = set(action_classes).intersection(
            self.policy.approval_forced_action_classes
        )
        if forced:
            if decision is not None and decision.move != "request_approval":
                append_event(
                    incident_id=self.incident_id,
                    actor="commander",
                    event_type="commander_overruled",
                    payload={
                        "summary": "Risk policy forced human approval for the proposed action.",
                        "state": self.current_state,
                        "requested_move": decision.move,
                        "applied_move": "request_approval",
                    },
                )
                decision = None
            move = self.apply_move(
                decision,
                forced_move="request_approval",
                forced_reason="Risk policy requires human approval.",
            )
            append_event(
                incident_id=self.incident_id,
                actor="system",
                event_type="approval_requested",
                payload={"summary": "Risky remediation is waiting for human approval."},
            )
            return move
        return self.apply_move(decision, forced_move="dispatch_verification")

    def after_approval(self, approved: bool) -> str:
        if self.current_state != "awaiting_approval":
            raise RuntimeError("after_approval requires the awaiting_approval state")
        move = "approval_granted" if approved else "approval_denied"
        self.apply_move(None, forced_move=move)
        append_event(
            incident_id=self.incident_id,
            actor="human",
            event_type=move,
            payload={
                "summary": (
                    "Human approved the risky remediation."
                    if approved
                    else "Human denied the risky remediation."
                ),
                "channel": "web",
            },
        )
        return move

    def after_verification(
        self,
        recovered: bool,
        decision: CommanderDecision | None = None,
    ) -> str:
        if self.current_state != "verification":
            raise RuntimeError("after_verification requires the verification state")
        if recovered:
            append_event(
                incident_id=self.incident_id,
                actor="verification",
                event_type="verification_passed",
                payload={"summary": "Recovery verification passed."},
            )
            return self.apply_move(None, forced_move="verification_passed")

        append_event(
            incident_id=self.incident_id,
            actor="verification",
            event_type="verification_failed",
            payload={"summary": "Recovery verification failed."},
        )
        self.apply_move(None, forced_move="verification_failed")
        cap = self.policy.retry_caps.get("verification", 0)
        retries = self.snapshot.retry_counts.get("verification", 0)
        requested = decision.move if decision else None

        if requested == "retry_remediation" and retries >= cap:
            append_event(
                incident_id=self.incident_id,
                actor="commander",
                event_type="commander_overruled",
                payload={
                    "summary": "Verification retry cap was reached; escalating the incident.",
                    "state": self.current_state,
                    "requested_move": requested,
                    "applied_move": "escalate",
                },
            )
            decision = None
            move = self.apply_move(None, forced_move="escalate")
        elif decision is None:
            move = "retry_remediation" if retries < cap else "escalate"
            move = self.apply_move(None, forced_move=move)
        else:
            move = self.apply_move(decision)

        if move == "retry_remediation":
            self.snapshot.retry_counts["verification"] = retries + 1
        return move

    def after_postmortem(self) -> str:
        if self.current_state != "postmortem":
            raise RuntimeError("after_postmortem requires the postmortem state")
        append_event(
            incident_id=self.incident_id,
            actor="postmortem",
            event_type="postmortem_ready",
            payload={"summary": "The incident postmortem is ready."},
        )
        move = self.apply_move(None, forced_move="resolve")
        append_event(
            incident_id=self.incident_id,
            actor="system",
            event_type="incident_resolved",
            payload={"summary": f"Incident {self.incident_id} resolved."},
        )
        return move

    def to_json(self) -> str:
        return self.snapshot.model_dump_json()

    @classmethod
    def from_json(
        cls,
        raw: str,
        policy: Policy | None = None,
    ) -> "IncidentStateMachine":
        snapshot = MachineSnapshot.model_validate(json.loads(raw))
        return cls(snapshot.incident_id, policy=policy, snapshot=snapshot)

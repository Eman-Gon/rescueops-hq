"""Validation and loading for the code-enforced RescueOps policy."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.json")


class PolicyValidationError(RuntimeError):
    """Raised when policy.json cannot safely drive the incident state machine."""


class StateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transitions: dict[str, str]
    default_move: str | None
    commander_decides: bool
    terminal: bool = False

    @model_validator(mode="after")
    def validate_default(self) -> "StateRule":
        if self.terminal:
            if self.transitions or self.default_move is not None:
                raise ValueError("terminal states cannot have transitions or a default_move")
        elif not self.transitions:
            raise ValueError("non-terminal states require at least one transition")
        elif self.default_move not in self.transitions:
            raise ValueError("default_move must name one of the state's transitions")
        return self


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    initial_state: str
    states: dict[str, StateRule]
    retry_caps: dict[str, int]
    approval_forced_action_classes: list[str]

    @model_validator(mode="after")
    def validate_graph(self) -> "Policy":
        required_transitions = {
            "opened": {"dispatch_triage"},
            "triage": {"fast_path", "deep_diagnosis"},
            "diagnosis": {"dispatch_remediation", "escalate_to_human"},
            "remediation": {"request_approval", "dispatch_verification"},
            "awaiting_approval": {"approval_granted", "approval_denied"},
            "verification": {"verification_passed", "verification_failed"},
            "verification_decision": {"retry_remediation", "escalate"},
            "postmortem": {"resolve"},
            "resolved": set(),
            "escalated": set(),
        }
        if self.initial_state not in self.states:
            raise ValueError("initial_state must exist in states")
        missing_states = set(required_transitions).difference(self.states)
        if missing_states:
            raise ValueError(
                f"policy is missing required states: {sorted(missing_states)}"
            )
        if not self.approval_forced_action_classes:
            raise ValueError("approval_forced_action_classes cannot be empty")
        if "verification" not in self.retry_caps:
            raise ValueError("retry_caps must define verification")
        for name, cap in self.retry_caps.items():
            if cap < 0:
                raise ValueError(f"retry cap {name!r} cannot be negative")
        for state_name, rule in self.states.items():
            required_moves = required_transitions.get(state_name, set())
            missing_moves = required_moves.difference(rule.transitions)
            if missing_moves:
                raise ValueError(
                    f"state {state_name!r} is missing required moves: "
                    f"{sorted(missing_moves)}"
                )
            for move, target in rule.transitions.items():
                if target not in self.states:
                    raise ValueError(
                        f"state {state_name!r} move {move!r} targets unknown state {target!r}"
                    )
        return self


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> Policy:
    """Load and validate a policy, refusing to continue on malformed input."""
    policy_path = Path(path)
    try:
        raw = json.loads(policy_path.read_text())
        return Policy.model_validate(raw)
    except Exception as error:
        raise PolicyValidationError(
            f"Invalid RescueOps policy at {policy_path}: {error}"
        ) from error

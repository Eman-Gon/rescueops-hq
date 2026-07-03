import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from events import append_event, clear_events, list_events
from policy import PolicyValidationError, load_policy
from schemas import CommanderDecision
from state_machine import IncidentStateMachine


def _machine(incident_id: str) -> IncidentStateMachine:
    clear_events(incident_id)
    machine = IncidentStateMachine(incident_id)
    assert machine.start() == "dispatch_triage"
    assert machine.current_state == "triage"
    return machine


def test_malformed_policy_fails_with_clear_error(tmp_path) -> None:
    malformed = tmp_path / "policy.json"
    malformed.write_text(
        json.dumps(
            {
                "version": 1,
                "initial_state": "missing",
                "states": {},
                "retry_caps": {},
                "approval_forced_action_classes": ["risky"],
            }
        )
    )

    with pytest.raises(PolicyValidationError, match="Invalid RescueOps policy"):
        load_policy(malformed)


def test_policy_rejects_unknown_fields_and_missing_runtime_moves(tmp_path) -> None:
    source = json.loads(open("policy.json").read())
    source["states"]["triage"]["surprise_typo"] = True
    malformed = tmp_path / "unknown-field.json"
    malformed.write_text(json.dumps(source))
    with pytest.raises(PolicyValidationError, match="extra_forbidden"):
        load_policy(malformed)

    source = json.loads(open("policy.json").read())
    del source["states"]["triage"]["transitions"]["fast_path"]
    malformed = tmp_path / "missing-move.json"
    malformed.write_text(json.dumps(source))
    with pytest.raises(PolicyValidationError, match="missing required moves"):
        load_policy(malformed)


def test_illegal_commander_move_uses_default_and_logs_overrule() -> None:
    machine = _machine("INC-ILLEGAL")
    move = machine.after_triage(
        "SEV-2",
        CommanderDecision(move="launch_missiles", rationale="Bad idea"),
    )

    assert move == "deep_diagnosis"
    assert machine.current_state == "diagnosis"
    events = list_events("INC-ILLEGAL")
    assert events[-1]["type"] == "commander_overruled"
    assert events[-1]["payload"]["applied_move"] == "deep_diagnosis"


def test_sev3_fast_paths_to_remediation() -> None:
    machine = _machine("INC-SEV3")

    context = machine.commander_context(
        {"severity": "SEV-3", "summary": "Internal alert only"}
    )
    assert context == {
        "current_state": "triage",
        "legal_moves": ["fast_path", "deep_diagnosis"],
        "latest_specialist_output": {
            "severity": "SEV-3",
            "summary": "Internal alert only",
        },
    }
    assert machine.after_triage("SEV-3") == "fast_path"
    assert machine.current_state == "remediation"


def test_risky_action_forces_approval() -> None:
    machine = _machine("INC-RISK")
    machine.after_triage("SEV-3")

    move = machine.after_remediation(
        ["risky"],
        CommanderDecision(
            move="dispatch_verification",
            rationale="Attempted to bypass approval",
        ),
    )

    assert move == "request_approval"
    assert machine.current_state == "awaiting_approval"
    assert [event["type"] for event in list_events("INC-RISK")][-2:] == [
        "commander_overruled",
        "approval_requested",
    ]


def test_verification_retries_once_then_escalates() -> None:
    machine = _machine("INC-RETRY")
    machine.after_triage("SEV-3")
    machine.after_remediation([])

    retry = CommanderDecision(
        move="retry_remediation",
        rationale="One bounded retry may recover the service",
    )
    assert machine.after_verification(False, retry) == "retry_remediation"
    assert machine.snapshot.retry_counts["verification"] == 1
    assert machine.current_state == "remediation"

    machine.after_remediation([])
    assert machine.after_verification(False, retry) == "escalate"
    assert machine.snapshot.retry_counts["verification"] == 1
    assert machine.current_state == "escalated"
    assert list_events("INC-RETRY")[-1]["type"] == "commander_overruled"


def test_paused_snapshot_restores_and_resumes_in_fresh_machine() -> None:
    machine = _machine("INC-PAUSED")
    machine.after_triage("SEV-3")
    machine.after_remediation(["risky"])
    snapshot = machine.to_json()

    restored = IncidentStateMachine.from_json(snapshot)
    assert restored.current_state == "awaiting_approval"
    assert restored.after_approval(True) == "approval_granted"
    assert restored.current_state == "verification"


def test_event_sequence_is_gapless() -> None:
    machine = _machine("INC-SEQUENCE")
    machine.after_triage("SEV-3")
    machine.after_remediation(["risky"])
    machine.after_approval(False)
    machine.after_verification(True)
    assert machine.after_postmortem() == "resolve"
    assert machine.current_state == "resolved"

    events = list_events("INC-SEQUENCE")
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert all(event["payload"]["summary"].strip() for event in events)
    assert [event["type"] for event in events][-3:] == [
        "verification_passed",
        "postmortem_ready",
        "incident_resolved",
    ]


def test_event_validation_and_concurrent_sequence_integrity() -> None:
    clear_events("INC-CONCURRENT")
    with pytest.raises(ValueError, match="unknown event actor"):
        append_event(
            incident_id="INC-CONCURRENT",
            actor="pirate",
            event_type="finding",
            payload={"summary": "Invalid actor."},
        )
    with pytest.raises(ValueError, match="payload.summary"):
        append_event(
            incident_id="INC-CONCURRENT",
            actor="system",
            event_type="finding",
            payload={},
        )

    def append(index: int) -> None:
        append_event(
            incident_id="INC-CONCURRENT",
            actor="system",
            event_type="finding",
            payload={"summary": f"Concurrent finding {index}."},
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(100)))

    events = list_events("INC-CONCURRENT")
    assert [event["seq"] for event in events] == list(range(1, 101))

    events[0]["payload"]["summary"] = "Mutated outside the log."
    assert list_events("INC-CONCURRENT")[0]["payload"]["summary"] != events[0]["payload"]["summary"]

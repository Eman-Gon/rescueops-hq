"""RescueOps — demo CLI entry point.

Usage:
    python main.py                                         # INC-001, interactive approval
    python main.py --incident INC-003-redis-cache-outage
    python main.py --incident INC-001-checkout-db-pool --auto-approve
"""
import argparse

from pipeline import run_incident
from schemas import ApprovalDecision, RemediationPlan

DEFAULT_INCIDENT = "INC-001-checkout-db-pool"


def _sep(title: str) -> None:
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print('─'*62)


def _interactive_approval(plan: RemediationPlan) -> ApprovalDecision:
    _sep("APPROVAL GATE — human decision required")

    if plan.safe:
        print("\nSafe actions (execute automatically, no approval needed):")
        for i, a in enumerate(plan.safe, 1):
            print(f"  {i}. {a.action}")

    if plan.risky:
        print("\nRisky actions (destructive — need your approval):")
        for i, a in enumerate(plan.risky, 1):
            print(f"  {i}. {a.action}")
            print(f"     Rationale: {a.rationale}")

    print()
    while True:
        answer = input("Approve risky actions? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return ApprovalDecision(
                approved=True,
                approver="human-cli",
                note="Approved interactively via CLI",
            )
        if answer in ("n", "no"):
            return ApprovalDecision(
                approved=False,
                approver="human-cli",
                note="Denied interactively via CLI — only safe actions will execute",
            )
        print("Please enter y or n.")


def _print_result(result) -> None:
    _sep("TRIAGE")
    print(f"  Severity:        {result.triage.severity}")
    print(f"  Customer-facing: {result.triage.customer_facing}")
    print(f"  Summary:         {result.triage.summary}")
    print(f"  Route to:        {result.triage.route_to}")
    print(f"  Reason:          {result.triage.reason}")

    _sep("DIAGNOSIS")
    print(f"  Root cause:  {result.diagnosis.root_cause}")
    print(f"  Confidence:  {result.diagnosis.confidence:.2f}")
    print("  Evidence:")
    for e in result.diagnosis.cited_evidence:
        print(f"    • {e}")
    print(f"  Reasoning:   {result.diagnosis.reasoning[:200]}{'...' if len(result.diagnosis.reasoning) > 200 else ''}")

    _sep("REMEDIATION PLAN")
    print("  Safe actions:")
    for a in result.remediation.safe:
        print(f"    • {a.action}")
    print("  Risky actions:")
    for a in result.remediation.risky:
        status = "(APPROVED)" if result.approval.approved else "(DENIED)"
        print(f"    • {a.action}  {status}")

    _sep("APPROVAL")
    verdict = "APPROVED" if result.approval.approved else "DENIED"
    print(f"  Decision:  {verdict}")
    print(f"  Approver:  {result.approval.approver}")
    print(f"  Note:      {result.approval.note}")

    _sep("VERIFICATION")
    status = "RECOVERED" if result.verification.recovered else "NOT RECOVERED"
    print(f"  Status:  {status}")
    print(f"  Metric:  {result.verification.metric_name} = {result.verification.observed_value}  (threshold {result.verification.threshold})")
    print(f"  Note:    {result.verification.note}")

    _sep("POSTMORTEM")
    print(f"  Summary:\n    {result.postmortem.summary}")
    print(f"\n  Root cause confirmed:\n    {result.postmortem.root_cause}")
    if result.postmortem.timeline:
        print("\n  Timeline:")
        for event in result.postmortem.timeline:
            print(f"    • {event}")
    print("\n  Follow-ups:")
    for fu in result.postmortem.follow_ups:
        print(f"    • {fu}")

    _sep(f"DONE  —  run_id: {result.run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RescueOps — AI incident first responder"
    )
    parser.add_argument(
        "--incident", "-i",
        default=DEFAULT_INCIDENT,
        help=f"Incident ID to process (default: {DEFAULT_INCIDENT})",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve all risky actions without prompting",
    )
    args = parser.parse_args()

    print(f"\nRescueOps  —  incident: {args.incident}")
    print("Routing through TrueFoundry AI Gateway  (grok-3 primary)\n")

    callback = (
        (lambda plan: ApprovalDecision(
            approved=True,
            approver="auto-cli",
            note="--auto-approve flag set",
        ))
        if args.auto_approve
        else _interactive_approval
    )

    result = run_incident(args.incident, approval_callback=callback)
    _print_result(result)


if __name__ == "__main__":
    main()

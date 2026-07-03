"""Pre-compute a demo run so the Streamlit app is instant-on for the live demo.

Runs a real incident through the full pipeline (approve path), saves the
RunResult to demo_example.json (app.py auto-loads it on startup), and runs the
eval harness once so the Evaluation tab is pre-populated.

The audit events for the demo run are written to rescueops_audit.db — keep that
file so the app's Audit Log panel renders for the pre-loaded example.

Usage:  python seed_demo.py
"""
from pathlib import Path

import audit
import evaluation
from schemas import ApprovalDecision, RemediationPlan
from pipeline import run_incident

DEMO_INCIDENT = "INC-001-checkout-db-pool"
_DEMO_PATH = Path(__file__).parent / "demo_example.json"


def _approve(plan: RemediationPlan) -> ApprovalDecision:
    return ApprovalDecision(
        approved=True,
        approver="human-ui",
        note="Operator approved risky actions via UI",
    )


def main() -> None:
    audit.init_db()

    print(f"[seed] Running demo incident: {DEMO_INCIDENT} (approve path)...")
    result = run_incident(DEMO_INCIDENT, approval_callback=_approve)
    _DEMO_PATH.write_text(result.model_dump_json(indent=2))
    print(f"[seed] Wrote {_DEMO_PATH.name} (run_id {result.run_id[:8]})")
    print(f"        triage={result.triage.severity}  "
          f"confidence={result.diagnosis.confidence}  "
          f"recovered={result.verification.recovered}")

    print("[seed] Running evaluation across all 5 incidents (this takes ~2 min)...")
    summary = evaluation.evaluate_all()
    print(f"[seed] Eval persisted. aggregate={summary['aggregate']}")
    print("[seed] Done. App is demo-ready — start with: streamlit run app.py")


if __name__ == "__main__":
    main()

# Prompt A — Track A: Agent pipeline (the brains)

You own the reasoning layer of RescueOps. Your teammate (Track B) owns the platform/UI in parallel.
**Read `README.md` first — it is the source of truth and the integration contract.** Build strictly
to the signatures it defines. If anything here conflicts with `README.md`, the README wins; flag it.

## How you operate (governs every response)
- **One phase at a time.** Do only the current phase. At its verify gate, STOP, run the verification, report PASS/FAIL with the actual output, and WAIT for my explicit "go" before the next phase.
- **State assumptions before coding.** If ambiguous or you're about to guess, ask one specific question instead.
- **Simplicity first.** Minimum code for the phase objective. No speculative abstraction, no flexibility I didn't ask for, no error handling for impossible cases.
- **Surgical + stay in your lane.** You may create/edit ONLY: `schemas.py`, `agents.py`, `pipeline.py`, `main.py`. Treat `config.py`, `incidents.py`, `incidents.json` as read-only shared files. NEVER touch Track B's files (`audit.py`, `chaos.py`, `evaluation.py`, `app.py`). Match the existing Phase 1 style.
- **No faking.** Never present a stub as working logic except where this prompt explicitly asks for a stub (Phase A1). If you can't verify live (needs my gateway creds), say so and give me the exact command + expected PASS.
- **Honest status over spin.**

## Critical technical facts (from README)
- Every LLM call goes through `config.build_llm(...)`. The gateway handles model fallback. Do NOT build a model router.
- Agents see `observable(incident)` only — never `incident["ground_truth"]`.
- **Confidence is computed in code from available telemetry sources (no ground_truth), not stated by the model.** Start 1.0, subtract a fixed weight per missing/disabled source.
- Apply chaos by calling Track B's `chaos.apply_chaos(observable, chaos_config)` inside `run_incident` BEFORE handing telemetry to agents. Import it; don't reimplement it. (Until B has committed it, use a trivial local pass-through and swap to the import at integration.)
- Every agent emits a distinct typed artifact from `schemas.py`. Crew stays `Process.sequential`.

## Your phases

**A1 — Lock the contract + ship the stub (do this first, it unblocks your teammate)**
- In `schemas.py`, define every artifact in the README contract.
- In `pipeline.py`, write `run_incident(incident_id, chaos_config=None, approval_callback=None) -> RunResult` that returns **hardcoded, schema-valid** artifacts (a stub — no agents yet). Generate a `run_id`. Call `audit.log_event` if available, else no-op.
- Commit immediately so Track B can build against it.
- Verify gate: `run_incident("INC-001-checkout-db-pool")` returns a fully-populated `RunResult` that validates against the schemas.

**A2 — Real Triage + Diagnosis**
- Replace the stub's triage/diagnosis with real CrewAI agents (Triage already exists in `main.py` — move/adapt it into `agents.py`). Diagnosis cites specific telemetry keys/lines and gets the **computed** confidence (in code).
- Verify gate: on INC-001, diagnosis names a root cause citing real telemetry; confidence is a computed float; removing a telemetry section lowers it.

**A3 — Remediation + the approval seam**
- Remediation agent produces `RemediationPlan` (safe[] vs risky[], each with rationale, `destructive` flag).
- `run_incident` calls `approval_callback(plan)` before any risky action; if no callback supplied, default to auto-reject risky actions (safe default). Record the returned `ApprovalDecision` in the `RunResult`.
- Verify gate: with a callback that approves, risky actions proceed; with none, they're held. Both paths produce a valid `RunResult`.

**A4 — Verification + Postmortem**
- Verification (thin): does the incident's recovery metric cross its threshold? Set `recovered`. (Read the threshold from telemetry/observable, not ground_truth.)
- Postmortem agent assembles `PostmortemReport` from the run's artifacts.
- Verify gate: full `run_incident` returns all artifacts populated end-to-end on INC-001.

## Integration checkpoints with Track B
- After A1: tell B the stub is committed.
- At A3: confirm the `approval_callback` signature matches what B's UI will pass.
- After A4: do a joint run of B's `app.py` against your real `run_incident`.

## Start now
Confirm you've read `README.md`. State your A1 assumptions and plan (the exact schema fields and the stub's canned values). Do NOT write code until I reply "go". Begin.

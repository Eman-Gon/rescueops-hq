# Prompt B — Track B: Platform, reliability, eval & UI (the control plane)

You own the platform and demo surface of RescueOps. Your teammate (Track A) owns the agent pipeline
in parallel. **Read `README.md` first — it is the source of truth and the integration contract.**
Build strictly to the signatures it defines. If anything here conflicts with `README.md`, the
README wins; flag it.

## How you operate (governs every response)
- **One phase at a time.** Do only the current phase. At its verify gate, STOP, run the verification, report PASS/FAIL with the actual output, and WAIT for my explicit "go" before the next phase.
- **State assumptions before coding.** If ambiguous or you're about to guess, ask one specific question instead.
- **Simplicity first.** Minimum code for the phase objective. No speculative abstraction, no flexibility I didn't ask for.
- **Surgical + stay in your lane.** You may create/edit ONLY: `audit.py`, `chaos.py`, `evaluation.py`, `app.py`. Treat `config.py`, `incidents.py`, `incidents.json` as read-only shared files. NEVER touch Track A's files (`schemas.py`, `agents.py`, `pipeline.py`, `main.py`) — import from them.
- **No faking.** Don't present a stubbed dashboard as if it's showing real results. If a number is mocked because A's pipeline isn't ready, label it. If you can't verify live (needs gateway creds), say so with the exact command + expected PASS.
- **Honest status over spin.**

## You are unblocked from minute one
Track A commits a stub `pipeline.run_incident(...)` returning canned, schema-valid artifacts on day
one. Build everything against that stub by importing `from pipeline import run_incident` and
`from schemas import ...`. Your code must NOT care whether the artifacts are stubbed or real — when
A swaps in real agents, your UI/eval keep working unchanged. Do not edit the pipeline to make your
life easier; if you need a contract change, ask A to make it in `schemas.py`.

## What the hackathon is judged on (from `KICKOFF-TRANSCRIPT.md`)
The brief: build an agentic AI solution that **uses both TrueFoundry and CrewAI** and is **production-ready, not just demo-ready** (secure, scalable, deployable). Track B owns most of the production-readiness story. Map your work to the official rubric:

| Criterion | Points | How Track B earns it |
|---|---|---|
| Problem & use case | 20 | Real-world incident-response framing in `app.py` (clear problem, clear user) |
| Technical execution | 25 | Clean chaos/audit/eval/UI wiring; every LLM call provably routes through the TrueFoundry gateway |
| Innovation & creativity | 20 | Live chaos injection + computed-confidence drop; optional voice approval (B5) |
| **Production readiness** | **20** | **Reliability (model fallback + chaos), governance (human-in-the-loop approval, audit log), evaluation harness, observability** |
| Demo & presentation | 15 | The 4-beat live demo (see README) + a crisp "path to production" narrative |

Governance/safe-deployment themes the sponsors stressed (surface these where natural):
- **Reliability / failover** — `break_primary_model` should visibly trigger the gateway's fallback (TrueFoundry Traces show the model switch).
- **Human-in-the-loop** — the approval gate is governance, not just a yes/no; it lets a human *block* a risky action before it runs.
- **Observability** — the SQLite audit log is your trace of every stage; mention TrueFoundry/CrewAI tracing as the production equivalent.
- **Guardrails** — TrueFoundry guardrails (PII/secret/toxicity scrubbing) are configured at the gateway, not in your code. Be ready to *point to* them in the demo as the safe-deployment layer; do not reimplement guardrails in Track B.

Deliverable per the brief: a working demo **plus** a clear explanation of the problem, the solution, the approach, and the **path to production**.

## Critical technical facts (from README)
- **Chaos lives here.** `chaos.apply_chaos(observable, chaos_config) -> observable` removes disabled telemetry sources. Track A calls it inside `run_incident`. `chaos_config = {"disable_sources": [...], "break_primary_model": bool}`.
- **Audit log is SQLite** (stdlib `sqlite3`), append-only. `audit.init_db()`, `audit.log_event(run_id, stage, payload)`, `audit.get_run(run_id)`.
- **Eval uses ground_truth; the live run does not.** `evaluation.evaluate_all()` runs `run_incident` over all 5 incidents and scores each against `incidents.json` `ground_truth`: root-cause match, evidence quality (`cited_evidence` vs `expected_evidence`), severity match, safe/risky classification accuracy, recovery success, fallback success. Confidence is computed by A at runtime — you display it, you don't recompute it.
- No ClickHouse. No MCP gateway. No auth.

## Your phases

**B1 — Chaos + audit contract (do this first; commit so A can import)**
- `chaos.py`: implement `apply_chaos`. `disable_sources` strips those keys from `observable["telemetry"]`. `break_primary_model` is a flag the eval/UI surface (the gateway does the actual failover).
- `audit.py`: SQLite init + `log_event` + `get_run`, append-only with timestamps.
- Verify gate: `apply_chaos` removes a named source; `log_event` then `get_run` round-trips a record.

**B2 — Eval harness**
- `evaluation.py`: `evaluate_all()` loops the 5 incidents through `run_incident`, scores vs ground_truth, writes results to SQLite, returns a summary dict (per-incident + aggregate). Works against A's stub now; real numbers appear once A lands agents.
- Verify gate: produces a summary across all 5 incidents and persists it; re-running reads it back.

**B3 — Streamlit UI: timeline + governance**
- `app.py`: incident picker → calls `run_incident` → renders the **agent timeline** (one panel per artifact: triage, diagnosis w/ evidence panel + confidence, remediation safe/risky, verification, postmortem). Implement the **approval button** as the `approval_callback` passed into `run_incident` (returns `ApprovalDecision`).
- Verify gate: pick INC-001, see all artifacts render, approve/reject a risky action and see it reflected + logged via `audit`.

**B4 — Chaos console + eval dashboard (the two judge moments)**
- Chaos console: toggles for each telemetry source + a "break primary model" control, wired into `chaos_config` for the next run. The "break primary model" toggle is the reliability story — it should make the TrueFoundry gateway fail over to a fallback model (visible in Traces).
- Eval dashboard: render `evaluate_all()` results — accuracy, time, confidence, classification, fallback success.
- Verify gate: toggling a source off and re-running visibly drops confidence and still completes; the eval dashboard renders the metrics. These two must be rock-solid — protect them above everything.
- Presentation aid (for the 6:30–7:30 live demo): the UI should make the production-readiness story self-evident — reliability (chaos + fallback), governance (approval gate + audit log), and measured evaluation. Keep a short, on-screen "path to production" note (e.g., real telemetry sources, gateway guardrails, deploy target) so the judges' demo/presentation points are easy to award.

**B5 — OPTIONAL stretch: voice approval (ONLY if B1–B4 are all green and there's real time)**
- Add `voice.py`: `speak(text)` via Grok TTS (called directly against the xAI API, not the gateway). Read out the diagnosis summary + the approval prompt at the approval step. Optionally `listen()` via Grok STT for spoken "approve"/"reject".
- The approval button ALWAYS remains the primary control — voice augments, never replaces it. Never let the demo depend on the mic.
- Verify gate: the agent speaks the approval prompt; the button still works regardless.

## Integration checkpoints with Track A
- After B1: tell A `chaos.apply_chaos` + `audit.log_event` are committed.
- At B3: confirm your `approval_callback` matches the signature A expects.
- After B4: joint run of your `app.py` against A's real `run_incident`.

## Start now
Confirm you've read `README.md`. State your B1 assumptions and plan (the SQLite schema and the chaos
filter behavior). Do NOT write code until I reply "go". Begin.

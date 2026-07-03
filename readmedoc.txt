What the project is

RescueOps — a resilient, self-evaluating AI incident first responder. A CrewAI crew responds
to simulated production incidents: triage → diagnose (cited evidence + computed confidence) →
propose safe-vs-risky fixes → gate risky actions behind human approval → verify recovery → write
the postmortem. All LLM calls route through the TrueFoundry AI Gateway (Grok primary,
Claude/Gemini fallback configured in the gateway). A chaos console lets anyone break a data
source or the primary model mid-incident; a ground-truth eval dashboard scores the system
against 5 labeled incidents.

It's for a hackathon (Capgemini AIE × TrueFoundry × CrewAI) judged on production-readiness:
reliability, evaluation, governance, multi-agent orchestration. The two demo moments that win:
(1) a judge breaks something live and the system degrades gracefully with confidence dropping for
a computed reason; (2) the eval dashboard shows measured accuracy across the 5 incidents.

Existing code (Phase 1, already built — document it, don't change it)


config.py — build_llm(model_id, temperature) routes any model through the gateway. Every agent uses it.
incidents.py — load_incidents(), get_incident(id), observable(incident) (alert + telemetry only).
schemas.py — TriageReport so far.
main.py — runs Triage on one incident.
incidents.json — 5 incidents, each with alert, telemetry (logs/metrics/deploys), ground_truth.
.env — gateway URL, token, model IDs.


The README must contain these sections


Overview — what RescueOps is, the problem, the two judge moments.
Architecture — a simple diagram (ASCII is fine): incident → CrewAI crew (5 agents) → gateway; chaos layer wrapping telemetry; audit + eval in SQLite; Streamlit surface.
Repo map — every file and which track owns it (see ownership below).
The integration contract — THE most important section. Document these exact signatures so both tracks build against them:

Artifacts (in schemas.py, Track A authors): TriageReport, DiagnosisReport(root_cause, cited_evidence: list[str], confidence: float, reasoning), RemediationAction(action, rationale, destructive: bool), RemediationPlan(safe: list[RemediationAction], risky: list[RemediationAction]), VerificationReport(recovered: bool, metric_name, observed_value, threshold, note), PostmortemReport(summary, timeline: list[str], root_cause, actions_taken, follow_ups), ApprovalDecision(approved: bool, approver, note), RunResult(run_id, incident_id, triage, diagnosis, remediation, approval, verification, postmortem, chaos_config).
Orchestrator (Track A): pipeline.run_incident(incident_id: str, chaos_config: dict | None = None, approval_callback=None) -> RunResult. approval_callback(plan: RemediationPlan) -> ApprovalDecision is supplied by the caller (CLI for A's tests, UI button/voice for B).
Chaos (Track B): chaos.apply_chaos(observable: dict, chaos_config: dict | None) -> dict. chaos_config shape: {"disable_sources": ["logs"|"metrics"|"deploys", ...], "break_primary_model": bool}.
Audit (Track B): audit.init_db(), audit.log_event(run_id: str, stage: str, payload: dict), audit.get_run(run_id) -> list[dict].
Eval (Track B): evaluation.evaluate_all() -> dict (runs run_incident over all 5 incidents, scores vs ground_truth, writes to SQLite, returns a summary).



Confidence vs evaluation — keep these separate (credibility-critical):

Confidence is computed AT RUNTIME from the observable telemetry only (no ground_truth): start at 1.0, subtract a fixed weight per telemetry source missing/disabled. Killing a source drops it mechanically. The agent never states a confidence number.
Evidence quality is scored IN THE EVAL ONLY, where using ground_truth.expected_evidence is allowed (compare it against diagnosis.cited_evidence).
State plainly: agents never see ground_truth; only the eval harness reads it.



Ownership split (parallel work) — Track A: schemas.py, agents.py, pipeline.py, main.py. Track B: audit.py, chaos.py, evaluation.py, app.py. Shared/read-only for both: config.py, incidents.py, incidents.json. Rule: never edit a file the other track owns; coordinate any contract change in schemas.py.
The integration seam — Track A commits a STUB run_incident() returning canned artifacts on day one so Track B can build immediately; A replaces internals phase by phase without changing the signature.
Build phases — list both tracks' phases (from the two build prompts) and the cut-line: protect chaos + eval above all; postmortem drops first.
Setup — Python 3.12, pip install -r requirements.txt, .env from .env.example, run order.
Demo script — the exact 4-beat run judges see: pick incident → agents produce artifacts → approve a risky fix → verify recovery + postmortem; then break a source/model live; then show the eval dashboard.
Hard constraints — no real cloud integrations; no custom model router (gateway owns fallback); SQLite not ClickHouse; sequential crew; no auth/registry.
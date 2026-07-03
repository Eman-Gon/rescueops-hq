# Track A prompt — Agents & model layer

Read ARCHITECTURE.md and CLAUDE.md fully before anything. CLAUDE.md Principles 1–4 govern
every phase; per Principle 4, open each phase by restating it as numbered
`[step] → verify: [check]` lines before writing code. You own: `agents/`,
`pipeline.py`, `llm_client.py`, `schemas.py`, `events.py` (write path), pack rubric/
scenario content. You do NOT touch Track B files (§8). Work phase-by-phase with gates.

## Phase A1 — Repo audit (ARCHITECTURE §9.1)
The prior RescueOps repo is checked out at the path I give you. Answer with grep/read
evidence, no changes yet:
1. Is every LLM call routed through one client/config module? List every call site.
2. Are incidents, severity rubric, and mock tools data-driven (JSON/config) or embedded
   in agent definitions? List exact locations.
3. List TrueFoundry / Traceloop / MCP-gateway touchpoints (files + lines).
→ VERIFY: the three answers with pasted evidence. HUMAN GATE: I approve either "proceed"
or "insert scoped refactor phase" before you write any code.

## Phase A2 — Model swap (local)
Point `llm_client.py` at the EdgeOne gateway per .env.template (OpenAI-compatible client,
LLM_BASE_URL + MAKERS_MODELS_KEY, model = LLM_PRIMARY_MODEL). Implement in-code failover:
try primary → on failure retry once with LLM_FALLBACK_MODEL → emit `model_fallback`
event. (If Phase 0 recon showed the gateway routes fallbacks natively, configure that
instead and the in-code path becomes a guard — say which applies.)
→ VERIFY: one it-ops incident end-to-end locally on the gateway; then all 5 scenarios —
report per-scenario: structured outputs parsed cleanly y/n, latency, any schema mangling
by deepseek-v4-flash. HUMAN GATE: I confirm primary/fallback model assignment on this
evidence.

## Phase A3 — Strip old platform
Remove TrueFoundry/Traceloop/MCP-gateway code paths found in A1 from YOUR files only.
→ VERIFY: grep zero matches in Track A files; full local incident still green.

## Phase A4 — Commander + state machine + event production
1. Root `policy.json`: states, legal transitions per state, Commander decision points,
   retry caps, approval-forced action classes. Ship the default policy matching
   ARCHITECTURE §3.2. Validate at boot; malformed policy → clear error, refuse to start.
2. `pipeline.py`: explicit state machine parameterized by the loaded policy —
   deterministic defaults per state. Preserve run_until_approval/resume_after_approval
   semantics exactly.
3. Commander agent: receives current state + legal moves (from policy) + latest
   specialist output; returns {move, rationale}. Illegal/unparseable → policy default +
   `commander_overruled` event. No autonomy beyond the policy's decision points.
4. `events.py`: append-one-event helper per §4 schema; every agent/tool/decision emits.
   payload.summary: one human sentence (rendered in the UI). Stamp trace_id on
   agent/model/tool events when the runtime exposes it (per recon Q9); null otherwise.
5. Paused-state persistence: the run_until_approval snapshot persists in Makers
   context.store per recon Q8 (native-first rule, ARCHITECTURE §7). If recon showed the
   binding doesn't fit, use KV and add the written reason to ARCHITECTURE §7 — that
   documentation is part of this phase's deliverable, not optional.
→ VERIFY (tests): illegal move falls back + logs overrule; SEV-3 fast-paths; failed
verification retries exactly per policy cap then escalates; malformed policy.json fails
at boot with a clear message; every pipeline step emits ≥1 event and seq is gapless;
a paused incident resumes correctly from persisted state after process restart.
Paste test output.

## Phase A5 — Integration support
Expose the runner in the handler shape Track B's Phase-0 recon specified (agent runtime
idiom). Coordinate the swap with Track B; do not modify their files.
→ VERIFY: full incident on PROD with real events consumed by the frontend. (Joint gate.)

## Phase A6 — Stretch (only on explicit "go", in order)
a. sec-ops pack: 5 SOC scenarios with ground truth, rubric.md, playbook.json, and ONE
   real tool — NVD/CISA-KEV CVE lookup with response caching; tolerate the feed being
   chaos-killed (degrade + lower confidence, never crash).
   → VERIFY: SOC scenario end-to-end; kill the feed → graceful degradation event trail.
b. Incident-chat agent on Makers session memory (context.store): answers questions about
   a COMPLETED incident, citing event-log entries by seq. No new autonomy.
   → VERIFY: two-turn conversation with correct citations.

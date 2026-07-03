# Track B prompt — Platform & surface (Makers deploy, Ops Floor, trust harness)

Read ARCHITECTURE.md and CLAUDE.md fully before anything. CLAUDE.md Principles 1–4 govern
every phase; per Principle 4, open each phase by restating it as numbered
`[step] → verify: [check]` lines before writing code. You own: Makers deploy config,
`api/` cloud functions, `storage.py`, `chaos.py`, `evaluation.py`, all of `web/`, event
consumption. You do NOT touch Track A files (§8).

## Phase B0 — Platform recon (BLOCKS Track A's packaging decisions — do first)
HUMAN GATE up front: I create the Makers account and paste credentials/CLI auth.
Deploy their hello-world agent template. Then answer IN WRITING with evidence
(doc links + observed behavior):
1. Agent-runtime handler shape for a Python/CrewAI app; how a multi-step run with a
   mid-run human pause fits it.
2. Execution time limits: agent runtime vs cloud functions vs edge functions.
3. Model gateway: does it support fallback routing across bound keys natively? Exact
   mechanism for binding an Anthropic key + resulting model string.
4. KV/Blob API surface (append patterns, read-after-write behavior, size limits).
5. Secrets handling (console env vars? per-deploy?).
6. Sandboxed tool mechanism: how a tool call opts into the sandbox.
7. Streaming/SSE support y/n (polling remains the committed default regardless).
8. Session store (context.store): what CrewAI-native binding is exposed; can arbitrary
   pipeline state (our paused run_until_approval snapshot) persist in it; size limits.
9. Tracing: is a trace/run ID retrievable in-process per agent/model/tool call (so we
   can stamp trace_id on events), and what URL shape opens a specific trace?
10. Gateway usage/latency metrics: queryable via API y/n (informational only — no scope
    depends on it; if trivially available it becomes an eval-board footnote, else skip).
11. Outbound HTTPS from cloud functions to arbitrary hosts (api.twilio.com) y/n, and any
    egress restrictions — gates the §6A SMS channel.
→ VERIFY: hello-world public URL live. HUMAN GATE: we lock deployment shape + update
.env.template placeholders from findings.

## Phase B1 — Stub stream + surfaces on prod
1. `storage.py`: KV adapter (append event, read since seq, incidents, eval cache).
2. `api/`: events (read), incidents CRUD, approval endpoints, chaos toggles, eval runner.
3. STUB (sanctioned, labeled, deleted at integration): replays a canned event sequence
   for one incident on a timer through the REAL storage + REAL /api/events path — so
   only the producer is fake, never the pipe.
4. `web/`: SPA shell — dashboard (event timeline + incident state), approval panel,
   chaos console, eval board, domain switcher reading packs list; poller per §4. The
   dashboard is the CORE renderer; the Ops Floor (stretch) later consumes the same
   poller untouched.
→ VERIFY: on the PRODUCTION URL, canned incident streams through /api/events; approval
buttons round-trip; events survive a cold refresh (KV-persisted).

## Phase B2 — Trust harness real
`chaos.py` (kill/restore any pack data source + primary model + real-feed flag) and
`evaluation.py` (run labeled scenarios, score severity accuracy / root-cause match /
time-to-diagnosis per pack, cache results in KV).
→ VERIFY: eval board renders 5/5 from cache after cold refresh; chaos flags visibly
alter stubbed tool_failed events.

## Phase B3 — Integration (joint, ARCHITECTURE §9.4)
Point the frontend at Track A's real runner; DELETE the stub.
→ VERIFY: full real incident on prod — dashboard renders real events, approval
pause/resume works, timed end-to-end. Then Phase 5 (§9.5) chaos/failover/eval on prod.
CORE MVP ENDS HERE. Everything below requires explicit "go".

## Phase B4 — Stretch (in ladder order, each gated on previous green)
a. On-call SMS channel per ARCHITECTURE §6A. HUMAN GATE first: I provide Twilio
   credentials + the verified on-call number. Build: `notify.py` (outbound send on
   approval_requested / postmortem_ready landing in storage append; fire-and-forget;
   emits oncall_notified) and `api/sms/inbound` (signature validation, sender allowlist,
   YES/NO grammar per §6A, calls the EXISTING approval endpoint, emits oncall_reply).
   No new approval logic — if you find yourself writing approval state, stop (Principle 2).
   → VERIFY (tests first where feasible): grammar parser — YES/NO/case/with-and-without
   id/ambiguous-multiple-pending/garbage; unregistered sender rejected + logged;
   double-approval (web races SMS) yields exactly one approval event. Then live on prod
   with a real phone (HUMAN GATE): risky action → text arrives → reply YES → run
   resumes with channel="sms"; resolution → summary text arrives, one segment.
b. Ops Floor MVP: DOM/CSS + inline SVG only. Six desks + Commander podium + incident
   board + status light + service racks from the pack's floor.json. Character states:
   idle / working / blocked / down. Speech bubbles from payload.summary (truncate 90
   chars). Implement the §5 event→animation table as literally a table (one mapping
   module). The dashboard remains the fallback renderer of the same stream.
   → VERIFY: a REAL incident plays out visually on prod: alarm → dispatch bubbles →
   working loops → approval freeze/pulse → resolve; chaos toggle sets a rack on fire
   live. HUMAN GATE: look approved before any polish.
c. (after Track A's sec-ops pack) Redeploy-a-domain beat: prepare packs/supply-chain
   (2 scenarios) on a branch; rehearse commit → `edgeone deploy` → refresh → new domain
   appears. Measure latency.
   → VERIFY: performed twice successfully, timings recorded in DEMO-SCRIPT.md.
d. Ops Floor polish: walking paths, confetti on verification_passed, easing. Last, always.

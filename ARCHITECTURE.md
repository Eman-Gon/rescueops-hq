# RescueOps HQ — Architecture & Contract

**One line:** A visible, testable **agent harness** — the model is the brain (via the
Makers gateway); we build the operating system around it: memory (append-only event log),
context management (what each agent sees), safety controls (policy-defined legal moves,
human approval gates, chaos-tested), and tool access (pack tools + sandboxed execution).
Incident response — a Commander dispatching five specialists through triage → diagnosis →
remediation → verification → postmortem — is the demo domain that proves it.

**Event:** AI Builders × Tencent EdgeOne Makers — Agent Forge Mini Hackathon (SF).
**Judging:** Completeness · Innovation · Real-Life Problem · Sponsored Product Usage.
**Demo slot:** 3 minutes, top-5 demo at 4:00 PM.

This file is the single source of truth. Both tracks build against it. If code and this
file disagree, this file wins until explicitly amended.

---

## 1. Why this wins (map to rubric)

- **Completeness** — ported, working system on a public Makers URL. Most 1-hour teams
  will demo localhost or a chat wrapper.
- **Innovation** — the harness is the product: policy-defined legal moves the LLM cannot
  escape, human approval gates, live chaos injection, and measured accuracy on labeled
  incidents. Nobody else will attack their own agent on stage. (If the Ops Floor ships,
  judges additionally *watch* the harness work — characters block on approval and catch
  fire under chaos.)
- **Real-Life Problem** — incident response / SOC triage; the domain-pack reveal shows the
  same harness generalizes (IT ops ↔ security ops).
- **Sponsored Usage** — see §7. Every Makers primitive is used for a real job, named out
  loud in the demo.

**Pitch line:** "Everyone deployed an agent today. We deployed a harness — the operating
system around the model: memory, safety controls, tools, human gates — chaos-tested and
evaluated, live."

---

## 2. System overview

```
┌────────────────────────────────────────────────────────────────────┐
│ EdgeOne Makers project (one repo, one-click deploy via CLI / Git)  │
│                                                                    │
│  Static hosting                    Agent runtime (Python)          │
│  ┌─────────────────────┐           ┌─────────────────────────────┐ │
│  │ React SPA           │           │ COMMANDER (LLM, constrained │ │
│  │  · Ops Floor (anim) │──HTTP────▶│ by state machine in code)   │ │
│  │  · Dashboard        │  poll     │   dispatches ↓               │ │
│  │  · Approval panel   │  /events  │ Triage · Diagnosis ·         │ │
│  │  · Chaos console    │           │ Remediation · Verification · │ │
│  │  · Eval board       │           │ Postmortem  (CrewAI, ported) │ │
│  │  · Domain switcher  │           └──────┬───────────┬──────────┘ │
│  └─────────────────────┘                  │           │            │
│                                     Domain-pack   LLM calls via    │
│  Cloud functions (plain HTTP):      tools (mock   Makers MODEL     │
│   incidents CRUD · chaos toggles ·  logs/metrics/ GATEWAY          │
│   approval endpoints · eval runner  SIEM feeds;   ai-gateway.      │
│                                     chaos flags;  edgeone.link     │
│                                     +1 real tool: primary:         │
│                                     NVD CVE fetch) @makers/deep-   │
│                                                    seek-v4-flash   │
│                                                    fallback: bound │
│                                                    Anthropic key   │
│  STATE: Makers KV/Blob — event log (append-only), incidents,       │
│         eval cache, chat sessions (stretch)                        │
│  OBSERVABILITY: Makers built-in end-to-end tracing (demo beat)     │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent design

### 3.1 Specialists (ported from RescueOps, logic unchanged)
Triage (severity per domain-pack rubric) → Diagnosis (cited evidence + computed
confidence) → Remediation (safe vs risky actions; risky gate on human approval) →
Verification (thin: did the recovery metric cross back? a check, not a reasoning
marathon) → Postmortem (report).

### 3.2 Incident Commander (NEW — the "manager agent")
An LLM agent that makes real dispatch decisions, constrained by a code-enforced state
machine. The code supplies the set of **legal next moves** for the current state; the
Commander chooses among them and emits a one-sentence rationale (which becomes its
speech bubble on the Ops Floor).

**Legal moves are user-configurable.** A single root `policy.json` defines: states, legal
transitions per state, which decision points the Commander owns, retry caps, and which
action classes force human approval. Loaded and validated at startup — an invalid policy
fails loudly at boot, never silently mid-incident. Code enforces the loaded policy at
runtime exactly as before; editing the JSON + redeploy is how you change the harness's
safety envelope. (No per-pack overrides, no UI editor — speculative.)

Decision points the Commander owns under the default policy:
- After Triage: `fast_path` (SEV-3: skip deep diagnosis) vs `deep_diagnosis`.
- After Diagnosis: `dispatch_remediation` vs `escalate_to_human` (low confidence).
- After a risky action is proposed: `request_approval` (forced by code — Commander
  cannot bypass; it only phrases the request).
- After failed Verification: `retry_remediation` (max 1 retry, enforced in code) vs
  `escalate`.

Rules: the state machine in `pipeline.py`, parameterized by `policy.json`, is the
authority. The Commander NEVER free-form routes. If the LLM returns an illegal move, code
falls back to the policy's deterministic default and logs a `commander_overruled` event
(this is honest, and it's a great trace to show).

### 3.3 Existing approval split (kept verbatim)
`run_until_approval()` / `resume_after_approval()` — two-phase HTTP so no request blocks
on a human, and so serverless timeouts can never kill a run mid-approval. If recon (§9
Phase 0) finds tight per-request limits, the same pattern extends to per-agent invocation.

---

## 4. THE EVENT STREAM — the contract between everything

Every meaningful action appends one event to an append-only log in Makers KV, keyed by
incident. **The Ops Floor, the plain dashboard, the audit view, and the eval harness are
all just consumers of this stream.** Nothing in the frontend is animated from anything
except real events.

```json
{
  "seq": 41,
  "ts": "2026-07-03T21:04:11Z",
  "incident_id": "INC-3",
  "actor": "commander | triage | diagnosis | remediation | verification |
            postmortem | human | chaos | gateway | system",
  "type": "incident_opened | agent_dispatched | agent_started | tool_call |
           tool_result | tool_failed | finding | action_proposed |
           approval_requested | approval_granted | approval_denied |
           action_executed | verification_passed | verification_failed |
           commander_decision | commander_overruled | model_fallback |
           chaos_injected | chaos_cleared | incident_resolved | postmortem_ready |
           oncall_notified | oncall_reply",
  "payload": { "summary": "<one sentence, human-readable>", "...": "type-specific" },
  "trace_id": "<Makers trace reference when available, else null>"
}
```

- `approval_granted`/`approval_denied` carry `payload.channel: "web" | "sms"` — one
  approval state machine, two channels (§6A). `oncall_notified` (actor: system) records
  an outbound text (payload.kind: "approval_request" | "summary"); `oncall_reply`
  (actor: human) records the inbound text verbatim + parsed intent.
- `trace_id` links an event to its Makers end-to-end trace: the dashboard renders it as
  a click-through from our event row to their trace view. Populated for agent/model/tool
  events when the runtime exposes the ID (Phase 0 recon Q9); null is legal.

- Transport: frontend polls `GET /api/events?incident=INC-3&since=<seq>` every 1s.
  (SSE/streaming on Makers is a Phase-0 recon question; polling is the committed default —
  it cannot fail in a demo.)
- `payload.summary` is written for humans; it is the speech-bubble text. Truncate at 90
  chars in the UI, never in the log.
- Track A owns event **production**, Track B owns event **consumption**. Neither touches
  the other's side. Schema changes require editing this file first.

---

## 5. The Ops Floor (visual layer — STRETCH #1, built only after core MVP is green)

Core MVP renders the event stream through the plain dashboard. The Ops Floor is a second
renderer of the identical stream — nothing downstream depends on it, so it slots in
whenever core ships without touching anything else.

A playful 2D office rendered with DOM/CSS + inline SVG characters. **No game engine, no
canvas library** — speculative machinery, and CSS transitions are plenty at this scale.

Scene: six desks (one per specialist) around a central Commander podium; an "incident
board" wall; a status light; service racks for each data source (logs, metrics, deploys /
SIEM, EDR, threat-feed depending on domain pack).

Event → animation mapping (the whole renderer is this table):

| Event                      | Animation                                                    |
|----------------------------|--------------------------------------------------------------|
| incident_opened            | Alarm light spins; board posts the incident card             |
| agent_dispatched           | Commander speech bubble = rationale; pointer to specialist   |
| agent_started              | Character walks desk → board, then "typing" loop             |
| tool_call / tool_result    | Dotted line character → service rack; rack blinks            |
| finding                    | Speech bubble with payload.summary                           |
| approval_requested         | Character freezes, red "WAITING FOR HUMAN" tag; approval panel pulses |
| approval_granted/denied    | Green check / red X floats up; character resumes or returns  |
| chaos_injected             | Target rack catches fire (🔥 + shake); dependent characters show ⚠ |
| model_fallback             | Gateway rack flickers, badge swaps "deepseek → claude"       |
| verification_passed        | Confetti burst (small); light goes green                     |
| incident_resolved          | All characters return to desks; board card stamps RESOLVED   |

Floor MVP: characters exist, four states (idle / working / blocked / down), speech
bubbles, alarm light, fire-on-chaos. Everything else (walking paths, confetti, easing
polish) is the LAST stretch item. The plain dashboard is always the fallback renderer of
the same stream — if the floor slips or breaks, the demo survives on the dashboard.

---

## 6. Domain packs

A pack is **data, not code**: `packs/<name>/` containing `scenarios.json` (labeled, with
ground truth), `rubric.md` (severity definitions injected into Triage), `playbook.json`
(safe vs risky actions), `tools.py` (mock source functions; same signatures across packs),
`floor.json` (rack names/icons for the Ops Floor).

- Pack 1: `it-ops` (the original five incidents, ported).
- Pack 2: `sec-ops` (stretch #1): SOC alerts; Diagnosis gains ONE real tool — live NVD/
  CISA-KEV CVE lookup (response cached; chaos can kill it, which is itself a demo beat).
- Pack 3: `supply-chain` (exists only as the live-redeploy beat — 2 scenarios, committed
  and deployed DURING the demo: `edgeone deploy` → refresh → new domain in the dropdown).

HARD RULE: no pack-loader framework, no registry, no plugin system. A pack is a directory
read at startup. The generality is demonstrated by the second pack existing, not by
speculative abstraction.

---

## 6A. On-call SMS channel (stretch #1 — first thing built after core MVP)

The human gate works where humans actually are: their phone. One on-call engineer
(ONCALL_PHONE_NUMBER) gets texted by the harness and can approve risky actions by reply.

**Design rule: SMS is just another consumer of the event stream. Track A is untouched.**
- Outbound: the storage append path (`storage.py`, Track B) fires `notify.py` when these
  events land — `approval_requested` → text the pending action, its risk class, and the
  reply grammar; `postmortem_ready` (or `incident_resolved` if postmortem was cut) →
  text a summary: incident id, severity, root cause one-liner, actions taken
  (auto vs human-gated), duration. One SMS segment target (~300 chars), link to the
  incident URL. Send is fire-and-forget (try/except) — a Twilio outage may never stall
  the pipeline. Every send emits `oncall_notified`.
- Inbound: Twilio webhook → Makers cloud function `POST /api/sms/inbound` → parses reply
  → calls the SAME approval endpoint the web panel uses. One approval state machine,
  two channels; first response wins, the second channel gets "already resolved" back.
- Reply grammar (all of it): `YES [incident-id]` / `NO [incident-id]`, case-insensitive.
  Bare YES/NO accepted only when exactly one approval is pending across incidents;
  otherwise reply asks to specify. Anything unparseable → reply with the grammar.
  Every inbound emits `oncall_reply`.
- Security floor (an approval channel gets exactly this, no more): accept only
  ONCALL_PHONE_NUMBER as sender; validate Twilio's webhook signature. Rejected inbound
  is logged, not processed.
- Provider: Twilio (trial account acceptable: verified numbers only + trial prefix on
  messages — fine for a demo). SMS_ENABLED=false turns the whole channel off; the web
  panel is always the guaranteed approval path. That is why this feature is stretch #1
  and NOT in the untouchable set: an external dependency (Twilio, venue cell coverage)
  must never be able to sink the demo.
- Explicitly out of scope: rosters, escalation chains, scheduling, multi-recipient,
  two-way chat. Text one human; accept YES/NO. That is the feature.

---

## 7. Harness architecture (ours on theirs, named in the demo)

Definition used here: the harness is the software infrastructure wrapping the model to
make it a functional agent — the model is the brain; the harness is the OS providing
memory, context management, safety controls, and tool access.

Our harness layers → implementation:
- **Memory** — append-only event log + incident/eval state in Makers KV/Blob; session
  memory (chat stretch) via Makers context.store.
- **Context management** — each specialist receives a scoped context assembled from the
  event log (its dispatch, relevant tool results, pack rubric) — never the raw firehose.
- **Safety controls** — policy.json legal moves, forced approval gates on risky action
  classes, commander_overruled fallback, retry caps, chaos-tested under failure.
- **Tool access** — pack tools (mock sources + real CVE feed) and remediation execution
  via Makers sandboxed tools.

Makers primitives underneath — with DEPTH COMMITMENTS (each must be evidenced, §9.5):

| Makers primitive        | Our real use                                                  |
|-------------------------|---------------------------------------------------------------|
| Agent runtime           | Hosts Commander + crew in framework-native (CrewAI) idiom     |
| Model gateway           | ALL LLM calls; primary @makers/deepseek-v4-flash (free quota),|
|                         | fallback = bound Anthropic key; failover is a live demo beat  |
| Memory / session store  | THE pipeline's memory: paused state between run_until_approval|
|                         | and resume_after_approval persists in context.store; CrewAI   |
|                         | memory binds to it (recon-gated; KV fallback documented if    |
|                         | the binding doesn't fit). Chat sessions (stretch) same store. |
| KV / Blob storage       | Event log, incidents, eval cache — the system of record       |
| Sandboxed tools         | Remediation "execute action" runs as sandboxed tool call      |
|                         | (Phase-0 recon confirms mechanism; else document why not)     |
| Built-in tracing        | trace_id on events → click-through from our dashboard rows to |
|                         | their trace view; zero instrumentation written                |
| Cloud functions         | Plain HTTP: CRUD, chaos toggles, approvals, eval runner,      |
|                         | Twilio inbound-SMS webhook (§6A)                              |
| Static hosting          | The SPA / Ops Floor                                           |
| One-click deploy (CLI)  | The live redeploy-a-domain beat                               |

**Native-first rule:** where Makers provides a capability, use it instead of building our
own. Hand-rolling is permitted only when Phase 0 recon shows the native path doesn't fit
this design — and the reason is written into this file at that time.

**Evidence rule:** no §7 row may be claimed in the demo without observable proof (a
trace, a console view, a storage read) captured at §9.5. Unevidenced claims get cut from
the script, not softened.

Our harness ON TOP of theirs (the standout): chaos console (kill any data source, kill
the primary model, kill the real CVE feed) + ground-truth eval (accuracy & time-to-
diagnosis across labeled incidents, per pack, cached in KV, rendered as the eval board).

---

## 8. File ownership (two tracks, disjoint)

- **Track A — Agents & model layer:** `agents/`, `pipeline.py` (state machine +
  Commander), `llm_client.py`, `schemas.py`, `packs/*/rubric.md`, `packs/*/scenarios.json`
  event PRODUCTION helpers (`events.py` write path).
- **Track B — Platform & surface:** Makers deploy config, cloud functions (`api/`),
  `storage.py` (KV adapter), `chaos.py`, `evaluation.py`, ALL frontend (`web/`), event
  CONSUMPTION, Ops Floor, demo tooling.
- Shared: this file + `.env.template` only. Changes to either require both to ack.
- Day-one seam: Track B deploys a **stub event stream** (canned event sequences for one
  incident, replayed on a timer) and builds the dashboard + control surfaces against it.
  Track A ports the real crew locally. Integration = pointing the frontend at the real
  `/api/events`. The stub is deleted at integration (it is a scaffold, never demoed).

---

## 9. Phases & gates (VERIFY = automated check with real output; HUMAN = you)

0. **[B] Recon** — deploy Makers hello-world agent; answer IN WRITING: runtime handler
   shape · timeout limits (runtime vs functions) · gateway fallback routing y/n ·
   KV/Blob API · secrets handling · sandboxed-tool mechanism · streaming/SSE y/n.
   → VERIFY: public URL live. HUMAN: Shape decisions confirmed against answers.
1. **[A] Repo audit** — confirm LLM client centralization & data/code isolation of
   incidents/rubric/tools. → VERIFY: grep evidence pasted. (If either fails, a scoped
   refactor phase is inserted HERE, not discovered later.)
2. **[A] Model swap local** → VERIFY: one incident end-to-end via EdgeOne gateway; all 5
   it-ops scenarios parse structured outputs cleanly on deepseek-v4-flash (this is where
   model quality is exposed; decide primary/fallback assignment on evidence).
   **[B ∥] Stub stream + dashboard on prod** → VERIFY: canned incident streams through
   /api/events and renders on the production URL.
3. **[A] Commander + event production** (state machine parameterized by policy.json,
   legal-move constraint, commander_overruled fallback) → VERIFY: unit tests — illegal
   move falls back; SEV-3 takes fast path; failed verification retries exactly per
   policy cap; malformed policy.json fails at boot with a clear error.
   **[B ∥] KV storage port + chaos + eval wired to stub** → VERIFY: events persist across
   cold refresh; grep zero TrueFoundry/Traceloop imports repo-wide.
4. **[BOTH] Integration** — real crew behind `/api/events` on prod. → VERIFY: full
   incident on the production URL incl. approval pause/resume, dashboard rendering the
   real event stream, timed end-to-end. (Budget real time; this is where two-person
   projects die.)
5. **[B leads] Trust harness on prod + INTEGRATION EVIDENCE** → VERIFY: model-kill
   mid-incident → completes on fallback with visible confidence drop + model_fallback
   event; data-source kill → graceful degradation; 5/5 evals cached & render after cold
   refresh. THEN the evidence checklist: for every §7 row, capture observable proof
   (trace link resolving from an event's trace_id, session-store read showing paused
   pipeline state, sandbox execution record, console views). Rows without evidence are
   struck from DEMO-SCRIPT.md.
6. **Stretch ladder, strictly in order, each gated on previous green:**
   a. [B] On-call SMS channel (§6A) → VERIFY: on prod, a risky action texts the on-call
      phone; reply YES resumes the run with approval_granted channel="sms"; reply from
      an unregistered number is rejected + logged; web-panel approval racing the text
      leaves exactly one approval event; resolution sends the summary text. (HUMAN GATE:
      real phone in hand for this one.)
   b. [B] Ops Floor MVP (§5) → VERIFY: real incident plays out visually on prod: alarm →
      dispatch bubbles → working loops → approval freeze → resolve; chaos sets a rack on
      fire live. HUMAN: look approved.
   c. [A] sec-ops pack + live CVE tool → VERIFY: SOC scenario end-to-end; CVE fetch
      cached; chaos-kill of feed degrades gracefully.
   d. [B] redeploy-a-domain beat → VERIFY: rehearsed twice, deploy latency measured.
   e. [A] incident chat on Makers session memory → VERIFY: two-turn convo cites audit log.
   f. [B] Ops Floor polish (walking paths, confetti, easing) — last, always.
7. **[BOTH] Demo prep** — script in DEMO-SCRIPT.md; two full rehearsals on prod; fresh
   incident pre-warming before demos; roles fixed (who drives, who narrates).

**Cut lines, rightmost first:** floor polish → chat → redeploy beat → sec-ops pack →
Ops Floor MVP → SMS channel → Postmortem agent → Verification agent.
**Untouchable (core MVP):** Commander + policy.json, chaos console, eval board,
dashboard (incl. web approval panel), deployed URL.

---

## 10. Resolved decisions (was: open questions)

1. Track ownership: as written in §8; swap freely — the split works under any ownership.
2. Repo unknowns: resolved by Phase A1 audit (no offhand answers available).
3. Art direction: flat SVG humanoids, 2-color per character, domain-pack accent color.
4. Domain packs: in scope as stretch (§9.6b), behind the Ops Floor MVP. Pack structure
   is how content is organized regardless, so keeping it costs nothing.
5. Commander legal moves: user-configurable via root policy.json (§3.2).
6. Harness definition (§7): the software OS around the model — memory, context
   management, safety controls, tool access. This is the product framing.
7. On-call SMS channel (§6A): Twilio, one number, YES/NO grammar, event-consumer design,
   stretch #1, never in the untouchable set (external dependency). Track A untouched.

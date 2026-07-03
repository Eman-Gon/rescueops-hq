# DEMO-SCRIPT.md — 3 minutes, top-5 slot, two presenters

Roles (decide at Phase 7 and write here): DRIVER = ______  NARRATOR = ______
Pre-demo: start DEMO_PREWARM_INCIDENT on prod ~2 min before slot so a completed run
exists; open tabs: Ops Floor (or dashboard) · Makers trace view · eval board · terminal
(if redeploy beat shipped).

## 0:00–0:30 — Problem
"A model is a brain; it's not an agent until there's an operating system around it —
memory, context, safety controls, tools. That's the harness, and it's what everyone here
skips. RescueOps HQ is a harness you can see and test: a Commander dispatching five
incident-response specialists under a policy it cannot escape — and we attack it live."

## 0:30–2:00 — Live incident (Ops Floor if shipped; dashboard otherwise — same events)
- Open a fresh incident. Narrate what the JUDGES SEE: Commander's dispatch rationale,
  Triage severity, Diagnosis citing evidence with computed confidence. Point at
  policy.json once: "the Commander's legal moves are this file — edit it, redeploy,
  new safety envelope."
- CHAOS BEAT: kill the primary model mid-run from the chaos console → model_fallback
  event ("deepseek → claude"), run completes with visible confidence drop. Sponsor line:
  "every model call rides the Makers model gateway — failover just happened on stage."
- APPROVAL BEAT (the moment, if SMS shipped): risky action halts the run → the on-call
  phone ON STAGE buzzes with the approval text → reply YES from the phone → run resumes,
  event log shows approval channel="sms". "Safe actions auto-execute; risky ones text
  the engineer who'd actually be on call — forced by policy, not by prompt. Approval
  works where humans actually are." (SMS not shipped or no signal → approve from the
  web panel; the line becomes "…wait for a human." Decide which at rehearsal, not live.)
- CLOSE OF INCIDENT: resolution summary text arrives on the same phone — hold it up.

## 2:00–2:30 — Trust harness + Makers harness
- Eval board: "measured accuracy and time-to-diagnosis on labeled incidents — per
  domain." (If sec-ops shipped: flip the domain switcher, show the same floor running a
  SOC alert with a LIVE CVE lookup.)
- Makers trace view — entered by clicking a trace_id ON one of our event rows: "every
  event in our log links to the platform's end-to-end trace — runtime, session memory,
  KV, gateway, sandbox, hosting: Makers primitives doing real jobs, and here's the
  paused-approval state sitting in their session store."

## 2:30–3:00 — The thesis beat + close
- (If shipped) LIVE REDEPLOY: `edgeone deploy` the supply-chain pack → refresh → third
  domain appears. "New domain to production in one click — that's the point of today."
- Close on the URL + QR: "It's deployed. Scan it, open an incident, set something on
  fire yourself."

## Fallbacks (rehearsed, not improvised)
- Live run stalls → switch to the pre-warmed completed incident and replay its event
  stream. (Real events, recorded — say so honestly.)
- Redeploy beat over time → cut it; close on URL.
- SMS beat fails (no signal, Twilio hiccup) → web approval panel, same state machine;
  say one sentence and move on. Never debug SMS on stage.
- Ops Floor shipped but misbehaving → dashboard shows the identical stream; the harness
  story loses nothing.

## Rehearsal log (fill in — two full rehearsals required on PROD)
1. Date/time: ____  end-to-end incident duration: ____  issues: ____
2. Date/time: ____  redeploy latency: ____  issues: ____

## Likely judge questions (drill these)
- "Is the Commander really deciding, or is it scripted?" → show a commander_decision vs
  commander_overruled trace; explain legal-move constraint honestly.
- "Why not just use the platform's harness alone?" → their harness runs agents; ours
  proves you can trust them (chaos + eval). Complementary, and that's the product.
- "Is the office animation real?" → every animation maps 1:1 to an event in the KV log;
  open the raw event feed next to the floor.
- "Pre-existing code?" → built RescueOps at a prior hackathon; today = Commander, Ops
  Floor, domain packs, and the Makers port. (Confirm rules at kickoff.)

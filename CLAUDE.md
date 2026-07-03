# CLAUDE.md — operating rules for this repo

You are building RescueOps HQ per ARCHITECTURE.md. That file is the contract; if code and
the contract disagree, stop and say so — do not silently pick.

## Principle 1 — Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.
- State your assumptions explicitly before implementing. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop, name what's confusing, and ask ONE specific question.
- Phase gates are where this happens: one phase at a time (ARCHITECTURE.md §9), stop at
  every gate, wait for explicit "go".
  - VERIFY GATE: run the check yourself, report PASS/FAIL with real output pasted.
  - HUMAN GATE: stop and ask; you do not continue until confirmed.

## Principle 2 — Simplicity First
Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked. No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested (in this repo that means:
  no pack registries, no plugin systems, no game engines, no UI policy editors, no
  escalation rosters).
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it. Test: "Would a senior engineer
  say this is overcomplicated?" If yes, simplify before showing me.

## Principle 3 — Surgical Changes
Touch only what you must. Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting. Don't refactor what isn't broken.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions YOUR change made unused. If you notice pre-existing
  dead code, mention it and move on — don't delete it unless asked.
- Two-track file ownership (§8) is strict. If a change requires touching the other
  track's files, stop and say so.
- The test: every changed line traces directly to the current phase.

## Principle 4 — Goal-Driven Execution
Define success criteria. Loop until verified.
- Open every phase by restating it as a plan of verifiable steps:
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
- Prefer "write the failing test, then make it pass" wherever feasible (state machine,
  event schema, eval scoring, SMS reply parsing).
- No faking: never present a stub as working logic. The only sanctioned stub is Track B's
  day-one event-stream stub (ARCHITECTURE.md §8), labeled and deleted at integration.
  If you cannot verify something live (Makers console, deploy, browser, a real phone),
  that is a HUMAN GATE — say exactly what I must do and what result to expect.

## Hard rules specific to this project
- ALL LLM calls go through llm_client.py → EdgeOne model gateway. If you find a call
  path that doesn't, that's a bug to flag, not to route around.
- Every meaningful action emits exactly one event per the §4 schema. The frontend is
  animated ONLY from real events. Never animate from timers or assumptions.
- The Commander chooses only among legal moves defined in root policy.json (states,
  transitions, decision points, retry caps, approval-forced action classes). Code
  validates the policy at boot (malformed → loud failure) and enforces it at runtime.
  Illegal LLM output → policy's deterministic default + commander_overruled event.
  Never let the LLM free-route. One policy file — no per-pack overrides, no UI editor.
- Two-track file ownership (§8) is strict. If a change requires touching the other
  track's files, stop and say so.
- NATIVE-FIRST: where Makers provides a capability (session storage, tracing, sandbox,
  gateway routing), use it instead of building our own. Hand-roll only when Phase 0
  recon showed the native path doesn't fit — and write the reason into ARCHITECTURE §7
  as part of the same change.
- EVIDENCE: no sponsor-integration claim goes in the demo without observable proof
  captured at §9.5. If you implement a §7 row, your verify gate includes producing
  its evidence.
- payload.summary is human-readable, one sentence — it becomes a speech bubble.

## Environment
- Platform: EdgeOne Makers (agent runtime + cloud functions + KV/Blob + static hosting).
  Phase 0 recon findings override any assumption in this file about platform mechanics.
- Secrets via .env locally / Makers console in prod. Never commit keys. Never print keys.

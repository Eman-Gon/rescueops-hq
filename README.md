# RescueOps HQ

**An agent harness you can watch, test, and text.**

A model is only the brain. RescueOps HQ builds the operating system around it:
memory, scoped context, policy-enforced safety controls, human approval, tool access,
observability, chaos testing, and measured evaluation.

Incident response is the proving ground. An Incident Commander dispatches five
specialists through:

```text
Triage → Diagnosis → Remediation → Verification → Postmortem
```

The Commander can make useful routing decisions, but only among legal moves defined in
`policy.json`. Code—not a prompt—enforces the safety envelope. Illegal decisions are
overruled and recorded.

> [ARCHITECTURE.md](ARCHITECTURE.md) is the project contract. If this README and the
> architecture disagree, the architecture wins.

## Why this project exists

Most agent demos show a model calling a tool. RescueOps HQ makes the surrounding harness
visible and testable:

- **Policy-bound autonomy:** the Commander chooses only from legal state transitions.
- **Progressive control:** safe actions execute automatically; risky actions require a
  human.
- **Append-only evidence:** every agent, model, tool, human, and chaos action emits an
  event.
- **Graceful failure:** operators can kill telemetry or the primary model and watch the
  system degrade or fail over.
- **Measured quality:** labeled scenarios score severity, diagnosis, remediation, and
  time-to-diagnosis.
- **Domain portability:** incident knowledge lives in data packs rather than orchestration
  code.

## System design

```text
                         RescueOps HQ

  React dashboard / Ops Floor / approval panel / chaos / eval
                              │
                       polls real events
                              ▼
  ┌──────────────────────────────────────────────────────────┐
  │                 EdgeOne Makers runtime                   │
  │                                                          │
  │  Incident Commander ── policy.json legal-move boundary   │
  │          │                                               │
  │          └─ Triage → Diagnosis → Remediation             │
  │                                  │                       │
  │                         risky action?                     │
  │                         yes ──► human gate                │
  │                                  │                       │
  │                         Verification → Postmortem         │
  │                                                          │
  │  Every model call ──► Makers model gateway               │
  │  Paused state     ──► Makers session store               │
  │  Events/evals     ──► Makers KV/Blob                     │
  │  Agent/tool work  ──► Makers tracing                     │
  └──────────────────────────────────────────────────────────┘
```

The dashboard, audit view, eval harness, and animated Ops Floor are consumers of the same
event stream. UI state must never be invented independently from pipeline activity.

## Safety model

The default policy gives the Commander four decision points:

1. After triage: fast-path a SEV-3 incident or dispatch deep diagnosis.
2. After diagnosis: dispatch remediation or escalate low-confidence findings.
3. After risky remediation: request approval; code makes this transition mandatory.
4. After failed verification: retry once or escalate, subject to the configured cap.

`run_until_approval()` and `resume_after_approval()` keep human wait time outside an HTTP
request. A paused incident can therefore survive a serverless boundary and resume after a
web or SMS decision.

## Event stream

Every meaningful action follows one envelope:

```json
{
  "seq": 41,
  "ts": "2026-07-03T21:04:11Z",
  "incident_id": "INC-3",
  "actor": "commander",
  "type": "commander_decision",
  "payload": {
    "summary": "Diagnosis confidence is high; dispatching remediation."
  },
  "trace_id": null
}
```

Events are ordered per incident. `payload.summary` is always a human-readable sentence
because it also becomes the Ops Floor speech bubble.

## Domain packs

Domain knowledge is data, not orchestration code:

```text
packs/
└── it-ops/
    ├── scenarios.json   # five labeled incidents and ground truth
    └── rubric.md        # severity definitions injected into triage
```

The planned complete pack contract also includes `playbook.json`, `tools.py`, and
`floor.json`. Security operations and supply-chain response are stretch packs after the
core IT-ops path is green.

Agents receive only observable incident data. `ground_truth` is reserved for the eval
harness and is never included in an agent prompt.

## EdgeOne Makers usage

| Makers capability | RescueOps responsibility |
|---|---|
| Agent runtime | Host the Commander and specialist crew |
| Model gateway | Route every LLM call, with primary/fallback handling |
| Session store | Persist paused approval state |
| KV / Blob | Store append-only events, incidents, and eval results |
| Sandboxed tools | Execute remediation actions with bounded access |
| Built-in tracing | Link agent/model/tool events to platform traces |
| Cloud functions | Expose incidents, events, approvals, chaos, eval, and SMS |
| Static hosting | Serve the React dashboard and Ops Floor |

No platform capability is claimed in the demo until it has observable production
evidence.

## Current build status

This repository is being migrated from an earlier RescueOps prototype. The target
architecture above is not yet fully shipped.

| Area | Status |
|---|---|
| Track A repository audit | Complete |
| IT-ops scenarios and rubric extracted into a pack | Complete |
| Central `llm_client.py` boundary | Complete |
| Makers primary/fallback adapter and fallback event | Implemented; live credential gate pending |
| Commander factory and `policy.json` state-machine core | Offline implementation tested; live pipeline wiring pending |
| Event envelope, validation, and gapless local sequencing | Implemented; complete pipeline emission and KV write path pending |
| Makers session/KV persistence | Pending Track B recon and integration |
| Production dashboard integration | Pending |
| SMS, Ops Floor, sec-ops pack | Stretch; not yet shipped |

Legacy TrueFoundry, Traceloop, SQLite, Railway, Streamlit, and nested CrewAI scaffold
files remain from the prior prototype. They are not the target architecture and will be
removed or replaced only in their gated migration phases.

## Repository map

| Path | Purpose |
|---|---|
| `ARCHITECTURE.md` | Single source of truth and cross-track contract |
| `CLAUDE.md` | Implementation principles, gates, and hard rules |
| `TRACK-A.md` | Agents and model-layer execution plan |
| `TRACK-B.md` | Makers platform and frontend execution plan |
| `DEMO-SCRIPT.md` | Three-minute demo beats and fallback plan |
| `agents.py` | Current five specialist Agent factories |
| `pipeline.py` | Progressive-autonomy pipeline |
| `llm_client.py` | Single Makers gateway model boundary |
| `events.py` | Track A event production helper |
| `schemas.py` | Structured Pydantic artifacts |
| `packs/it-ops/` | IT-ops scenarios and severity rubric |
| `api/` | Current FastAPI surface; Track B migration area |
| `frontend/` | Current React interface; Track B migration area |
| `tests/` | Track A refactor and model-failover tests |

## Local setup

Requirements:

- Python 3.12
- Node.js 20
- EdgeOne Makers model-gateway credentials

Create the environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.template .env
```

Configure `.env` with values from the Makers console:

```env
LLM_BASE_URL=<OpenAI-compatible gateway URL>
MAKERS_MODELS_KEY=<secret>
LLM_PRIMARY_MODEL=@makers/deepseek-v4-flash
LLM_FALLBACK_MODEL=<bound fallback model ID>
```

Never commit `.env` or paste the key into an issue, log, or chat.

Run the current backend and frontend:

```bash
./dev.sh
```

Or run them separately:

```bash
uvicorn api.server:app --reload --port 8000

cd frontend
npm install
npm run dev
```

Run tests:

```bash
python3 -m pytest -q
```

## Two-track development

Work is deliberately split across disjoint ownership:

- **Track A — agents and model layer:** specialists, Commander, state machine, model
  client, schemas, pack content, and event production.
- **Track B — platform and surface:** Makers deployment, cloud functions, storage,
  chaos/evaluation wiring, frontend, event consumption, SMS, and Ops Floor.

Both tracks work phase-by-phase. Each phase ends with automated verification and,
where specified, a human gate. Core integration happens only after the real event
producer and production event consumer are independently green.

## Demo thesis

Everyone can deploy an agent. RescueOps HQ demonstrates whether that agent can be
trusted:

1. Open a real incident.
2. Watch the Commander dispatch specialists under a visible policy.
3. Kill a telemetry source or primary model.
4. Inspect the resulting fallback and degradation events.
5. Pause on a risky fix and approve it from the web or phone.
6. Show measured results against labeled ground truth.
7. Follow an event into its Makers trace.

The harness—not the chat box—is the product.

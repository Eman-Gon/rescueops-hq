# How RescueOps Uses CrewAI

RescueOps is a **multi-agent incident-response system** built on CrewAI. Five specialist agents run in sequence, each producing a typed artifact (Pydantic model). A **CrewAI Flow** orchestrates the full pipeline from incident load through postmortem, with a human approval gate in the middle.

> For general CrewAI API reference, see [`CREWAI-DOCS.md`](CREWAI-DOCS.md). This document explains **how this project** uses CrewAI.

---

## High-level flow

```
run_incident(incident_id, chaos_config, approval_callback)
       │
       ▼
IncidentResponseFlow.kickoff()     ← CrewAI Flow (6 steps)
       │
       ├─ 1. load_and_prepare      ← load incident, apply chaos, compute confidence
       ├─ 2. run_crew              ← Crew: Triage + Diagnosis agents
       ├─ 3. remediate             ← Crew: Remediation agent (single-task)
       ├─ 4. approve               ← Human-in-the-loop (NOT an agent)
       ├─ 5. verify                ← Crew: Verification agent
       └─ 6. write_postmortem      ← Crew: Postmortem agent
       │
       ▼
RunResult (Pydantic) → Streamlit UI / audit log / evaluation
```

---

## The five agents

Defined in `agents.py`. Each is a CrewAI `Agent` with role, goal, backstory, and an LLM from `config.build_llm()`.

| # | Factory | Role | Output artifact |
|---|---|---|---|
| 1 | `build_triage_agent()` | Incident Triage Engineer | `TriageReport` |
| 2 | `build_diagnosis_agent()` | Root Cause Analyst (SRE) | `DiagnosisReport` |
| 3 | `build_remediation_agent()` | Remediation Lead | `RemediationPlan` |
| 4 | `build_verification_agent()` | Recovery Verification Engineer | `VerificationReport` |
| 5 | `build_postmortem_agent()` | Postmortem Writer | `PostmortemReport` |

Agents are **built fresh per run** — no shared state between incidents.

Example agent definition:

```python
from crewai import Agent
from config import build_llm

def build_triage_agent(model_id: str | None = None) -> Agent:
    return Agent(
        role="Incident Triage Engineer",
        goal="Make fast, calibrated first calls on production incident severity...",
        backstory="A senior on-call engineer with 10+ years triaging...",
        llm=build_llm(model_id=model_id),
        verbose=True,
    )
```

Pass `model_id=` to override the default LLM (used when chaos breaks the primary model).

---

## CrewAI primitives used

| Primitive | Where | Purpose |
|---|---|---|
| **`Agent`** | `agents.py` | Five specialist personas with LLMs |
| **`Task`** | `pipeline.py` | Per-stage prompts + `output_pydantic` for structured output |
| **`Crew`** | `pipeline.py` | Runs one or more agents/tasks sequentially |
| **`Process.sequential`** | `pipeline.py` | Tasks execute in order; later tasks can use `context=[earlier_task]` |
| **`Flow`** | `pipeline.py` | `IncidentResponseFlow` — event-driven pipeline across 6 steps |
| **`@start` / `@listen`** | `pipeline.py` | Flow step wiring (`load_and_prepare` → `run_crew` → …) |
| **`LLM`** | `config.py` | CrewAI LLM object routed through TrueFoundry gateway |

---

## How crews are assembled

### Triage + Diagnosis (one crew, two tasks)

In `run_crew`, both agents run together in a single sequential crew:

```python
triage_task = Task(
    description=_triage_prompt(self.state.obs),
    expected_output="Structured triage report...",
    agent=triage_agent,
    output_pydantic=TriageReport,
)

diagnosis_task = Task(
    description=_diagnosis_prompt(self.state.obs, confidence, coverage_note),
    expected_output="Structured diagnosis report...",
    agent=diagnosis_agent,
    output_pydantic=DiagnosisReport,
    context=[triage_task],   # diagnosis sees triage output
)

result = Crew(
    agents=[triage_agent, diagnosis_agent],
    tasks=[triage_task, diagnosis_task],
    process=Process.sequential,
    verbose=True,
).kickoff()
```

`context=[triage_task]` lets the diagnosis agent reason over the triage result without re-prompting manually.

### Remediation, Verification, Postmortem (one agent each)

These stages use a helper that wraps a single agent in a one-task crew:

```python
def _run_single_agent(agent, description, expected_output, output_pydantic):
    task = Task(
        description=description,
        expected_output=expected_output,
        agent=agent,
        output_pydantic=output_pydantic,
    )
    result = Crew(
        agents=[agent], tasks=[task],
        process=Process.sequential, verbose=True,
    ).kickoff()
    return getattr(result.tasks_output[0], "pydantic", None)
```

---

## Structured output (Pydantic)

Every agent task sets `output_pydantic=<SchemaClass>`. CrewAI asks the LLM for JSON matching the schema; results land in `result.tasks_output[n].pydantic`.

Schemas live in `schemas.py`:

- `TriageReport` — severity, customer_facing, summary, route_to, reason
- `DiagnosisReport` — root_cause, cited_evidence, confidence, reasoning
- `RemediationPlan` — safe[] and risky[] action lists
- `VerificationReport` — recovered, metric_name, observed_value, threshold
- `PostmortemReport` — summary, timeline, actions_taken, follow_ups

The full run is wrapped in `RunResult` — the **integration contract** between Track A (agents) and Track B (UI, audit, evaluation).

### Parse-error fallbacks

If an agent's structured output fails to parse, `pipeline.py` uses generic labeled fallbacks (`_fallback_plan()`, etc.) — never incident-specific canned answers. A parse failure is obvious in the UI and audit log.

---

## CrewAI Flow orchestration

`IncidentResponseFlow` extends `Flow[IncidentFlowState]`:

```python
class IncidentFlowState(BaseModel):
    run_id: str
    incident_id: str
    chaos_config: Optional[dict]
    obs: dict
    confidence: float
    triage: Optional[dict]
    diagnosis: Optional[dict]
    remediation: Optional[dict]
    approval: Optional[dict]
    verification: Optional[dict]
    postmortem: Optional[dict]
```

Flow steps:

| Step | Decorator | What happens |
|---|---|---|
| `load_and_prepare` | `@start()` | Load incident, apply chaos, compute confidence |
| `run_crew` | `@listen(load_and_prepare)` | Triage + Diagnosis crew |
| `remediate` | `@listen(run_crew)` | Remediation agent |
| `approve` | `@listen(remediate)` | **Human gate** — calls `approval_callback` |
| `verify` | `@listen(approve)` | Verification agent |
| `write_postmortem` | `@listen(verify)` | Postmortem agent |

State persists across steps via `self.state`. Each stage logs to the audit DB when Track B's `audit.py` is available.

### Public entrypoint

```python
def run_incident(
    incident_id: str,
    chaos_config: dict | None = None,
    approval_callback: Callable[[RemediationPlan], ApprovalDecision] | None = None,
) -> RunResult:
    flow = IncidentResponseFlow(approval_callback=approval_callback)
    flow.state.run_id = str(uuid.uuid4())
    flow.state.incident_id = incident_id
    flow.state.chaos_config = chaos_config
    flow.kickoff()
    return RunResult(...)
```

Track B (`app.py`, `evaluation.py`) calls this function — it never imports CrewAI directly.

---

## What CrewAI does *not* do here

| Concern | Owner | Why |
|---|---|---|
| **Confidence score** | `pipeline.py` (`_compute_confidence`) | Computed deterministically from telemetry coverage — not by the LLM |
| **Human approval** | `app.py` / `main.py` callback | Governance gate outside the agent loop |
| **Chaos injection** | `chaos.py` | Degrades telemetry before agents see it |
| **Audit logging** | `audit.py` | Append-only SQLite timeline |
| **Evaluation scoring** | `evaluation.py` | Compares outputs to ground truth |
| **LLM routing** | `config.py` + TrueFoundry | CrewAI calls `build_llm()`; gateway handles models |

This separation is intentional: agents reason over incidents; the platform enforces governance and measurement.

---

## Confidence: pipeline vs. agent

The diagnosis agent may produce a confidence field, but the pipeline **overrides** it:

```python
diagnosis = raw_diag.model_copy(update={"confidence": self.state.confidence})
```

`_compute_confidence()` penalizes missing telemetry:

| Missing source | Penalty |
|---|---|
| logs | −0.30 |
| metrics | −0.40 |
| deploys | −0.20 |

When chaos disables sources in the UI, confidence drops automatically — visible in the Streamlit diagnosis panel.

---

## How to run CrewAI in this project

### Streamlit (demo UI)

```bash
.venv/bin/streamlit run app.py
```

Select an incident → configure chaos/governance → **RUN INCIDENT**.

### CLI

```bash
python main.py                                          # INC-001, interactive approval
python main.py --incident INC-003-redis-cache-outage
python main.py --auto-approve
```

### Evaluation harness

```bash
python -c "import evaluation; print(evaluation.evaluate_all())"
```

Runs all 5 incidents through `run_incident()` with auto-approve — agents never see ground truth labels.

### Pre-baked demo

```bash
python seed_demo.py
```

Runs a real pipeline call, saves `demo_example.json` for instant Streamlit load.

---

## How to prove CrewAI is running

1. **Verbose logs** — every agent has `verbose=True`; crew execution prints to the terminal during `run_incident()`.
2. **Audit timeline** — `rescueops_audit.db` records stages: `start` → `triage` → `diagnosis` → `remediation_plan` → `approval` → `verification` → `postmortem` → `complete`.
3. **Structured artifacts** — each stage returns a distinct Pydantic object visible in the Streamlit timeline.
4. **Live run** — click **RUN INCIDENT** in the app; the spinner runs the full Flow (~30–60s with real LLM calls).

---

## File map

| File | CrewAI role |
|---|---|
| `agents.py` | Agent factory — 5 `Agent` definitions |
| `pipeline.py` | `Flow`, `Crew`, `Task`, prompts, `run_incident()` |
| `config.py` | `build_llm()` → CrewAI `LLM` via TrueFoundry |
| `schemas.py` | `output_pydantic` target models |
| `app.py` | Calls `run_incident()`; renders agent timeline |
| `evaluation.py` | Batch-runs `run_incident()` for scoring |
| `main.py` | CLI wrapper with interactive approval |

---

## Design choices (hackathon → production)

| Choice | Rationale |
|---|---|
| **Flow over a single mega-crew** | Approval gate and audit logging sit between agent stages |
| **Separate crews per late stage** | Remediation/verify/postmortem only run after prior artifacts exist |
| **`output_pydantic` everywhere** | Typed artifacts for UI, evaluation, and audit — no free-text parsing |
| **Fresh agents per run** | No cross-incident memory leaks or stale context |
| **Deterministic confidence** | "Measured confidence, not vibes" — aligns with judging criteria |

For production you'd add CrewAI tools (PagerDuty, kubectl, runbooks), memory/knowledge sources, and guardrails — the Flow + schema contract stays the same.

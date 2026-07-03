# How RescueOps Uses TrueFoundry

RescueOps routes **every agent LLM call** through the **TrueFoundry AI Gateway**. No CrewAI agent talks to xAI, Anthropic, or Google directly. The gateway owns authentication, model routing, failover, and observability.

---

## Role in the architecture

```
Streamlit UI / CLI
       │
       ▼
  pipeline.py  (CrewAI Flow)
       │
       ▼
  agents.py    (5 CrewAI Agents)
       │
       ▼
  config.py    build_llm()
       │
       ▼
  TrueFoundry AI Gateway  ──►  Grok (primary)
       │                       Claude (fallback)
       │                       Gemini (fallback)
       ▼
  TrueFoundry Traces / Logs
```

**What TrueFoundry provides in this project:**

| Capability | How RescueOps uses it |
|---|---|
| **Single API surface** | One base URL + one API key for all models |
| **Model aliases** | `GROK_MODEL_ID`, `CLAUDE_MODEL_ID`, `GEMINI_MODEL_ID` are gateway-configured IDs, not raw vendor endpoints |
| **Failover** | Gateway can route to fallback models when the primary is unavailable |
| **Observability** | Every LLM call appears in TrueFoundry Traces (latency, tokens, cost) |
| **Production path** | README calls out guardrails (PII/secret scrubbing) as a future production step |

---

## Configuration

Copy `.env.example` to `.env` and fill in your tenant values:

```bash
TFY_GATEWAY_BASE_URL=https://gateway.truefoundry.ai/api/llm
TFY_API_KEY=<your-gateway-api-key>

# Model IDs as aliased in your TrueFoundry gateway dashboard
GROK_MODEL_ID=xai/grok-3
CLAUDE_MODEL_ID=anthropic/claude-sonnet-4-5
GEMINI_MODEL_ID=google-gemini/gemini-2.5-flash-lite
```

`config.py` auto-detects gateway mode when `TFY_GATEWAY_BASE_URL` and `TFY_API_KEY` are set and the URL is not a placeholder (`<...>`).

In gateway mode it also sets:

```python
os.environ["OPENAI_API_KEY"] = GATEWAY_API_KEY
os.environ["OPENAI_API_BASE"] = GATEWAY_BASE_URL
```

CrewAI's `LLM` class uses LiteLLM under the hood, which speaks the OpenAI-compatible API that TrueFoundry exposes.

---

## The single integration point: `build_llm()`

All LLM access goes through `config.build_llm()`:

```python
from crewai import LLM

def build_llm(model_id: str | None = None, temperature: float = 0.2) -> LLM:
    mid = model_id or GROK_MODEL_ID
    return LLM(
        model=f"openai/{mid}",
        base_url=GATEWAY_BASE_URL,
        api_base=GATEWAY_BASE_URL,
        api_key=GATEWAY_API_KEY,
        temperature=temperature,
    )
```

**Key details:**

- `model=f"openai/{mid}"` — tells LiteLLM to use the OpenAI-compatible provider against the gateway URL.
- `mid` defaults to `GROK_MODEL_ID` (primary).
- Passing `model_id=` overrides the default — used for chaos failover (see below).
- Temperature is fixed at `0.2` for consistent, low-variance incident responses.

Every agent in `agents.py` receives `llm=build_llm(model_id=model_id)`.

---

## Model routing and fallbacks

### Normal run

All five agents call through the gateway with the **primary model** (`GROK_MODEL_ID`).

### Chaos: `break_primary_model`

When the Streamlit chaos console checks **"Break primary model"**, the pipeline does **not** call xAI directly. Instead, `pipeline.py` passes the Claude fallback ID into every agent:

```python
def _fallback_model(self) -> Optional[str]:
    if self.state.chaos_config and self.state.chaos_config.get("break_primary_model"):
        return CLAUDE_MODEL_ID
    return None

agent = build_remediation_agent(model_id=self._fallback_model())
```

The request still goes to `https://gateway.truefoundry.ai/api/llm/` — only the `model` field in the payload changes. This demonstrates **gateway-level resilience** without bypassing governance.

> **Note:** Automatic gateway failover (Grok down → Claude without app code) is configured in the TrueFoundry dashboard. The chaos flag simulates a primary-model failure at the application layer so the demo can show explicit fallback routing.

---

## What is *not* routed through TrueFoundry

| Component | Routing |
|---|---|
| **Agent LLM calls** | TrueFoundry gateway |
| **Voice narration** (`voice.py`) | Direct xAI TTS API (optional stretch feature) |
| **Telemetry / incidents** | Local JSON (`incidents.json`) — synthetic, not live |
| **Audit log** | Local SQLite (`rescueops_audit.db`) |

---

## How to prove the gateway is connected

### 1. Quick Python smoke test

```bash
.venv/bin/python -c "
import config
llm = config.build_llm()
print(llm.call('Reply with exactly: CREWAI_OK'))
"
```

Expected output: `CREWAI_OK`

### 2. Inspect the outbound request

Enable LiteLLM debug to see the physical POST target:

```bash
.venv/bin/python -c "
import litellm; litellm._turn_on_debug()
import config
config.build_llm().call('Reply with exactly: PROOF_OK')
" 2>&1 | grep 'POST Request'
```

You should see:

```
POST Request Sent from LiteLLM:
https://gateway.truefoundry.ai/api/llm/
```

### 3. TrueFoundry Traces (best for judges)

1. Open your TrueFoundry tenant → **Gateway** → **Traces** (or Logs).
2. Run an incident in the Streamlit app (`RUN INCIDENT`).
3. Refresh the dashboard — a new trace appears with model, latency, token usage, and cost.

### 4. Live demo: chaos failover

1. In the sidebar, check **Break primary model**.
2. Run an incident.
3. Show the trace switched from Grok to Claude while still hitting the same gateway URL.

---

## Sharing credentials with a partner

You can share **one gateway** for the hackathon:

- Same `TFY_GATEWAY_BASE_URL` and `TFY_API_KEY` in both `.env` files.
- Model IDs must match what's configured in the shared gateway tenant.

Each developer still runs their own local Streamlit app and audit DB. Traces aggregate in the shared TrueFoundry project.

---

## Development fallback (no gateway)

If `TFY_GATEWAY_BASE_URL` is missing or still contains `<` placeholders, `config.py` falls back to **direct Anthropic**:

```python
LLM(model=f"anthropic/{CLAUDE_MODEL_ID}", api_key=ANTHROPIC_API_KEY)
```

This is for local dev only. Production/demo mode should always use the TrueFoundry gateway.

---

## Files to read

| File | Purpose |
|---|---|
| `config.py` | Gateway detection, `build_llm()`, env loading |
| `agents.py` | Each agent wires `llm=build_llm(...)` |
| `pipeline.py` | Chaos failover passes `CLAUDE_MODEL_ID` to agents |
| `chaos.py` | Documents that `break_primary_model` is handled by the pipeline, not telemetry |
| `.env.example` | Required environment variables |
| `app.py` | Chaos console UI; shows "gateway failing over" banner |

---

## Production path (from README / kickoff)

What you have now vs. what you'd add for real production:

| Today (hackathon) | Production |
|---|---|
| Gateway routing + traces | Same |
| Synthetic incidents | Live telemetry (Datadog, PagerDuty, etc.) |
| Local SQLite audit log | Centralized audit store |
| Chaos toggles in UI | Controlled chaos in staging |
| — | TrueFoundry **guardrails** (PII/secret scrubbing on all LLM I/O) |
| — | Rate limits and spend caps per team |

The gateway integration you have is the foundation — agents never need to change when you swap synthetic data for live telemetry.

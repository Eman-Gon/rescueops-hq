"""Central config: loads .env, builds LLMs, and initializes TrueFoundry tracing.

Supports two modes:
  1. TrueFoundry gateway (production) — set TFY_GATEWAY_BASE_URL + TFY_API_KEY in .env
  2. Direct Anthropic (development) — set ANTHROPIC_API_KEY in .env

build_llm() picks the right mode automatically based on which env vars are present.

Importing this module also initializes Traceloop tracing once (best-effort) so
every CrewAI run shows up in TrueFoundry's tracing UI. Tracing failures never
break a pipeline run — init is wrapped and degrades silently.
"""
import os
from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

# ── Detect mode ──
_TFY_URL = os.environ.get("TFY_GATEWAY_BASE_URL", "")
_TFY_KEY = os.environ.get("TFY_API_KEY", "")
_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# TrueFoundry mode: real gateway URL is set (not a placeholder)
_USE_GATEWAY = bool(_TFY_URL and _TFY_KEY and "<" not in _TFY_URL)

if _USE_GATEWAY:
    GATEWAY_BASE_URL = _TFY_URL
    GATEWAY_API_KEY = _TFY_KEY
    GROK_MODEL_ID = os.environ.get("GROK_MODEL_ID", "")
    CLAUDE_MODEL_ID = os.environ.get("CLAUDE_MODEL_ID", "claude-3-5-sonnet-20260319")
    GEMINI_MODEL_ID = os.environ.get("GEMINI_MODEL_ID", "")
    os.environ["OPENAI_API_KEY"] = GATEWAY_API_KEY
    os.environ["OPENAI_API_BASE"] = GATEWAY_BASE_URL
else:
    # Direct Anthropic mode
    GATEWAY_BASE_URL = ""
    GATEWAY_API_KEY = ""
    GROK_MODEL_ID = ""
    CLAUDE_MODEL_ID = "claude-sonnet-4-20250514"
    GEMINI_MODEL_ID = ""


def build_llm(model_id: str | None = None, temperature: float = 0.2) -> LLM:
    """Return a CrewAI LLM.

    In gateway mode: routes through TrueFoundry.
    In direct mode: calls Anthropic API directly via LiteLLM.
    """
    if _USE_GATEWAY:
        mid = model_id or GROK_MODEL_ID
        return LLM(
            model=f"openai/{mid}",
            base_url=GATEWAY_BASE_URL,
            api_base=GATEWAY_BASE_URL,
            api_key=GATEWAY_API_KEY,
            temperature=temperature,
        )

    # Direct Anthropic — no gateway needed
    return LLM(
        model=f"anthropic/{CLAUDE_MODEL_ID}",
        api_key=_ANTHROPIC_KEY,
        temperature=temperature,
    )


# ── TrueFoundry tracing (Traceloop) ──────────────────────────────────────────
# Judged observability pillar: every crew run is traced into TrueFoundry.
# Best-effort and idempotent — a bad endpoint or missing token never breaks a run.
# All values are .env-overridable; defaults are derived from the gateway creds.
_TRACING_ENABLED = False


def _tracing_endpoint() -> str:
    """Base host for tracing. Defaults to the gateway host (strip any /api/... path)."""
    explicit = os.environ.get("TFY_TRACING_ENDPOINT", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if _TFY_URL:
        # https://gateway.truefoundry.ai/api/llm  ->  https://gateway.truefoundry.ai
        from urllib.parse import urlparse
        p = urlparse(_TFY_URL)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    return ""


def init_tracing() -> bool:
    """Initialize Traceloop -> TrueFoundry tracing once. Returns True if it initialized.

    Never raises: any failure (import, network, auth) is swallowed so a demo run
    is never blocked by tracing being misconfigured.
    """
    global _TRACING_ENABLED
    if _TRACING_ENABLED:
        return True
    if os.environ.get("TFY_TRACING_DISABLED", "").lower() in ("1", "true", "yes"):
        return False

    endpoint = _tracing_endpoint()
    token = os.environ.get("TFY_PAT_TOKEN", "").strip() or _TFY_KEY
    project = os.environ.get("TFY_TRACING_PROJECT", "rescueops").strip() or "rescueops"
    if not (endpoint and token):
        return False

    try:
        # The gateway exposes a traces endpoint only — disable the metrics and
        # logging OTLP exporters so they don't 404 noisily on every run.
        os.environ.setdefault("TRACELOOP_METRICS_ENABLED", "false")
        os.environ.setdefault("TRACELOOP_LOGGING_ENABLED", "false")

        from traceloop.sdk import Traceloop

        Traceloop.init(
            app_name="rescueops",
            api_endpoint=f"{endpoint}/api/tracing",
            headers={
                "Authorization": f"Bearer {token}",
                "TFY-Tracing-Project": project,
            },
            disable_batch=True,  # flush per-span so short demo runs show up immediately
        )
        _TRACING_ENABLED = True
        print(f"[tracing] Traceloop -> {endpoint}/api/tracing  (project: {project})")
    except Exception as exc:  # noqa: BLE001 — tracing must never break a run
        print(f"[tracing] disabled — init failed: {exc}")
        _TRACING_ENABLED = False
    return _TRACING_ENABLED


# Initialize at import time so any entrypoint (CLI, Streamlit, eval) gets tracing.
init_tracing()

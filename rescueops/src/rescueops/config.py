"""TrueFoundry gateway LLM config for CrewAI deploy scaffold.

All agent LLM calls route through TFY_GATEWAY_BASE_URL + TFY_API_KEY.
No direct OpenAI/Anthropic vendor calls in gateway mode.
"""
import os

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

_TFY_URL = os.environ.get("TFY_GATEWAY_BASE_URL", "")
_TFY_KEY = os.environ.get("TFY_API_KEY", "")
_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_USE_GATEWAY = bool(_TFY_URL and _TFY_KEY and "<" not in _TFY_URL)

if _USE_GATEWAY:
    GATEWAY_BASE_URL = _TFY_URL
    GATEWAY_API_KEY = _TFY_KEY
    GROK_MODEL_ID = os.environ.get("GROK_MODEL_ID", "")
    CLAUDE_MODEL_ID = os.environ.get("CLAUDE_MODEL_ID", "claude-3-5-sonnet-20260319")
    GEMINI_MODEL_ID = os.environ.get("GEMINI_MODEL_ID", "")
else:
    GATEWAY_BASE_URL = ""
    GATEWAY_API_KEY = ""
    GROK_MODEL_ID = ""
    CLAUDE_MODEL_ID = "claude-sonnet-4-20250514"
    GEMINI_MODEL_ID = ""


def build_llm(model_id: str | None = None, temperature: float = 0.2) -> LLM:
    """Return a CrewAI LLM routed through TrueFoundry (or direct Anthropic fallback)."""
    if _USE_GATEWAY:
        mid = model_id or GROK_MODEL_ID
        return LLM(
            model=f"openai/{mid}",
            base_url=GATEWAY_BASE_URL,
            api_base=GATEWAY_BASE_URL,
            api_key=GATEWAY_API_KEY,
            temperature=temperature,
        )

    return LLM(
        model=f"anthropic/{CLAUDE_MODEL_ID}",
        api_key=_ANTHROPIC_KEY,
        temperature=temperature,
    )

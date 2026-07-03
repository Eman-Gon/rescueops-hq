"""Optional voice augmentation for the approval step (Track B, B5 stretch).

The approval BUTTON is always the primary control — voice never replaces it and
the demo must never depend on the mic. Everything here is best-effort: if there is
no API key, no network, or the audio tooling is missing, every function degrades
to a silent no-op and returns False/None. Nothing here ever raises.

speak() prefers Grok TTS via the xAI API (direct, not through the gateway), and
falls back to the macOS `say` command so the feature still works in the demo room.
"""
import os
import shutil
import subprocess
import tempfile

_XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1")
_XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
_XAI_TTS_MODEL = os.environ.get("XAI_TTS_MODEL", "grok-tts")
_XAI_TTS_VOICE = os.environ.get("XAI_TTS_VOICE", "alloy")


def available() -> bool:
    """True if any speech backend is usable (xAI key present, or macOS `say`)."""
    return bool(_XAI_API_KEY) or shutil.which("say") is not None


def _speak_xai(text: str) -> bool:
    if not _XAI_API_KEY:
        return False
    try:
        from openai import OpenAI

        client = OpenAI(base_url=_XAI_BASE_URL, api_key=_XAI_API_KEY)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        resp = client.audio.speech.create(model=_XAI_TTS_MODEL, voice=_XAI_TTS_VOICE, input=text)
        resp.stream_to_file(path)
        return _play(path)
    except Exception:
        return False


def _speak_say(text: str) -> bool:
    say = shutil.which("say")
    if not say:
        return False
    try:
        subprocess.run([say, text], check=True, timeout=30)
        return True
    except Exception:
        return False


def _play(path: str) -> bool:
    player = shutil.which("afplay") or shutil.which("ffplay")
    if not player:
        return False
    try:
        args = [player, path] if player.endswith("afplay") else [player, "-nodisp", "-autoexit", path]
        subprocess.run(args, check=True, timeout=60)
        return True
    except Exception:
        return False


def speak(text: str) -> bool:
    """Speak `text` aloud. Returns True if audio played, False otherwise. Never raises."""
    if not text:
        return False
    return _speak_xai(text) or _speak_say(text)


def approval_prompt(diagnosis_summary: str, risky_count: int) -> str:
    """Build the spoken approval prompt from the diagnosis."""
    plural = "action" if risky_count == 1 else "actions"
    return (
        f"Diagnosis: {diagnosis_summary}. "
        f"There {'is' if risky_count == 1 else 'are'} {risky_count} risky {plural} "
        f"awaiting your approval. Please approve or deny."
    )

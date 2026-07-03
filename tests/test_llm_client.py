from crewai import LLM

import llm_client
from agents import build_commander_agent
from events import clear_events, list_events


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("MAKERS_MODELS_KEY", "test-key")
    monkeypatch.setenv("LLM_PRIMARY_MODEL", "@makers/primary")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "@makers/fallback")


def test_primary_failure_retries_fallback_once_and_emits_event(monkeypatch) -> None:
    _configure(monkeypatch)
    calls = []

    def fake_call(self, *args, **kwargs):
        calls.append(self.model)
        if self.model == "openai/@makers/primary":
            raise ConnectionError("primary unavailable")
        return "fallback response"

    monkeypatch.setattr(LLM, "call", fake_call)
    clear_events()
    llm_client.begin_model_run("INC-TEST")
    model = llm_client.build_llm()

    assert model.call("hello") == "fallback response"
    assert calls == ["openai/@makers/primary", "openai/@makers/fallback"]
    events = list_events("INC-TEST")
    assert len(events) == 1
    assert events[0]["type"] == "model_fallback"
    assert events[0]["payload"]["summary"].endswith(".")
    assert events[0]["trace_id"] is None


def test_fallback_circuit_is_shared_across_models(monkeypatch) -> None:
    _configure(monkeypatch)
    calls = []

    def fake_call(self, *args, **kwargs):
        calls.append(self.model)
        return "ok"

    monkeypatch.setattr(LLM, "call", fake_call)
    clear_events()
    llm_client.begin_model_run("INC-CHAOS", force_primary_failure=True)
    first = llm_client.build_llm()
    second = llm_client.build_llm()

    assert first.call("first") == "ok"
    assert second.call("second") == "ok"
    assert calls == ["openai/@makers/fallback", "openai/@makers/fallback"]
    assert len(list_events("INC-CHAOS")) == 1


def test_missing_gateway_setting_fails_clearly(monkeypatch) -> None:
    for name in (
        "LLM_BASE_URL",
        "MAKERS_MODELS_KEY",
        "LLM_PRIMARY_MODEL",
        "LLM_FALLBACK_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    llm_client.begin_model_run("INC-CONFIG")
    try:
        llm_client.build_llm()
    except llm_client.LLMConfigurationError as error:
        assert "Missing LLM_BASE_URL" in str(error)
    else:
        raise AssertionError("missing Makers configuration should fail")


def test_commander_uses_the_central_gateway_client(monkeypatch) -> None:
    _configure(monkeypatch)
    llm_client.begin_model_run("INC-COMMANDER")

    commander = build_commander_agent()

    assert isinstance(commander.llm, llm_client.GatewayLLM)
    assert commander.llm.model == "openai/@makers/primary"

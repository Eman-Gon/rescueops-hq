from pathlib import Path

import incidents


ROOT = Path(__file__).parents[1]


def test_it_ops_pack_loads_all_scenarios_and_rubric() -> None:
    scenarios = incidents.load_incidents()
    rubric = incidents.load_rubric()

    assert len(scenarios) == 5
    assert {scenario["id"] for scenario in scenarios} == {
        "INC-001-checkout-db-pool",
        "INC-002-payment-latency-baddeploy",
        "INC-003-redis-cache-outage",
        "INC-004-autoscaler-underprovisioned",
        "INC-005-expired-api-key",
    }
    assert all(level in rubric for level in ("SEV-1", "SEV-2", "SEV-3"))


def test_active_pipeline_uses_only_llm_client_boundary() -> None:
    agents_source = (ROOT / "agents.py").read_text()
    pipeline_source = (ROOT / "pipeline.py").read_text()

    assert "from llm_client import build_llm" in agents_source
    assert "from llm_client import begin_model_run" in pipeline_source
    assert "from config import" not in agents_source
    assert "from config import" not in pipeline_source


def test_severity_definitions_live_only_in_pack() -> None:
    agents_source = (ROOT / "agents.py").read_text()
    pipeline_source = (ROOT / "pipeline.py").read_text()

    assert "SEV-1 =" not in agents_source
    assert "SEV-1 =" not in pipeline_source

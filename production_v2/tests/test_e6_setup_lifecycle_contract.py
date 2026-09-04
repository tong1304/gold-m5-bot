from types import SimpleNamespace

import production_v2.app as app


def test_current_opportunity_input_preserves_setup_thesis(monkeypatch):
    engines = [
        SimpleNamespace(engine_id="E6", output={
            "setup": "LIQUIDITY_RESPONSE",
            "setup_state": "SETUP_THESIS",
            "opportunity_stage": "SETUP_THESIS",
            "state": "SETUP_THESIS",
            "direction": "BUY",
            "trade_ready": False,
            "gate_passed": False,
            "watch_only": False,
            "missing_proof": ["E7_CONFIRMATION"],
        }),
        SimpleNamespace(engine_id="E7", output={"confirmation_state": "PENDING"}),
        SimpleNamespace(engine_id="E8", output={"economic_state": "NOT_APPLICABLE"}),
        SimpleNamespace(engine_id="E9", output={"decision": "NO_TRADE"}),
    ]
    result = SimpleNamespace(engines=engines, decision="NO_TRADE", gate_passed=False)
    monkeypatch.setattr(app, "reconcile_causal_evidence", lambda _engines: {"state": "NO_SETUP", "direction": "NEUTRAL", "wait_for": []})
    current = app._current_opportunity_input(result, "2026-09-04T11:00:00Z")
    assert current["candidate"] is True
    assert current["direction"] == "BUY"
    assert current["setup"] == "LIQUIDITY_RESPONSE"
    assert current["thesis_status"] == "SETUP_THESIS"
    assert current["lifecycle_source"] == "E6_SETUP"
    assert "E7_CONFIRMATION" in current["wait_for"]

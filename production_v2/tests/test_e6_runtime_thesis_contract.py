from production_v2.contracts import EngineResult
from production_v2.e6_runtime_authority import _normalize_watch_semantics


def test_runtime_membrane_preserves_surviving_setup_thesis():
    output = {
        "state": "SETUP_THESIS",
        "setup": "LIQUIDITY_RESPONSE",
        "candidate_type": "SETUP_CANDIDATE",
        "direction": "BUY",
        "thesis_direction": "BUY",
        "thesis_status": "FORMING",
        "watch_only": False,
        "trade_ready": False,
        "gate_passed": False,
        "finding": "BUY liquidity response setup is forming.",
        "reason_codes": ["E7_CONFIRMATION"],
    }
    normalized = _normalize_watch_semantics(output)
    assert normalized["setup"] == "LIQUIDITY_RESPONSE"
    assert normalized["candidate_type"] == "SETUP_CANDIDATE"
    assert normalized["watch_only"] is False
    assert normalized["state"] == "SETUP_THESIS"

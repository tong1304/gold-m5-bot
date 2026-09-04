from types import SimpleNamespace

from production_v2.contracts import EngineResult
from production_v2 import e6_runtime_authority


def test_runtime_authority_rewrites_legacy_no_setup_finding_when_watch_is_preserved():
    legacy_watch = EngineResult(
        "E6", "E6", False, 52.0,
        {"setup": "OPPORTUNITY_WATCH", "candidate_type": "OPPORTUNITY_CANDIDATE", "direction": "BUY", "stage": "FORMING", "watch_only": True, "trade_ready": False, "gate_passed": False, "finding": "No causal setup hypothesis survives current closed-candle evidence.", "missing_proof": ["E6_CAUSAL_SETUP_PROOF", "E7_CONFIRMATION"], "reason_codes": ["E2_OPPORTUNITY_CONFIRMATION"]}, (),
    )
    fake_module = SimpleNamespace(analyze_e6=lambda market_data, upstream: legacy_watch)
    e6_runtime_authority.install(fake_module)
    result = fake_module.analyze_e6({"bars": []}, {})
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert result.output["watch_only"] is True
    assert "No causal setup hypothesis survives" not in result.output["finding"]
    assert "opportunity" in result.output["finding"].lower()
    assert "not yet proven" in result.output["finding"].lower()


def test_runtime_authority_never_leaves_stale_professional_reasoning_on_concrete_e6_thesis():
    concrete = EngineResult(
        "E6", "E6", False, 76.0,
        {"setup": "LIQUIDITY_RESPONSE", "setup_family": "LIQUIDITY_RESPONSE", "candidate_type": "SETUP_CANDIDATE", "direction": "SELL", "state": "THESIS_CONTESTED", "setup_state": "THESIS_CONTESTED", "thesis_status": "CONTESTED", "watch_only": False, "trade_ready": False, "gate_passed": False, "finding": "SELL setup thesis is contested; confirmation/economics are not yet proven.", "thesis": "SELL causal setup thesis is established from E1-E5; E7/E8 proof remains pending.", "missing_proof": ["E2_OPPORTUNITY_CONFIRMATION", "E7_CONFIRMATION"], "professional_reasoning": {"conclusion": "No causal setup hypothesis survives current closed-candle evidence.", "hypothesis": ""}}, (),
    )
    fake_module = SimpleNamespace(analyze_e6=lambda market_data, upstream: concrete)
    e6_runtime_authority.install(fake_module)
    result = fake_module.analyze_e6({"bars": []}, {})
    reasoning = result.output["professional_reasoning"]
    assert "No causal setup hypothesis survives" not in reasoning["conclusion"]
    assert "SELL setup thesis is contested" in reasoning["conclusion"]
    assert reasoning["hypothesis"] == concrete.output["thesis"]
    assert reasoning["missing_evidence"] == concrete.output["missing_proof"]

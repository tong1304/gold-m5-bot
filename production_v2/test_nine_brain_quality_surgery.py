from production_v2.nine_brain_surgery import harden_all, harden_engine


def test_all_nine_have_professional_contract_and_quality():
    outputs = {f"E{i}": {"confidence": 0.8} for i in range(1, 10)}
    hardened = harden_all(outputs)
    assert tuple(hardened) == tuple(f"E{i}" for i in range(1, 10))
    for engine_id, output in hardened.items():
        assert output["professional_contract"]["engine"] == engine_id
        assert output["professional_contract"]["closed_candle_only"] is True
        assert "evidence_quality" in output
        assert output["evidence_quality"]["score"] <= 80.0


def test_future_or_lookahead_evidence_blocks_quality_gate():
    output = harden_engine("E7", {"confidence": 0.95, "reasons": ["LOOKAHEAD"]})
    assert output["professional_contract"]["gate_state"] == "BLOCKED"
    assert output["evidence_quality"]["band"] == "LOW"


def test_pending_e4_auction_never_becomes_ready():
    output = harden_engine("E4", {"confidence": 0.95, "auction_state": "PENDING", "response_actor": "BUYERS"})
    assert output["professional_contract"]["gate_state"] == "PENDING"
    assert output["auction_confirmation_proven"] is False
    assert output["auction_confirmation_pending"] is True


def test_e2_direction_is_not_authoritative_until_confirmed():
    output = harden_engine("E2", {"confidence": 0.9, "direction": "SELL", "opportunity_maturity": "DEVELOPING"})
    assert output["direction_for_market_control"] == "NEUTRAL"
    assert output["directional_claim_authority"] == "E2_OPPORTUNITY_ONLY"


def test_active_invalidation_blocks_even_with_high_confidence():
    output = harden_engine("E8", {"confidence": 0.99, "active_invalidations": ["INVALID_RISK_GEOMETRY"]})
    assert output["professional_contract"]["gate_state"] == "BLOCKED"
    assert output["professional_contract"]["active_invalidated"] is True

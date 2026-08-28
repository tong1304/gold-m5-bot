import importlib


def _module():
    return importlib.import_module("production_v2.e4_brain")


def _bars(n=60, base=100.0):
    return [
        {"open": base, "high": base + 1.0, "low": base - 1.0, "close": base + 0.2, "closed": True}
        for _ in range(n)
    ]


def test_e4_does_not_create_a_liquidity_level_from_a_pivot_confirmed_by_the_event_candle():
    mod = _module()
    bars = _bars()
    bars[56] = {"open": 100.0, "high": 105.0, "low": 99.0, "close": 100.0, "closed": True}
    bars[57] = {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2, "closed": True}
    bars[58] = {"open": 100.2, "high": 106.0, "low": 99.8, "close": 105.8, "closed": True}
    bars[59] = {"open": 105.8, "high": 106.2, "low": 105.2, "close": 105.9, "closed": True}
    result = mod.analyze_e4(bars)
    event = result["event"]
    assert not (event["index"] == 58 and event["zone"] and event["zone"]["price"] >= 104.0)


def test_e4_never_promotes_current_candle_to_confirmed_auction():
    mod = _module()
    bars = _bars()
    bars[-1] = {"open": 100.0, "high": 104.0, "low": 99.8, "close": 100.2, "closed": True}
    result = mod.analyze_e4(bars)
    assert result["auction"]["confirmed"] is False
    assert result["auction_state"] in {"UNRESOLVED", "ACCEPTANCE_PENDING", "REJECTION_PENDING", "INTERACTION_PENDING"}


def test_e4_dispatcher_uses_v23_and_keeps_decision_authority_with_e9():
    from production_v2.engines import run_engine
    result = run_engine("E4", {"bars": _bars()}, None)
    assert result.output["architecture"] == "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V23"
    assert result.output["reasoning_role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert result.output["decision"] is None
    assert result.output["gate"] is None
    assert result.output["decision_authority"] == "E9_ONLY"
    assert result.output["evidence"]["decisions_used"] is False
    assert result.output["evidence"]["gates_used"] is False
    assert result.output["evidence"]["scores_used"] is False


def test_e4_exposes_direct_observations_and_audit_contract():
    mod = _module()
    result = mod.analyze_e4(_bars())
    assert result["observations"]
    assert result["audit"]["closed_candle_only"] is True
    assert result["audit"]["no_lookahead"] is True
    assert result["professional_reasoning"]["actor_identification"] == "INFERENCE_FROM_OHLC_ONLY"

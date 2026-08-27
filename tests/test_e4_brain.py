import importlib


def _module():
    return importlib.import_module("production_v2.e4_brain")


def _bars(n=60, base=100.0):
    return [
        {"open": base, "high": base + 1.0, "low": base - 1.0, "close": base + 0.2}
        for _ in range(n)
    ]


def test_e4_does_not_create_a_liquidity_level_from_a_pivot_confirmed_by_the_event_candle():
    mod = _module()
    bars = _bars()
    bars[56] = {"open": 100.0, "high": 105.0, "low": 99.0, "close": 100.0}
    bars[57] = {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2}
    bars[58] = {"open": 100.2, "high": 106.0, "low": 99.8, "close": 105.8}
    bars[59] = {"open": 105.8, "high": 106.2, "low": 105.2, "close": 105.9}
    result = mod.analyze_e4(bars)
    event = result["event"]
    assert not (event["index"] == 58 and event["zone"] and event["zone"]["price"] >= 104.0)


def test_e4_never_promotes_current_candle_wick_to_confirmed_auction():
    mod = _module()
    bars = _bars()
    bars[-1] = {"open": 100.0, "high": 104.0, "low": 99.8, "close": 100.2}
    result = mod.analyze_e4(bars)
    assert result["auction"]["confirmed"] is False
    assert result["auction_state"] in {"UNRESOLVED", "ACCEPTANCE_PENDING", "REJECTION_PENDING"}


def test_e4_dispatcher_uses_v14_and_keeps_decision_authority_with_e9():
    from production_v2.engines import run_engine
    result = run_engine("E4", {"bars": _bars()}, None)
    assert result.output["architecture"] == "E4_SINGLE_PROFESSIONAL_BRAIN_V14_LIQUIDITY_AUCTION"
    assert result.output["reasoning_role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert result.output["decision"] is None
    assert result.output["gate"] is None
    assert result.output["decision_authority"] == "E9_ONLY"
    assert result.output["evidence"]["decisions_used"] is False
    assert result.output["evidence"]["gates_used"] is False
    assert result.output["evidence"]["scores_used"] is False

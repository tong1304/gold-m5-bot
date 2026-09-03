from types import SimpleNamespace

from production_v2.contracts import EngineResult
from production_v2 import e6_opportunity_guard


def _engine(name, output):
    return EngineResult(name, name, False, 0.0, output, ())


def _upstream():
    return {
        "E1": _engine("E1", {"directional_pressure": "UP", "market_state": "TRANSITION"}),
        "E2": _engine("E2", {"finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.", "counter_evidence": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"]}),
        "E3": _engine("E3", {"external_state": "DOWN", "internal_state": "DOWN", "protected_integrity": "VALID", "protected_active_regime": "DOWN"}),
        "E4": _engine("E4", {"event": "HIGH_ACCEPTANCE_CANDIDATE", "event_id": "2026-09-03T07:20:00Z|HIGH_ACCEPTANCE_CANDIDATE|HIGH|4428.52000000|UP", "event_candle_id": "2026-09-03T07:20:00Z", "event_level": 4428.52, "liquidity_taker": "BUYERS", "response_actor": "BUYERS", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "EQUILIBRIUM", "structural_location": "INSIDE_STRUCTURE", "available_space_atr_long": 0.3885, "available_space_atr_short": 0.7221}),
    }


def test_pending_high_acceptance_against_opposite_structure_is_watch_only():
    original = lambda market_data, upstream: _engine("E6", {"setup": "NO_SETUP", "reason_codes": ["NO_CAUSAL_OPPORTUNITY"]})
    module = SimpleNamespace(analyze_e6=original)
    e6_opportunity_guard.install(module)
    out = module.analyze_e6({}, _upstream()).output
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert out["direction"] == "BUY"
    assert out["watch_only"] is True
    assert out["trade_ready"] is False
    assert out["gate_passed"] is False
    assert "E4_AUCTION_FOLLOW_THROUGH" in out["missing_proof"]
    assert "NO_CAUSAL_OPPORTUNITY" not in out["reason_codes"]


def test_hard_directional_conflict_is_not_promoted_to_watch():
    upstream = _upstream()
    upstream["E2"] = _engine("E2", {"finding": "DOWN opportunity is confirmed.", "direction": "SELL"})
    original = lambda market_data, upstream: _engine("E6", {"setup": "NO_SETUP", "reason_codes": ["NO_CAUSAL_OPPORTUNITY"]})
    module = SimpleNamespace(analyze_e6=original)
    e6_opportunity_guard.install(module)
    out = module.analyze_e6({}, upstream).output
    assert out["setup"] == "NO_SETUP"
    assert "NO_CAUSAL_OPPORTUNITY" in out["reason_codes"]

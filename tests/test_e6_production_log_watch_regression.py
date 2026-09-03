from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6


def _engine(name, output):
    return EngineResult(name, name, False, 0.0, output, ())


def test_gold_high_failed_break_reclaim_is_watch_not_no_causal_opportunity():
    upstream = {
        "E1": _engine("E1", {
            "directional_pressure": "BALANCED",
            "market_state": "TRANSITION",
            "structure": "BULLISH",
        }),
        "E2": _engine("E2", {
            "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
            "counter_evidence": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
        }),
        "E3": _engine("E3", {
            "external_state": "DOWN",
            "internal_state": "MIXED",
            "protected_integrity": "VALID",
            "protected_completeness": "BREAK_LEVEL_ONLY",
            "protected_active_regime": "DOWN",
        }),
        "E4": _engine("E4", {
            "event": "HIGH_FAILED_BREAK_RECLAIM",
            "event_id": "2026-09-03T07:05:00Z|HIGH_FAILED_BREAK_RECLAIM|HIGH|4428.52000000|DOWN",
            "event_candle_id": "2026-09-03T07:05:00Z",
            "event_level": 4428.52,
            "liquidity_taker": "BUYERS",
            "response_actor": "SELLERS",
            "auction_state": "PENDING",
        }),
        "E5": _engine("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "DISCOUNT",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.636281,
            "available_space_atr_short": 0.470848,
        }),
    }

    out = analyze_e6({"symbol": "XAU/USD", "timeframe": "M5"}, upstream).output

    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert out["direction"] == "SELL"
    assert out["watch_only"] is True
    assert out["trade_ready"] is False
    assert out["gate_passed"] is False
    assert "NO_CAUSAL_OPPORTUNITY" not in out["reason_codes"]
    assert "E4_AUCTION_FOLLOW_THROUGH" in out["missing_proof"]
    assert "E7_CONFIRMATION" in out["missing_proof"]


def test_gold_07_40_sweep_rejection_is_rescued_when_e6_only_reports_downstream_proof():
    upstream = {
        "E1": _engine("E1", {
            "directional_pressure": "BALANCED",
            "market_state": "RANGE",
            "structure": "BULLISH",
            "structure_direction": "UP",
        }),
        "E2": _engine("E2", {
            "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
            "counter_evidence": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
        }),
        "E3": _engine("E3", {
            "finding": "STRUCTURE_FORMING",
            "external_state": "MIXED",
            "internal_state": "DOWN",
            "protected_integrity": "VALID",
            "protected_completeness": "NO_DIRECTIONAL_REGIME",
            "protected_active_regime": "MIXED",
        }),
        "E4": _engine("E4", {
            "finding": "HIGH_SWEEP_REJECTION",
            "event": "HIGH_SWEEP_REJECTION",
            "event_id": "2026-09-03T07:40:00Z|HIGH_SWEEP_REJECTION|HIGH|4428.52000000|DOWN",
            "event_candle_id": "2026-09-03T07:40:00Z",
            "event_level": 4428.52,
            "liquidity_taker": "BUYERS",
            "response_actor": "SELLERS",
            "auction_state": "PENDING",
        }),
        "E5": _engine("E5", {
            "finding": "WAIT_CONFIRMATION",
            "value_state": "EQUILIBRIUM",
            "value_response": "REJECTED_ABOVE_VALUE",
            "repricing_state": "REPRICING_FAILED",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.421157,
            "available_space_atr_short": 0.171657,
        }),
    }

    out = analyze_e6({"symbol": "XAU/USD", "timeframe": "M5"}, upstream).output

    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert out["direction"] == "SELL"
    assert out["watch_only"] is True
    assert out["trade_ready"] is False
    assert out["trade_permission"] is False
    assert out["gate_passed"] is False
    assert "E4_AUCTION_FOLLOW_THROUGH" in out["missing_proof"]
    assert "E7_CONFIRMATION" in out["missing_proof"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in out["missing_proof"]
    assert "NO_CAUSAL_OPPORTUNITY" not in out["reason_codes"]


def test_mixed_structure_without_causal_auction_does_not_create_watch():
    upstream = {
        "E1": _engine("E1", {"directional_pressure": "BALANCED"}),
        "E2": _engine("E2", {"finding": "NEUTRAL opportunity is emerging."}),
        "E3": _engine("E3", {"external_state": "MIXED", "internal_state": "MIXED"}),
        "E4": _engine("E4", {"event": "NONE", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"finding": "WAIT_CONFIRMATION", "value_state": "EQUILIBRIUM", "available_space_atr_long": 2.0, "available_space_atr_short": 2.0}),
    }

    out = analyze_e6({"symbol": "XAU/USD", "timeframe": "M5"}, upstream).output

    assert out["setup"] not in {"OPPORTUNITY_WATCH", "OPPORTUNITY_THESIS"}
    assert out["trade_ready"] is False

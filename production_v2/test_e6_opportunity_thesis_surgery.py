from production_v2.e6_brain import analyze_e6


class Result:
    def __init__(self, output):
        self.output = output


def _bars(n=80):
    price = 4300.0
    bars = []
    for _ in range(n):
        bars.append({"open": price, "high": price + 2.0, "low": price - 2.0, "close": price + 0.5})
        price += 0.5
    return bars


def _upstream(space_long=1.45):
    return {
        "E1": Result({"directional_pressure": "UP", "pressure": "UP", "trend_state": "NONE", "finding": "MARKET_STATE=TRANSITION"}),
        "E2": Result({"direction": "NEUTRAL", "finding": "OPPORTUNITY IS EMERGING", "opportunity_state": "UNRESOLVED"}),
        "E3": Result({"finding": "BULLISH_STRUCTURE", "internal_state": "UP", "external_state": "UP", "bos": "NONE"}),
        "E4": Result({"event": "HIGH_ACCEPTANCE_CANDIDATE", "auction_state": "PENDING", "direction": "BUY", "event_level": 4326.7, "event_id": "gold-watch-1"}),
        "E5": Result({"finding": "FAVORABLE_LOCATION", "value_state": "DISCOUNT", "value_response": "WAIT_CONFIRMATION", "available_space_atr_long": space_long, "available_space_atr_short": 1.0}),
    }


def test_e6_exposes_forming_opportunity_when_setup_proof_is_not_ready():
    out = analyze_e6({"bars": _bars()}, _upstream()).output
    assert out["state"] == "FORMING"
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["direction"] == "BUY"
    assert out["trade_ready"] is False
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert "E2_OPPORTUNITY_CONFIRMATION" in out["missing_proof"]


def test_e6_keeps_opportunity_watchable_when_space_is_constrained():
    out = analyze_e6({"bars": _bars()}, _upstream(space_long=0.40)).output
    assert out["state"] == "FORMING"
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["trade_ready"] is False
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in out["missing_proof"]


def test_e6_does_not_create_watch_on_hard_directional_conflict():
    upstream = _upstream()
    upstream["E2"] = Result({"direction": "SELL", "finding": "OPPORTUNITY IS CONFIRMED", "opportunity_state": "CONFIRMED"})
    out = analyze_e6({"bars": _bars()}, upstream).output
    assert out["setup"] != "OPPORTUNITY_WATCH"
    assert out["trade_ready"] is False


def test_e6_internal_counterflow_is_counter_evidence_not_hard_conflict():
    upstream = _upstream()
    upstream["E3"] = Result({"finding": "BOS_UP", "internal_state": "DOWN", "external_state": "UP", "bos": "UP"})
    out = analyze_e6({"bars": _bars()}, upstream).output
    assert out["state"] == "FORMING"
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["direction"] == "BUY"
    assert out["trade_ready"] is False
    assert "E3_INTERNAL_COUNTER_EVIDENCE" in out["counter_evidence"]
    assert "E3_INTERNAL_COUNTER_EVIDENCE" not in out["hard_conflicts"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" in out["missing_proof"]


def test_e6_mixed_internal_structure_is_counter_evidence_not_hard_conflict():
    upstream = _upstream()
    upstream["E3"] = Result({"finding": "SWEEP_RECLAIM", "internal_state": "MIXED", "external_state": "UP", "bos": "FAILED"})
    out = analyze_e6({"bars": _bars()}, upstream).output
    assert out["state"] == "FORMING"
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["direction"] == "BUY"
    assert out["trade_ready"] is False
    assert "E3_INTERNAL_COUNTER_EVIDENCE" in out["counter_evidence"]
    assert "E3_INTERNAL_EVIDENCE_UNRESOLVED" in out["missing_proof"]


def test_e6_generic_high_liquidity_interaction_uses_buyer_taker_as_directional_evidence():
    upstream = _upstream()
    upstream["E4"] = Result({
        "event": "HIGH_LIQUIDITY_INTERACTION",
        "auction_state": "PENDING",
        "liquidity_taker": "BUYERS",
        "response_actor": "UNCLEAR",
        "liquidity_type": "EQUAL_LIQUIDITY",
        "event_level": 4375.02,
        "event_id": "gold-2026-09-02T17:45:00Z",
    })
    upstream["E3"] = Result({
        "finding": "BULLISH_STRUCTURE",
        "internal_state": "DOWN",
        "external_state": "UP",
        "bos": "NO_BREAK",
    })
    out = analyze_e6({"bars": _bars()}, upstream).output
    assert out["state"] == "FORMING"
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["direction"] == "BUY"
    assert out["trade_ready"] is False
    assert "E3_INTERNAL_COUNTER_EVIDENCE" in out["counter_evidence"]
    assert "E3_INTERNAL_COUNTER_EVIDENCE" not in out["hard_conflicts"]


def test_e6_exact_constrained_counterflow_keeps_a_contested_thesis_alive():
    upstream = _upstream(space_long=0.2527)
    upstream["E1"] = Result({
        "directional_pressure": "UP",
        "pressure": "UP",
        "trend_state": "NONE",
        "finding": "MARKET_STATE=RANGE; STRUCTURE=BULLISH; COUNTER_EVIDENCE_PRESENT",
    })
    upstream["E2"] = Result({
        "direction": "NEUTRAL",
        "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
        "opportunity_state": "UNRESOLVED",
        "reason_codes": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
    })
    upstream["E3"] = Result({
        "finding": "BULLISH_STRUCTURE",
        "internal_state": "DOWN",
        "external_state": "UP",
        "bos": "NONE",
    })
    upstream["E4"] = Result({
        "event": "LOW_FAILED_BREAK_RECLAIM",
        "auction_state": "PENDING",
        "direction": "UP",
        "liquidity_taker": "SELLERS",
        "response_actor": "BUYERS",
        "event_level": 4375.02,
        "event_id": "gold-2026-09-02T21:35:00Z",
        "quality": 72.75,
    })
    upstream["E5"] = Result({
        "finding": "FAVORABLE_LOCATION",
        "value_state": "EQUILIBRIUM",
        "value_response": "WAIT_CONFIRMATION",
        "available_space_atr_long": 0.2527,
        "available_space_atr_short": 0.6565,
    })

    out = analyze_e6({"bars": _bars()}, upstream).output

    assert out["state"] == "THESIS_CONTESTED"
    assert out["setup"] == "OPPORTUNITY_THESIS"
    assert out["opportunity_stage"] == "CONTESTED"
    assert out["direction"] == "BUY"
    assert out["trade_ready"] is False
    assert out["watch_only"] is True
    assert "E2_OPPORTUNITY_CONFIRMATION" in out["missing_proof"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" in out["missing_proof"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in out["missing_proof"]
    assert "E3_INTERNAL_COUNTER_EVIDENCE" in out["counter_evidence"]
    assert out["hard_conflicts"] == []


def test_e6_infers_failed_break_reclaim_direction_from_event_when_direction_field_is_absent():
    upstream = _upstream(space_long=0.2527)
    upstream["E1"] = Result({
        "directional_pressure": "UP",
        "pressure": "UP",
        "trend_state": "NONE",
        "finding": "MARKET_STATE=RANGE; STRUCTURE=BULLISH; COUNTER_EVIDENCE_PRESENT",
    })
    upstream["E2"] = Result({
        "direction": "NEUTRAL",
        "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
        "opportunity_state": "UNRESOLVED",
    })
    upstream["E3"] = Result({
        "finding": "BULLISH_STRUCTURE",
        "internal_state": "DOWN",
        "external_state": "UP",
        "bos": "NONE",
    })
    upstream["E4"] = Result({
        "event": "LOW_FAILED_BREAK_RECLAIM",
        "auction_state": "PENDING",
        "liquidity_taker": "SELLERS",
        "response_actor": "BUYERS",
        "event_level": 4375.02,
        "event_id": "gold-runtime-regression",
    })
    upstream["E5"] = Result({
        "finding": "FAVORABLE_LOCATION",
        "value_state": "EQUILIBRIUM",
        "available_space_atr_long": 0.2527,
        "available_space_atr_short": 0.6565,
    })

    out = analyze_e6({"bars": _bars()}, upstream).output

    assert out["state"] == "THESIS_CONTESTED"
    assert out["setup"] == "OPPORTUNITY_THESIS"
    assert out["direction"] == "BUY"
    assert out["hard_conflicts"] == []
    assert "E4_DIRECTIONAL_CONFLICT" not in out["hard_conflicts"]


def test_e6_single_e3_anchor_survives_opposing_e1_while_e2_is_unresolved():
    upstream = _upstream(space_long=0.7466)
    upstream["E1"] = Result({
        "directional_pressure": "DOWN",
        "pressure": "DOWN",
        "trend_state": "NONE",
        "finding": "MARKET_STATE=RANGE; STRUCTURE=BEARISH; PRESSURE=DOWN",
    })
    upstream["E2"] = Result({
        "direction": "NEUTRAL",
        "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
        "opportunity_state": "UNRESOLVED",
        "reasons": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
    })
    upstream["E3"] = Result({
        "finding": "BULLISH_STRUCTURE",
        "internal_state": "DOWN",
        "external_state": "UP",
        "bos": "NO_BREAK",
    })
    upstream["E4"] = Result({
        "event": "LOW_FAILED_BREAK_RECLAIM",
        "auction_state": "PENDING",
        "liquidity_taker": "SELLERS",
        "response_actor": "BUYERS",
        "event_level": 77296.52,
        "event_id": "2026-09-02T21:50:00Z|LOW_FAILED_BREAK_RECLAIM|LOW|77296.52|UP",
    })
    upstream["E5"] = Result({
        "finding": "FAVORABLE_LOCATION",
        "value_state": "EQUILIBRIUM",
        "value_response": "REJECTED_BELOW_VALUE",
        "available_space_atr_long": 0.7466,
        "available_space_atr_short": 0.3101,
    })

    out = analyze_e6({"bars": _bars()}, upstream).output

    assert out["state"] == "THESIS_CONTESTED"
    assert out["setup"] == "OPPORTUNITY_THESIS"
    assert out["direction"] == "BUY"
    assert out["trade_ready"] is False
    assert out["watch_only"] is True
    assert out["hard_conflicts"] == []
    assert "E1_COUNTER_EVIDENCE" in out["counter_evidence"]
    assert "E3_EXTERNAL_STRUCTURE_SUPPORT" in out["supporting_evidence"]
    assert "E2_OPPORTUNITY_CONFIRMATION" in out["missing_proof"]

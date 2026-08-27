from production_v2.professional_e4_brain_v15 import analyze_e4, _find_recent_event, _follow_through
from production_v2.engines import run_engine


def _bars(values):
    return [{"open": v - 0.2, "high": v + 0.5, "low": v - 0.5, "close": v} for v in values]


def test_e4_failed_break_reclaim_requires_follow_through_confirmation():
    bars = [
        {"open": 99.0, "high": 100.0, "low": 98.8, "close": 99.5},
        {"open": 99.5, "high": 100.4, "low": 99.2, "close": 100.2},
        {"open": 100.2, "high": 101.0, "low": 99.8, "close": 99.9},
        {"open": 99.9, "high": 100.0, "low": 99.0, "close": 99.2},
    ]
    event = {"type":"HIGH_FAILED_BREAK_RECLAIM","auction_state":"FAILED_BREAK_RECLAIM","directional_implication":"DOWN","index":2,"zone":{"side":"HIGH","upper":100.0,"lower":99.9}}
    result = _follow_through(event, bars, atr=1.0)
    assert result["present"] is True
    assert result["bars"] >= 1
    assert result["reason"] == "FOLLOW_THROUGH_OBSERVED"


def test_e4_ignores_consumed_zone_before_current_event():
    bars = _bars([100 + i * 0.1 for i in range(40)])
    consumed_zone = {"side":"HIGH","price":103.0,"lower":102.9,"upper":103.0,"last_touch_index":20,"consumed":True,"liquidity_taken":True,"taken_index":25,"state":"CONSUMED"}
    event = _find_recent_event(bars, [consumed_zone], [], atr=0.5)
    assert event["zone"] is None
    assert event["type"] == "NO_CONFIRMED_LIQUIDITY_EVENT"


def test_e4_is_analysis_only_and_uses_no_upstream_decision_gate_or_score():
    bars = _bars([100 + i * 0.1 for i in range(60)])
    evidence = {"E1":{"engine_id":"E1","evidence":{"output":{"score":99,"gate":True,"direction":"UP"}}}}
    result = run_engine("E4", {"bars":bars}, evidence)
    assert result.engine_id == "E4"
    assert result.gate_passed is None
    assert result.output["architecture"] == "E4_SINGLE_PROFESSIONAL_BRAIN_V17"
    assert result.output["professional_brain"] is True
    assert result.output["specialists_active"] is False
    assert result.output["specialists_status"] == "PAUSED"
    assert result.output["decision"] is None
    assert result.output["decision_authority"] == "E9_ONLY"
    assert result.output["evidence"]["decisions_used"] is False
    assert result.output["evidence"]["gates_used"] is False
    assert result.output["evidence"]["scores_used"] is False
    assert result.output["score"] is None


def test_e4_exposes_professional_question_and_confirmation_contract():
    bars = _bars([100 + i * 0.05 for i in range(60)])
    result = run_engine("E4", {"bars":bars}, None).output
    assert result["question"] == "Where is liquidity, who took it, and did price accept or reject the auction?"
    assert result["reasoning_role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert "finding" in result
    assert "observations" in result and result["observations"]
    assert "auction_state" in result
    assert "follow_through" in result
    assert "follow_through_bars" in result
    assert "auction_confirmation" in result


def test_e4_rejection_requires_post_event_follow_through():
    bars = _bars([100 + i * 0.02 for i in range(35)])
    event = {"type":"HIGH_SWEEP_REJECTION","auction_state":"REJECTION","directional_implication":"DOWN","index":1,"zone":{"side":"HIGH","upper":100.0,"lower":99.9}}
    no_follow = bars[:2]
    assert _follow_through(event, no_follow, atr=1.0)["present"] is False


def test_e4_context_is_only_a_hint():
    bars = _bars([100 + i * 0.05 for i in range(60)])
    evidence = {"E1":{"evidence":{"output":{"direction":"BUY","score":100,"gate":True}}}}
    result = analyze_e4(bars, evidence)
    assert result["contextual_direction_hint"] == "UP"
    assert result["decision"] is None
    assert result["direction_confirmed"] is False or result["direction"] in {"UP","DOWN","NEUTRAL"}
    assert result["evidence"]["scores_used"] is False
    assert result["evidence"]["gates_used"] is False


def test_e4_acceptance_candidate_cannot_be_reported_as_confirmed_without_follow_through():
    bars = _bars([100 + i * 0.1 for i in range(35)])
    event = {
        "type":"HIGH_ACCEPTANCE_CANDIDATE",
        "directional_implication":"UP",
        "index":34,
        "zone":{"side":"HIGH","upper":103.0,"lower":102.9},
        "liquidity_taker":"BUYERS",
    }
    result = _follow_through(event, bars, atr=1.0)
    assert result["present"] is False


def test_e4_finding_and_auction_state_must_share_confirmation_state():
    bars = _bars([100 + i * 0.05 for i in range(60)])
    result = analyze_e4(bars)
    state = result["auction_state"]
    finding = result["finding"]
    if "ACCEPTANCE_CONFIRMED" in state:
        assert "ACCEPTANCE_CONFIRMED" in finding
    if "REJECTION_CONFIRMED" in state:
        assert "REJECTION_CONFIRMED" in finding
    assert not ("ACCEPTANCE" in finding and "ACCEPTANCE_PENDING" not in state and not result["direction_confirmed"])

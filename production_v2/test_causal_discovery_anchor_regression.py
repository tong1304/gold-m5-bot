from production_v2.causal_reconciliation import reconcile_causal_evidence


class Result:
    def __init__(self, output):
        self.output = output


def _runtime_case():
    return {
        "E1": Result({
            "pressure": "BALANCED",
            "trend_state": "NONE",
            "structure_state": "MIXED",
            "finding": "MARKET_STATE=RANGE; STRUCTURE=MIXED; PRESSURE=BALANCED",
        }).output,
        "E2": Result({
            "direction": "NEUTRAL",
            "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
            "opportunity_state": "UNRESOLVED",
            "reasons": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
        }).output,
        "E3": Result({
            "finding": "BULLISH_STRUCTURE",
            "external_state": "UP",
            "internal_state": "DOWN",
            "bos": "NO_BREAK",
        }).output,
        "E4": Result({
            "event": "HIGH_ACCEPTANCE_CANDIDATE",
            "auction_state": "PENDING",
            "liquidity_taker": "BUYERS",
            "response_actor": "BUYERS",
            "event_level": 77396.97,
        }).output,
        "E5": Result({
            "finding": "FAVORABLE_LOCATION",
            "value_state": "PREMIUM",
            "value_response": "REJECTED_BELOW_VALUE",
            "available_space_atr_long": 0.21806532385754374,
            "available_space_atr_short": 1.297050484221356,
        }).output,
        "E6": {},
    }


def test_single_strong_structure_anchor_keeps_unresolved_opportunity_watchable():
    result = reconcile_causal_evidence(_runtime_case())

    assert result["state"] in {"OPPORTUNITY_WATCH", "CONTESTED_OPPORTUNITY_WATCH"}
    assert result["direction"] == "BUY"
    assert result["ready"] is False
    assert "E3_DIRECTIONAL_ANCHOR" in result["evidence"]
    assert "E2_OPPORTUNITY_CONFIRMATION" in result["wait_for"]
    assert "E6_CAUSAL_SETUP_PROOF" in result["wait_for"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result["reasons"]


def test_single_anchor_watch_never_becomes_execution_ready():
    result = reconcile_causal_evidence(_runtime_case())
    assert result["ready"] is False

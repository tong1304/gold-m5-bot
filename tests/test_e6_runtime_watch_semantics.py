from production_v2.contracts import EngineResult
from production_v2.e6_opportunity_guard import _fallback_opportunity
from production_v2.e6_runtime_authority import _has_no_setup, _normalize_watch_semantics


def _r(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", ())))


def test_setup_family_does_not_hide_legacy_no_setup():
    result = EngineResult(
        "E6", "SETUP_FORMATION_REASONER", False, 0.0,
        {
            "setup": "NO_SETUP",
            "setup_family": "LIQUIDITY_RESPONSE",
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
            "reason_codes": ["E2_OPPORTUNITY_CONFIRMATION", "E7_CONFIRMATION"],
        },
        ("E2_OPPORTUNITY_CONFIRMATION", "E7_CONFIRMATION"),
    )
    assert _has_no_setup(result) is True


def test_populated_setup_family_does_not_hide_legacy_no_setup():
    result = EngineResult(
        "E6", "SETUP_FORMATION_REASONER", False, 0.0,
        {
            "setup": "LIQUIDITY_RESPONSE",
            "setup_family": "LIQUIDITY_RESPONSE",
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
            "reason_codes": [
                "E2_OPPORTUNITY_CONFIRMATION",
                "E4_AUCTION_FOLLOW_THROUGH",
                "E7_CONFIRMATION",
                "STRUCTURAL_SPACE_INSUFFICIENT",
            ],
        },
        (
            "E2_OPPORTUNITY_CONFIRMATION",
            "E4_AUCTION_FOLLOW_THROUGH",
            "E7_CONFIRMATION",
            "STRUCTURAL_SPACE_INSUFFICIENT",
        ),
    )
    assert _has_no_setup(result) is True


def test_fallback_forms_watch_from_realistic_closed_candle_evidence():
    upstream = {
        "E1": _r("E1", {"directional_pressure": "BULLISH"}),
        "E2": _r("E2", {"finding": "UP opportunity is developing based on closed-candle evidence."}),
        "E3": _r("E3", {"external_state": "MIXED", "internal_state": "UP"}),
        "E4": _r("E4", {
            "event": "HIGH_LIQUIDITY_INTERACTION",
            "auction_state": "PENDING",
            "liquidity_taker": "BUYERS",
            "response_actor": "UNCLEAR",
            "event_id": "2026-09-03T12:25:00Z|HIGH_LIQUIDITY_INTERACTION|HIGH|4437.69|NEUTRAL",
        }),
        "E5": _r("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "PREMIUM",
            "structural_location": "AT_RESISTANCE",
            "available_space_atr_long": 0.69,
            "available_space_atr_short": 2.41,
        }),
    }
    candidate = _fallback_opportunity(upstream)
    assert candidate is not None
    assert candidate["direction"] == "BUY"
    assert "E4_AUCTION_FOLLOW_THROUGH" in candidate["missing"]


def test_watch_finding_uses_opportunity_stage_and_direction():
    output = _normalize_watch_semantics(
        {
            "setup": "OPPORTUNITY_WATCH",
            "watch_only": True,
            "trade_ready": False,
            "direction": "SELL",
            "opportunity_stage": "CONTESTED",
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
        }
    )
    assert output["finding"] == "SELL opportunity is contested; causal setup is not yet proven."
    assert output["runtime_authority"] == "E6_FINAL_OPPORTUNITY_MEMBRANE_V4"

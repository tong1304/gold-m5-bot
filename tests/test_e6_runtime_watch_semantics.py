from production_v2.contracts import EngineResult
from production_v2.e6_runtime_authority import _has_no_setup, _normalize_watch_semantics


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

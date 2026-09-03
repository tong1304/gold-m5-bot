from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9


def engine(name, output):
    return EngineResult(name, name, output.get("gate_passed"), 0.0, output, tuple(output.get("reason_codes", ())))


def test_e8_geometry_is_pending_before_closed_candle_trigger():
    upstream = {
        "E1": engine("E1", {"pressure": "UP"}),
        "E2": engine("E2", {"direction": "UP", "state": "DEVELOPING"}),
        "E3": engine("E3", {"structure_direction": "UP", "structure_integrity": "VALID"}),
        "E4": engine("E4", {"auction_state": "PENDING"}),
        "E5": engine("E5", {"value_state": "PREMIUM"}),
        "E6": engine("E6", {
            "direction": "BUY",
            "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
            "thesis_state": "FORMING",
            "finding": "BUY AUCTION_ACCEPTANCE_CONTINUATION is forming",
        }),
        "E7": engine("E7", {
            "confirmation_state": "PENDING",
            "reason_codes": ["VALID_CLOSED_CANDLE_TRIGGER_MISSING"],
        }),
        "E8": engine("E8", {
            "economic_state": "NOT_EVALUABLE",
            "reason_codes": [
                "INVALID_TRADE_GEOMETRY",
                "REAL_RR_BELOW_MINIMUM",
                "STOP_QUALITY_TOO_LOW",
                "TARGET_REALISM_TOO_LOW",
                "EFFECTIVE_SPACE_UNRELIABLE",
                "STRUCTURAL_SURVIVAL_NOT_PROVEN",
                "NO_USABLE_STRUCTURAL_TARGET",
                "HISTORICAL_SAMPLE_INSUFFICIENT",
                "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
            ],
        }),
    }

    result = analyze_e9({}, upstream)

    assert result.output["final_governance"] == "WATCH"
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["confirmation_state"] == "PENDING"
    assert result.output["economic_state"] == "PENDING"
    assert result.output["economic_blockers"] == []
    assert result.output["economic_pending"]
    assert result.output["mandatory_gates"]["fatal_veto_clear"] is True

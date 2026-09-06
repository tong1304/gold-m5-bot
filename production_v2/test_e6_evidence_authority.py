from production_v2.contracts import EngineResult
from production_v2.e6_evidence_authority import normalize_e6_evidence


def _result(output):
    return EngineResult("E6", "Setup Brain", False, 0.0, output, ())


def test_mixed_structure_and_pending_auction_are_not_promoted_to_directional_evidence():
    result = _result({
        "setup": "OPPORTUNITY_WATCH",
        "watch_only": True,
        "trade_ready": False,
        "direction": "BUY",
        "supporting_evidence": [
            "E1_DIRECTIONAL_CORE",
            "E4_DIRECTIONAL_AUCTION_EVIDENCE",
            "E5_LOCATION_VALUE_SUPPORT",
            "E3_EXTERNAL_STRUCTURE_SUPPORT",
        ],
    })
    upstream = {
        "E3": _result({
            "external_state": "MIXED",
            "internal_state": "MIXED",
            "protected_completeness": "NO_DIRECTIONAL_REGIME",
            "protected_active_regime": "MIXED",
        }),
        "E4": _result({
            "event": "LOW_LIQUIDITY_INTERACTION",
            "auction_state": "PENDING",
        }),
    }

    out = normalize_e6_evidence(result, upstream).output

    assert "E4_DIRECTIONAL_AUCTION_EVIDENCE" not in out["supporting_evidence"]
    assert "E4_DIRECTIONAL_EVENT_OBSERVATION" in out["supporting_evidence"]
    assert "E3_EXTERNAL_STRUCTURE_SUPPORT" not in out["supporting_evidence"]
    assert "E3_MIXED_CONTEXT" in out["supporting_evidence"]


def test_confirmed_auction_and_directional_structure_keep_authoritative_evidence():
    result = _result({
        "setup": "OPPORTUNITY_WATCH",
        "watch_only": True,
        "trade_ready": False,
        "direction": "BUY",
        "supporting_evidence": ["E4_DIRECTIONAL_AUCTION_EVIDENCE", "E3_EXTERNAL_STRUCTURE_SUPPORT"],
    })
    upstream = {
        "E3": _result({
            "external_state": "BUY",
            "internal_state": "BUY",
            "protected_completeness": "COMPLETE",
            "protected_active_regime": "BUY",
        }),
        "E4": _result({
            "event": "LOW_REJECTION",
            "auction_state": "CONFIRMED",
        }),
    }

    out = normalize_e6_evidence(result, upstream).output

    assert "E4_DIRECTIONAL_EVENT_OBSERVATION" in out["supporting_evidence"]
    assert "E4_CONFIRMED_RESPONSE" in out["supporting_evidence"]
    assert "E3_EXTERNAL_STRUCTURE_SUPPORT" in out["supporting_evidence"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" in out["supporting_evidence"]

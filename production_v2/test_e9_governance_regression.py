from production_v2.contracts import EngineResult
from production_v2.e9_brain import _hard_conflicts


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", ())))


def test_e9_does_not_promote_e6_propagated_e3_invalidation_when_e3_is_still_established():
    upstream = {
        "E3": _engine("E3", {
            "finding": "BEARISH_STRUCTURE",
            "external_state": "DOWN",
            "internal_state": "MIXED",
            "lifecycle": "ESTABLISHED",
            "invalidation": "NO_INVALIDATION",
            "reason_codes": ("STRUCTURE_LIFECYCLE_EXPLICIT",),
        }),
        "E6": _engine("E6", {
            "finding": "No setup survives because E3 has invalidated the active market structure.",
            "reason_codes": ("E3_STRUCTURE_INVALIDATED",),
        }),
    }

    assert "E3_STRUCTURE_INVALIDATED" not in _hard_conflicts(upstream)


def test_e9_keeps_direct_e3_structure_invalidation_as_hard_conflict():
    upstream = {
        "E3": _engine("E3", {
            "finding": "BULLISH_STRUCTURE_INVALIDATED",
            "external_state": "UP",
            "internal_state": "DOWN",
            "lifecycle": "INVALIDATED",
            "invalidation": "BULLISH_STRUCTURE_INVALIDATED",
        }),
        "E6": _engine("E6", {
            "finding": "BUY LIQUIDITY_REVERSAL is validating",
            "reason_codes": ("E3_STRUCTURE_INVALIDATED",),
        }),
    }

    conflicts = _hard_conflicts(upstream)
    assert any(code in conflicts for code in ("E3_STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED"))
    assert "BULLISH_STRUCTURE_INVALIDATED" in conflicts

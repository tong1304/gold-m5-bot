from types import SimpleNamespace

from production_v2.conflict_resolution import build_conflict_ledger
from production_v2.contracts import EngineResult
from production_v2.opportunity_timing import classify_opportunity_timing
from production_v2.opportunity_timing_runtime_hotfix import _apply


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def test_same_candle_event_is_not_late_from_displacement_alone():
    out = classify_opportunity_timing({
        "direction": "SELL",
        "event": "LOW_LIQUIDITY_INTERACTION",
        "event_level": 79420,
        "price": 79313.85,
        "event_atr_frozen": 100,
        "event_age_bars": 0,
        "opportunity_score": 76.25,
        "available_space_atr_short": 5.2484,
    })
    assert out["event_age_bars"] == 0
    assert out["phase"] != "LATE_OPPORTUNITY"
    assert out["chase_prohibited"] is False


def test_canonical_clock_overrides_stale_e4_age():
    result = _engine("E6", {"direction": "SELL", "finding": "SELL contested watch"})
    upstream = {
        "E4": _engine("E4", {
            "event": "LOW_LIQUIDITY_INTERACTION",
            "event_id": "2026-09-07T09:55:00Z|LOW_LIQUIDITY_INTERACTION|LOW|79420|NEUTRAL",
            "event_candle_id": "2026-09-07T09:55:00Z",
            "event_age_bars": 0,
            "auction_quality": 50.55,
        }),
        "E5": _engine("E5", {"price": 79313.85, "available_space_atr_short": 5.2484}),
    }
    snapshot = {"candle_close_timestamp": "2026-09-07T10:00:00Z"}
    applied = _apply(result, upstream, snapshot).output
    assert applied["causal_event_anchor"]["age_bars"] == 1
    assert applied["event_age_bars"] == 1
    assert applied["opportunity_timing"]["event_age_bars"] == 1
    assert applied["opportunity_timing"]["phase"] != "LATE_OPPORTUNITY"


def test_structure_auction_conflict_is_visible():
    results = {
        "E3": _engine("E3", {"structure_direction": "UP", "external_state": "UP", "finding": "BULLISH_STRUCTURE"}),
        "E4": _engine("E4", {"event": "HIGH_FAILED_BREAK_RECLAIM", "response_actor": "SELLERS", "auction_state": "PENDING"}),
        "E6": _engine("E6", {"direction": "BUY"}),
    }
    ledger = build_conflict_ledger(results)
    conflict = next(x for x in ledger["conflicts"] if x["code"] == "STRUCTURE_AUCTION_CONFLICT")
    assert conflict["brains"] == ["E3", "E4"]
    assert conflict["severity"] == "MEDIUM"
    assert conflict["authority"] == "E9_RECONCILIATION"


def test_conflict_ledger_does_not_turn_awareness_into_veto():
    results = {
        "E3": _engine("E3", {"structure_direction": "UP"}),
        "E4": _engine("E4", {"event": "HIGH_FAILED_BREAK_RECLAIM"}),
        "E6": _engine("E6", {"direction": "BUY"}),
    }
    ledger = build_conflict_ledger(results)
    assert ledger["authority"] == "NON_AUTHORITATIVE"
    assert any(x["code"] == "STRUCTURE_AUCTION_CONFLICT" for x in ledger["conflicts"])

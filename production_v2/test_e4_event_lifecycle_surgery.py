from production_v2.contracts import EngineResult
from production_v2.e4_event_lifecycle_surgery import _repair, install_enrichment_hook


def _bar(ts: str, close: float) -> dict:
    return {"timestamp": ts, "open": close, "high": close, "low": close, "close": close}


def test_pending_acceptance_advances_to_confirmed_after_two_closed_candles():
    bars = [_bar("2026-09-05T16:10:00Z", 79700.0), _bar("2026-09-05T16:15:00Z", 79763.41), _bar("2026-09-05T16:20:00Z", 79805.72), _bar("2026-09-05T16:25:00Z", 79863.99)]
    output = {"event_candle_id": "2026-09-05T16:15:00Z", "event_level": 79763.41, "event_atr": 47.140714, "auction_state": "PENDING", "event": {"index": 3, "event_candle_id": "2026-09-05T16:15:00Z", "event_level": 79763.41, "event_atr": 47.140714, "directional_implication": "UP"}}
    repaired = _repair(output, bars, "2026-09-05T16:25:00Z")
    assert repaired["auction_state"] == "CONFIRMED"
    assert repaired["event_age_bars"] == 2
    assert repaired["follow_through_bars"] == 2
    assert repaired["auction_confirmation"] == "FOLLOW_THROUGH_CONFIRMED"


def test_pending_event_invalidates_on_post_event_reclamation():
    bars = [_bar("2026-09-05T16:15:00Z", 79763.41), _bar("2026-09-05T16:20:00Z", 79805.72), _bar("2026-09-05T16:25:00Z", 79750.00)]
    output = {"event_candle_id": "2026-09-05T16:15:00Z", "event_level": 79763.41, "event_atr": 47.140714, "auction_state": "PENDING", "event": {"index": 2, "event_candle_id": "2026-09-05T16:15:00Z", "event_level": 79763.41, "event_atr": 47.140714, "directional_implication": "UP"}}
    repaired = _repair(output, bars, "2026-09-05T16:25:00Z")
    assert repaired["auction_state"] == "INVALIDATED"
    assert repaired["event_age_bars"] == 2
    assert repaired["auction_confirmation"] == "POST_EVENT_RECLAMATION"


def test_rejection_pending_event_ages_across_next_closed_candle():
    bars = [_bar("2026-09-06T06:00:00Z", 79952.90), _bar("2026-09-06T06:05:00Z", 79957.87)]
    output = {"event_candle_id": "2026-09-06T06:00:00Z", "event_level": 79952.90, "event_atr": 57.586429, "auction_state": "REJECTION_PENDING", "event": {"event_candle_id": "2026-09-06T06:00:00Z", "event_level": 79952.90, "event_atr": 57.586429, "directional_implication": "DOWN"}}
    repaired = _repair(output, bars, "2026-09-06T06:05:00Z")
    assert repaired["event_age_bars"] == 1
    assert repaired["event_index"] == 0
    assert repaired["auction_lifecycle_repaired"] is True


def test_repaired_event_age_is_consistent_in_nested_e4_audit_and_auction_views():
    bars = [_bar("2026-09-06T06:00:00Z", 79952.90), _bar("2026-09-06T06:05:00Z", 79957.87), _bar("2026-09-06T06:10:00Z", 79960.00)]
    output = {"event_candle_id": "2026-09-06T06:00:00Z", "event_level": 79952.90, "event_atr": 57.586429, "auction_state": "REJECTION_PENDING", "event_age_bars": 0, "auction": {"event_age_bars": 0}, "audit": {"event_age_bars": 0}, "event": {"event_candle_id": "2026-09-06T06:00:00Z", "event_level": 79952.90, "event_atr": 57.586429, "directional_implication": "DOWN"}}
    repaired = _repair(output, bars, "2026-09-06T06:10:00Z")
    assert repaired["event_age_bars"] == 2
    assert repaired["auction"]["event_age_bars"] == 2
    assert repaired["audit"]["event_age_bars"] == 2


def test_repaired_event_age_is_consistent_in_observations_view():
    bars = [_bar("2026-09-06T07:00:00Z", 79785.43), _bar("2026-09-06T07:05:00Z", 79784.17)]
    output = {"event_candle_id": "2026-09-06T07:00:00Z", "event_level": 79785.43, "event_atr": 45.525714, "auction_state": "PENDING", "event_age_bars": 0, "observations": ["event_candle_id=2026-09-06T07:00:00Z", "event_age_bars=0"], "event": {"event_candle_id": "2026-09-06T07:00:00Z", "event_level": 79785.43, "event_atr": 45.525714, "directional_implication": "DOWN"}}
    repaired = _repair(output, bars, "2026-09-06T07:05:00Z")
    assert repaired["event_age_bars"] == 1
    assert "event_age_bars=1" in repaired["observations"]
    assert "event_age_bars=0" not in repaired["observations"]


def test_e4_lifecycle_repair_runs_after_enrichment_when_enrichment_creates_pending_state():
    class FakePipeline:
        pass
    pipeline = FakePipeline()
    pipeline._enrich = lambda engine_id, result, snapshot: EngineResult(result.engine_id, result.name, result.gate_passed, result.score, {**result.output, "auction_state": "PENDING"}, result.reason_codes)
    install_enrichment_hook(pipeline)
    bars = [_bar("2026-09-06T05:40:00Z", 79900.0), _bar("2026-09-06T05:45:00Z", 79973.85), _bar("2026-09-06T05:50:00Z", 79994.00)]
    result = EngineResult("E4", "Liquidity Brain", False, 50.0, {"event_candle_id": "2026-09-06T05:45:00Z", "event_level": 79973.85, "event_atr": 59.022857, "event": {"event_candle_id": "2026-09-06T05:45:00Z", "directional_implication": "UP"}}, ())
    enriched = pipeline._enrich("E4", result, {"bars": bars, "evaluation_candle_timestamp": "2026-09-06T05:50:00Z"})
    assert enriched.output["auction_state"] == "PENDING"
    assert enriched.output["event_age_bars"] == 1
    assert enriched.output["event_index"] == 1
    assert enriched.output["auction_lifecycle_repaired"] is True

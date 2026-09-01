import pytest

from production_v2.market_data import normalize_market_data
from production_v2.shared_market_picture import audit_shared_market_picture_contract, attach_brain_view, build_shared_market_picture


def _bar(ts="2026-09-01T04:55:00Z", closed=True):
    return {
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "timestamp": ts,
        "candle_id": ts,
        "is_closed": closed,
        "candle_close_timestamp": "2026-09-01T05:00:00Z",
    }


def test_normalizer_rejects_unknown_candle_closure():
    bar = _bar()
    bar.pop("is_closed")
    with pytest.raises(ValueError, match="CLOSED_CANDLE_STATUS_REQUIRED"):
        normalize_market_data({"symbol": "XAU/USD", "timeframe": "M5", "bars": [bar]})


def test_normalizer_drops_explicitly_open_candle_and_preserves_identity():
    payload = normalize_market_data({
        "symbol": "XAU/USD",
        "timeframe": "M5",
        "bars": [_bar("2026-09-01T04:50:00Z"), _bar("2026-09-01T04:55:00Z", False)],
        "candle_close_timestamp": "2026-09-01T04:50:00Z",
    })
    assert len(payload["bars"]) == 1
    assert payload["bars"][0]["is_closed"] is True
    assert payload["bars"][0]["candle_id"] == "2026-09-01T04:50:00Z"
    assert payload["closed_candle_only"] is True
    assert payload["lookahead_allowed"] is False


def test_shared_picture_contract_has_cutoff_and_fact_source():
    market = {
        "symbol": "XAU/USD",
        "timeframe": "M5",
        "bars": [_bar("2026-09-01T01:00:00Z"), _bar("2026-09-01T01:05:00Z")],
        "closed_candle_only": True,
        "lookahead_allowed": False,
    }
    picture = build_shared_market_picture(market)
    assert picture["data_cutoff_candle_id"] == "2026-09-01T01:05:00Z"
    assert picture["data_cutoff_timestamp"] is not None
    assert picture["closed_candle_only"] is True
    assert picture["lookahead_detected"] is False
    assert picture["contract"]["fact_source_ids"] == ["CANDLE:2026-09-01T01:05:00Z"]


def test_all_brains_share_one_picture_and_fact_interpretation_decision_are_separate():
    market = {
        "symbol": "BTC/USD",
        "timeframe": "M5",
        "bars": [_bar(f"2026-09-01T01:{minute:02d}:00Z") for minute in range(0, 55, 5)],
        "closed_candle_only": True,
        "lookahead_allowed": False,
    }
    picture = build_shared_market_picture(market)
    outputs = {}
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
        outputs[engine_id] = attach_brain_view(engine_id, {"finding": "TEST", "decision": "NO_TRADE"}, picture)
    audit = audit_shared_market_picture_contract(outputs)
    assert audit["passed"] is True
    assert audit["unique_cutoff_candle_ids"] == ["2026-09-01T01:50:00Z"]
    for output in outputs.values():
        assert output["evidence_audit"]["facts"]["classification"] == "FACT"
        assert output["evidence_audit"]["interpretation"]["classification"] == "INTERPRETATION"
        assert output["evidence_audit"]["decision"]["classification"] == "DECISION"


def test_shared_picture_rejects_direct_input_without_explicit_closure_proof():
    bar = _bar()
    bar.pop("is_closed")
    with pytest.raises(ValueError, match="CLOSED_CANDLE_STATUS_REQUIRED"):
        build_shared_market_picture({"symbol": "XAU/USD", "timeframe": "M5", "bars": [bar]})


def test_shared_picture_rejects_cutoff_timestamp_without_timestamped_bar_evidence():
    bar = _bar()
    bar.pop("timestamp")
    with pytest.raises(ValueError, match="CUTOFF_TIMESTAMP_REQUIRES_TIMESTAMPED_CANDLES"):
        build_shared_market_picture({
            "symbol": "XAU/USD", "timeframe": "M5", "bars": [bar],
            "data_cutoff_timestamp": "2026-09-01T05:00:00Z",
        })


def test_contract_audit_requires_nonempty_provenance_arrays_and_matching_cutoffs():
    picture = build_shared_market_picture({
        "symbol": "BTC/USD", "timeframe": "M5",
        "bars": [_bar(f"2026-09-01T01:{minute:02d}:00Z") for minute in range(0, 55, 5)],
        "closed_candle_only": True, "lookahead_allowed": False,
    })
    outputs = {
        eid: attach_brain_view(eid, {"finding": "TEST", "decision": "NO_TRADE"}, picture)
        for eid in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
    }
    outputs["E4"]["market_picture_contract"]["fact_source_ids"] = []
    outputs["E5"]["market_picture_contract"]["data_cutoff_candle_id"] = "tampered"
    audit = audit_shared_market_picture_contract(outputs)
    assert audit["passed"] is False
    assert "E4:FACT_SOURCE_IDS_MISSING" in audit["issues"]
    assert "E5:CUTOFF_CANDLE_MISMATCH" in audit["issues"]

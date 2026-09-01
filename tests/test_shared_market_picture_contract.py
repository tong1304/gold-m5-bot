from production_v2.shared_market_picture import (
    ENGINE_ORDER,
    attach_brain_view,
    audit_shared_market_picture_contract,
    build_shared_market_picture,
)


def _bars():
    bars = []
    for i in range(50):
        bars.append({
            "id": f"c{i}",
            "timestamp": f"2026-09-01T00:{i:02d}:00Z",
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100.5 + i,
            "is_closed": True,
        })
    return bars


def test_shared_picture_excludes_unclosed_candle_and_freezes_cutoff():
    bars = _bars()
    bars[-1]["is_closed"] = False
    market_data = {
        "symbol": "TEST",
        "timeframe": "M5",
        "bars": bars,
        "closed_candle_only": True,
        "data_cutoff_candle_id": "c48",
    }

    picture = build_shared_market_picture(market_data)

    assert picture["data_cutoff_candle_id"] == "c48"
    assert picture["closed_candle_only"] is True
    assert picture["lookahead_detected"] is False
    assert picture["candle_identity"] == "c48"
    assert market_data["bars"][-1]["id"] == "c48"
    assert all(bar.get("is_closed") is not False for bar in market_data["bars"])


def test_each_brain_exposes_fact_interpretation_and_decision_contract():
    picture = build_shared_market_picture({"symbol": "TEST", "timeframe": "M5", "bars": _bars()})

    e1 = attach_brain_view("E1", {"finding": "RANGE"}, picture)
    e9 = attach_brain_view("E9", {"finding": "NO_TRADE", "decision": "NO_TRADE"}, picture)

    assert e1["evidence_audit"]["facts"]["classification"] == "FACT"
    assert e1["evidence_audit"]["interpretation"]["classification"] == "INTERPRETATION"
    assert e1["evidence_audit"]["facts"]["source_ids"]
    assert e1["evidence_audit"]["interpretation"]["source_ids"] == ["E1"]
    assert e1["evidence_audit"]["decision"]["source_ids"] == []
    assert e9["evidence_audit"]["decision"]["classification"] == "DECISION"
    assert e9["evidence_audit"]["decision"]["source_ids"] == ["E9"]


def test_contract_audit_rejects_lookahead_or_non_closed_brain_view():
    picture = build_shared_market_picture({"symbol": "TEST", "timeframe": "M5", "bars": _bars()})
    outputs = {
        eid: attach_brain_view(eid, {"finding": "OK"}, picture)
        for eid in ENGINE_ORDER
    }
    outputs["E4"]["market_picture_contract"]["lookahead_allowed"] = True

    audit = audit_shared_market_picture_contract(outputs)

    assert audit["passed"] is False
    assert "LOOKAHEAD_CONTRACT_VIOLATION" in audit["issues"]
    assert "E4" in audit["violating_brains"]

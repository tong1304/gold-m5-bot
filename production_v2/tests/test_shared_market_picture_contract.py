from production_v2.shared_market_picture import (
    FIELD_OF_VIEW,
    attach_brain_view,
    audit_shared_market_picture_contract,
    build_shared_market_picture,
)


def _bars(n=60):
    return [
        {
            "timestamp": f"2026-09-01T00:{i:02d}:00Z",
            "open": 100.0 + i * 0.1,
            "high": 100.5 + i * 0.1,
            "low": 99.5 + i * 0.1,
            "close": 100.2 + i * 0.1,
        }
        for i in range(n)
    ]


def test_shared_picture_has_explicit_fact_ledger_and_stable_id():
    picture = build_shared_market_picture({"symbol": "XAUUSD", "timeframe": "M5", "bars": _bars()})

    assert picture["schema"] == "SHARED_MARKET_PICTURE_V2"
    assert picture["picture_id"]
    assert picture["fact_ledger"]["classification"] == "FACT_ONLY"
    assert picture["fact_ledger"]["interpretation_allowed"] is False
    assert picture["fact_ledger"]["fields"]


def test_brain_view_separates_shared_facts_from_brain_interpretation():
    picture = build_shared_market_picture({"symbol": "XAUUSD", "timeframe": "M5", "bars": _bars()})
    output = attach_brain_view("E1", {"finding": "MARKET_STATE=RANGE", "reasons": ["COUNTER_EVIDENCE_PRESENT"]}, picture)

    contract = output["market_picture_contract"]
    assert contract["picture_id"] == picture["picture_id"]
    assert contract["fact_authority"] == "SHARED_MARKET_PICTURE"
    assert contract["interpretation_authority"] == "BRAIN_ROLE_ONLY"
    assert output["evidence_audit"]["facts"]["source"] == "SHARED_MARKET_PICTURE"
    assert output["evidence_audit"]["interpretation"]["finding"] == "MARKET_STATE=RANGE"
    assert output["evidence_audit"]["interpretation"]["finding"] not in output["evidence_audit"]["facts"]


def test_shared_picture_contract_detects_mismatched_picture_ids():
    picture = build_shared_market_picture({"symbol": "BTCUSD", "timeframe": "M5", "bars": _bars()})
    outputs = {eid: attach_brain_view(eid, {"finding": "TEST"}, picture) for eid in FIELD_OF_VIEW}
    outputs["E5"]["shared_market_picture"] = dict(outputs["E5"]["shared_market_picture"], picture_id="TAMPERED")

    audit = audit_shared_market_picture_contract(outputs)

    assert audit["passed"] is False
    assert "E5" in audit["mismatched_brains"]
    assert "SHARED_PICTURE_ID_MISMATCH" in audit["issues"]


def test_shared_picture_contract_accepts_all_nine_brains_on_same_snapshot():
    picture = build_shared_market_picture({"symbol": "XAUUSD", "timeframe": "M5", "bars": _bars()})
    outputs = {eid: attach_brain_view(eid, {"finding": f"{eid}_INTERPRETATION"}, picture) for eid in FIELD_OF_VIEW}

    audit = audit_shared_market_picture_contract(outputs)

    assert audit["passed"] is True
    assert audit["covered_brains"] == list(FIELD_OF_VIEW)
    assert audit["unique_picture_ids"] == [picture["picture_id"]]
    assert audit["issues"] == []

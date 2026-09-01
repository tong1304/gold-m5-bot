from production_v2.shared_market_picture import attach_brain_view, build_shared_market_picture


def test_shared_picture_has_stable_cycle_identity_and_brain_views_reference_it():
    bars = [
        {"timestamp": f"2026-09-01T00:{i:02d}:00Z", "open": 100+i, "high": 101+i, "low": 99+i, "close": 100.5+i}
        for i in range(60)
    ]
    picture = build_shared_market_picture({"symbol": "TEST", "timeframe": "M5", "bars": bars})

    assert picture["picture_id"]
    assert picture["picture_id"].startswith("SMP1:")
    assert picture["candle_identity"] == bars[-1]["timestamp"]

    e1 = attach_brain_view("E1", {"finding": "RANGE"}, picture)
    e6 = attach_brain_view("E6", {"finding": "SETUP"}, picture)

    assert e1["shared_market_picture"]["picture_id"] == picture["picture_id"]
    assert e6["shared_market_picture"]["picture_id"] == picture["picture_id"]
    assert e1["view_contract"] == "SHARED_FACTS + BRAIN_SPECIFIC_INTERPRETATION + EXPLICIT_BOUNDARY"
    assert e1["field_of_view"]["role"] != e6["field_of_view"]["role"]


def test_brain_view_cannot_claim_authority_outside_its_boundary():
    picture = build_shared_market_picture({"symbol": "TEST", "timeframe": "M5", "bars": []})
    view = attach_brain_view("E7", {"finding": "CONFIRMATION"}, picture)

    assert view["field_of_view"]["does_not_own"]
    assert "creating_the_thesis" in view["field_of_view"]["does_not_own"]
    assert view["field_of_view"]["boundary_rule"] == "DESCRIBE_ONLY_WHAT_THIS_BRAIN_HAS_EVIDENCE_AND_AUTHORITY_TO_SEE"

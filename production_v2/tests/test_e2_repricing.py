from production_v2.e2_repricing import preserve_repricing_thesis


def test_preserves_directional_thesis_when_trend_is_valid_but_location_is_unfavorable():
    result = preserve_repricing_thesis({
        "state": "OPPORTUNITY_ANALYSIS_COMPLETE",
        "regime": "TREND",
        "direction": "DOWN",
        "opportunity": "TREND_PULLBACK_CONTINUATION",
        "opportunity_state": "DEVELOPING",
        "opportunity_maturity": "DEVELOPING",
        "location_context": "EDGE_LOW",
        "evidence_map": {"space_ok": False, "overextended": True},
        "invalidation_evidence": [],
        "counter_evidence": [],
        "missing_evidence": ["controlled pullback"],
        "reason_codes": ["MISSING_OPPORTUNITY_CONFIRMATION"],
    })

    assert result["direction"] == "DOWN"
    assert result["opportunity"] == "TREND_PULLBACK_CONTINUATION"
    assert result["opportunity_state"] == "WAITING_REPRICING"
    assert result["opportunity_maturity"] == "WAITING_REPRICING"
    assert "WAITING_REPRICING" in result["reason_codes"]
    assert "THESIS_INVALIDATED" not in result["reason_codes"]


def test_does_not_resurrect_an_invalidated_thesis():
    result = preserve_repricing_thesis({
        "regime": "TREND",
        "direction": "DOWN",
        "opportunity": "TREND_PULLBACK_CONTINUATION",
        "opportunity_state": "INVALIDATED",
        "opportunity_maturity": "INVALIDATED",
        "location_context": "EDGE_LOW",
        "evidence_map": {"space_ok": False, "overextended": True},
        "invalidation_evidence": ["opposing structure reclaimed"],
        "counter_evidence": [],
        "missing_evidence": [],
        "reason_codes": ["THESIS_INVALIDATED"],
    })

    assert result["opportunity_state"] == "INVALIDATED"
    assert result["opportunity_maturity"] == "INVALIDATED"
    assert "WAITING_REPRICING" not in result["reason_codes"]

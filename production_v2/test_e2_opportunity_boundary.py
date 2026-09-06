from __future__ import annotations

from production_v2.e2_brain import _classify_opportunity


def test_e2_does_not_claim_directional_edge_when_score_margin_is_only_two():
    result = _classify_opportunity(
        up=5,
        down=3,
        auction="UNCOMMITTED_AUCTION",
        balanced=False,
        acceptance=False,
        rejection=False,
        space_atr=2.0,
        location_ok=True,
    )

    assert result["direction"] == "NEUTRAL"
    assert "DIRECTIONAL_EDGE_NOT_ESTABLISHED" in result["blockers"]


def test_e2_can_claim_directional_opportunity_when_evidence_margin_is_clear():
    result = _classify_opportunity(
        up=6,
        down=2,
        auction="BUY_SIDE_ACCEPTANCE",
        balanced=False,
        acceptance=True,
        rejection=False,
        space_atr=2.0,
        location_ok=True,
    )

    assert result["direction"] == "BUY"
    assert result["opportunity_maturity"] == "DEVELOPING"


def test_e2_keeps_directional_opportunity_watch_when_location_is_not_advantageous():
    result = _classify_opportunity(
        up=6,
        down=2,
        auction="BUYER_INITIATIVE_PENDING_ACCEPTANCE",
        balanced=False,
        acceptance=False,
        rejection=False,
        space_atr=2.0,
        location_ok=False,
    )

    assert result["direction"] == "BUY"
    assert "LOCATION_NOT_ADVANTAGEOUS" in result["blockers"]
    assert "NO_TRADEABLE_OPPORTUNITY_PATH_YET" in result["blockers"]

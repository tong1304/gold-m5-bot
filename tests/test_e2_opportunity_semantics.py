from production_v2.e2_brain import _classify_opportunity


def test_e2_acceptance_does_not_promote_opportunity_to_confirmed():
    result = _classify_opportunity(
        up=6,
        down=1,
        auction="BUY_SIDE_ACCEPTANCE",
        balanced=False,
        acceptance=True,
        rejection=False,
        space_atr=0.5,
        location_ok=False,
    )

    assert result["direction"] == "BUY"
    assert result["opportunity_maturity"] == "DEVELOPING"
    assert result["finding"] == "AUCTION_ACCEPTANCE_CONFIRMED_OPPORTUNITY_DEVELOPING"
    assert "INSUFFICIENT_OPPOSING_SPACE" in result["blockers"]
    assert "LOCATION_NOT_ADVANTAGEOUS" in result["blockers"]


def test_e2_developing_opportunity_uses_tradeable_path_blocker_not_no_opportunity():
    result = _classify_opportunity(
        up=6,
        down=1,
        auction="BUYER_INITIATIVE_PENDING_ACCEPTANCE",
        balanced=False,
        acceptance=False,
        rejection=False,
        space_atr=0.6,
        location_ok=True,
    )

    assert result["direction"] == "BUY"
    assert result["opportunity_maturity"] == "DEVELOPING"
    # _classify_opportunity owns base blockers; the final E2 layer upgrades
    # this to NO_TRADEABLE_OPPORTUNITY_PATH_YET only when no candidate is eligible.
    assert "NO_ELIGIBLE_OPPORTUNITY_PATH" not in result["blockers"]

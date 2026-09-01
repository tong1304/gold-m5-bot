from production_v2.e8_brain import _historical_probability, _stop


def test_e8_probability_requires_setup_matched_history_when_setup_is_known():
    records = ([{"direction": "BUY", "setup": "OTHER", "win": True}] * 80 +
               [{"direction": "BUY", "setup": "AUCTION_ACCEPTANCE_CONTINUATION", "win": False}] * 10)
    result = _historical_probability({"historical_outcomes": records}, "BUY", "AUCTION_ACCEPTANCE_CONTINUATION")
    assert result["sample"] == 10
    assert result["trusted"] is False
    assert result["method"] == "SETUP_DIRECTION_CONDITIONED_WILSON"


def test_e8_stop_selection_prefers_a_structurally_valid_width_over_too_tight_nearest_level():
    result = _stop("BUY", entry=100.0, atr=1.0, levels={"protected_low": 99.8, "structure_low_20": 98.0})
    assert result["source"] == "STRUCTURE_LOW_20"
    assert 0.50 <= result["risk_atr"] <= 3.50

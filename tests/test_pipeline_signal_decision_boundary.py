from production_v2.pipeline import normalize_final_decision


def test_e9_buy_survives_pipeline_decision_normalization():
    assert normalize_final_decision("BUY", True, True) == "BUY"


def test_e9_sell_survives_pipeline_decision_normalization():
    assert normalize_final_decision("SELL", True, True) == "SELL"


def test_non_actionable_decision_is_no_trade():
    assert normalize_final_decision("NO_TRADE", False, False) == "NO_TRADE"


def test_gate_failure_blocks_buy_sell():
    assert normalize_final_decision("BUY", False, True) == "NO_TRADE"
    assert normalize_final_decision("SELL", True, False) == "NO_TRADE"

from production_v2.bootstrap_surgery import _bootstrap_probability, _bootstrap_eligible


def test_bootstrap_probability_is_explicitly_uncalibrated_prior():
    probability = _bootstrap_probability()
    assert probability["state"] == "BOOTSTRAP_UNCALIBRATED"
    assert probability["probability"] == 0.50
    assert probability["stress_probability"] == 0.47
    assert probability["sample"] == 0
    assert probability["trusted"] is False


def test_bootstrap_requires_all_non_probability_gates():
    base = {
        "confirmation": "CONFIRMED",
        "target_valid": True,
        "side_valid": True,
        "risk_atr": 1.20,
        "real_rr": 2.00,
        "space_ok": True,
        "survival": "ROBUST",
        "execution_ok": True,
        "target_realism": 0.80,
        "stop_quality": 80.0,
        "sensitivity": "ROBUST",
        "risk_class": "A",
        "hard_reasons": [],
    }
    assert _bootstrap_eligible(base) is True
    base["survival"] = "FRAGILE"
    assert _bootstrap_eligible(base) is False

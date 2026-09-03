from production_v2.professional_governance import audit_engines


def test_pending_economics_is_not_a_hard_veto():
    results = {
        "E1": {"direction": "UP", "state": "READY"},
        "E2": {"direction": "UP", "state": "DEVELOPING"},
        "E3": {"direction": "UP", "structure_integrity": "VALID", "state": "READY"},
        "E4": {"auction_state": "PENDING", "state": "PENDING"},
        "E5": {"state": "FAVORABLE_LOCATION"},
        "E6": {"direction": "BUY", "setup": "AUCTION_ACCEPTANCE_CONTINUATION", "state": "FORMING"},
        "E7": {"confirmation_state": "PENDING", "state": "PENDING"},
        "E8": {
            "economic_state": "NOT_EVALUABLE",
            "risk_state": "UNRESOLVED",
            "reason_codes": [
                "ENTRY_CONFIRMATION",
                "HISTORICAL_SAMPLE_INSUFFICIENT",
                "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
            ],
        },
        "E9": {
            "decision": "NO_TRADE",
            "mandatory_gates": {
                "core_thesis": True,
                "closed_candle_trigger": False,
                "survivable_economics": False,
                "fatal_veto_clear": True,
            },
            "all_gates_pass": False,
        },
    }

    audit = audit_engines(results)

    assert audit["hard_veto"] is False
    assert "TRADE_ECONOMICS_NOT_VALID" not in audit["hard_vetoes"]
    assert "E8" in audit["pending_gates"]
    assert audit["pending_is_not_hard_conflict"] is True

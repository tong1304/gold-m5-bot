from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9


def _er(engine_id, output=None, reasons=()):
    return EngineResult(engine_id, engine_id, None, 0.0, output or {}, tuple(reasons))


def test_e9_preserves_e6_hypothesis_identity_while_waiting_for_proof():
    result = analyze_e9(
        {},
        {
            "E6": _er(
                "E6",
                {
                    "finding": "SELL AUCTION_ACCEPTANCE_CONTINUATION is validating: thesis alive",
                    "maturity": "FORMING",
                },
            ),
            "E7": _er(
                "E7",
                {"confirmation_state": "PENDING", "trigger_state": "OBSERVED"},
                ("PROOF_GATES_INCOMPLETE",),
            ),
            "E8": _er(
                "E8",
                {"risk_gate": "BLOCKED"},
                ("REAL_RR_BELOW_MINIMUM",),
            ),
        },
    )

    assert result.output["direction"] == "SELL"
    assert result.output["setup"] == "AUCTION_ACCEPTANCE_CONTINUATION"
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["decision_state"] == "WAIT_FOR_PROOF"


def test_e9_executes_only_when_all_master_gates_pass():
    plan = {"entry": 100.0, "stop_loss": 99.0, "take_profit_2": 102.0, "rr_tp2": 2.0}
    result = analyze_e9(
        {},
        {
            "E6": _er(
                "E6",
                {"finding": "BUY AUCTION_ACCEPTANCE_CONTINUATION is validating", "maturity": "MATURE"},
            ),
            "E7": _er(
                "E7",
                {"confirmation_state": "PROVEN", "trigger_observed": True},
                ("CONFIRMATION_PROVEN",),
            ),
            "E8": _er("E8", {"risk_gate": "RISK_READY", "trade_plan": plan}),
        },
    )

    assert result.output["decision"] == "BUY"
    assert result.gate_passed is True
    assert result.output["master_resolution"] == "EXECUTE"
    assert result.output["trade_plan"] == plan


def test_e9_hard_conflict_rejects_even_if_other_gates_pass():
    plan = {"entry": 100.0, "stop_loss": 99.0, "take_profit_2": 102.0, "rr_tp2": 2.0}
    result = analyze_e9(
        {},
        {
            "E3": _er("E3", reasons=("STRUCTURE_THESIS_CONFLICT",)),
            "E6": _er("E6", {"finding": "BUY X is validating", "maturity": "MATURE"}),
            "E7": _er("E7", {"confirmation_state": "PROVEN", "trigger_observed": True}, ("CONFIRMATION_PROVEN",)),
            "E8": _er("E8", {"risk_gate": "RISK_READY", "trade_plan": plan}),
        },
    )

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["decision_state"] == "REJECT"
    assert result.output["primary_blocker"] == "STRUCTURE_THESIS_CONFLICT"


def test_e9_reads_verified_nested_e8_execution_boundary():
    plan = {"direction": "BUY", "entry": 100.0, "stop_loss": 99.0, "take_profit_2": 102.0, "rr_tp2": 2.0}
    result = analyze_e9(
        {},
        {
            "E6": _er("E6", {"finding": "BUY X is validating", "maturity": "MATURE"}),
            "E7": _er("E7", {"confirmation_state": "PROVEN", "trigger_observed": True}, ("CONFIRMATION_PROVEN",)),
            "E8": _er(
                "E8",
                {
                    "specialists": {
                        "8G": {
                            "output": {
                                "trade_plan": plan,
                                "plan_status": "COMPLETE",
                                "risk_gate": "RISK_READY",
                            }
                        }
                    }
                },
            ),
        },
    )

    assert result.output["decision"] == "BUY"
    assert result.output["trade_plan"] == plan

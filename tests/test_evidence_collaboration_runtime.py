from types import SimpleNamespace

from production_v2.evidence_collaboration_runtime import (
    build_evidence_ledger,
    install,
    ledger_for_e9,
)
from production_v2.contracts import EngineResult


def _upstream():
    return {
        "E1": EngineResult("E1", "E1", True, 70.0, {"direction": "SELL", "finding": "BEARISH REGIME"}, ()),
        "E2": EngineResult("E2", "E2", False, 60.0, {"direction": "SELL", "finding": "SELL OPPORTUNITY DEVELOPING"}, ()),
        "E3": EngineResult("E3", "E3", True, 75.0, {"direction": "SELL", "finding": "BEARISH STRUCTURE"}, ()),
        "E4": EngineResult("E4", "E4", False, 50.0, {"direction": "SELL", "finding": "SWEEP PENDING"}, ()),
        "E5": EngineResult("E5", "E5", True, 65.0, {"direction": "SELL", "finding": "FAVORABLE LOCATION"}, ()),
    }


def test_evidence_ledger_preserves_pre_thesis_e1_e5_without_wrapping_e6():
    upstream = _upstream()
    ledger = build_evidence_ledger(upstream)

    assert ledger["schema"] == "EVIDENCE_LEDGER_V1"
    assert ledger["phase"] == "PRE_THESIS_E1_E5"
    assert ledger["brains"]["E4"]["proof_state"] == "PENDING"
    assert "decision" not in ledger

    def e6(market_data, upstream):
        return EngineResult("E6", "E6", False, 0.0, {"setup": "OPPORTUNITY_WATCH"}, ())

    def e9(snapshot, upstream):
        return EngineResult("E9", "E9", False, 0.0, {"decision": "NO_TRADE"}, ())

    e6_module = SimpleNamespace(analyze_e6=e6)
    e9_module = SimpleNamespace(analyze_e9=e9)
    original_e6 = e6_module.analyze_e6
    install(e6_module, e9_module)

    assert e6_module.analyze_e6 is original_e6


def test_final_evidence_ledger_covers_e1_e8_for_e9():
    upstream = _upstream()
    upstream.update({
        "E6": EngineResult("E6", "E6", True, 80.0, {"direction": "SELL", "setup": "SELL_PULLBACK", "finding": "SELL THESIS"}, ()),
        "E7": EngineResult("E7", "E7", True, 80.0, {"confirmation_state": "CONFIRMED"}, ()),
        "E8": EngineResult("E8", "E8", True, 80.0, {"economic_state": "READY"}, ()),
    })

    ledger = ledger_for_e9(upstream)

    assert ledger["schema"] == "EVIDENCE_LEDGER_V1"
    assert ledger["phase"] == "FINAL_GOVERNANCE_E1_E8"
    assert ledger["decision"] is None
    assert set(ledger["brains"]) == set(upstream)

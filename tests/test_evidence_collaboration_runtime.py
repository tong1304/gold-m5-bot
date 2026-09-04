from types import SimpleNamespace

from production_v2.evidence_collaboration_runtime import install
from production_v2.contracts import EngineResult


def test_evidence_ledger_flows_from_e1_e5_into_e6_and_e9():
    seen = {}

    def e6(market_data, upstream):
        seen["e6"] = market_data["evidence_ledger"]
        return EngineResult("E6", "E6", False, 0.0, {"setup": "OPPORTUNITY_WATCH"}, ())

    def e9(snapshot, upstream):
        seen["e9"] = snapshot["evidence_ledger"]
        return EngineResult("E9", "E9", False, 0.0, {"decision": "NO_TRADE"}, ())

    e6_module = SimpleNamespace(analyze_e6=e6)
    e9_module = SimpleNamespace(analyze_e9=e9)
    install(e6_module, e9_module)

    upstream = {
        "E1": EngineResult("E1", "E1", True, 70.0, {"direction": "SELL", "finding": "BEARISH REGIME"}, ()),
        "E2": EngineResult("E2", "E2", False, 60.0, {"direction": "SELL", "finding": "SELL OPPORTUNITY DEVELOPING"}, ()),
        "E3": EngineResult("E3", "E3", True, 75.0, {"direction": "SELL", "finding": "BEARISH STRUCTURE"}, ()),
        "E4": EngineResult("E4", "E4", False, 50.0, {"direction": "SELL", "finding": "SWEEP PENDING"}, ()),
        "E5": EngineResult("E5", "E5", True, 65.0, {"direction": "SELL", "finding": "FAVORABLE LOCATION"}, ()),
    }
    market_data = {}
    e6_module.analyze_e6(market_data, upstream)

    assert seen["e6"]["schema"] == "EVIDENCE_LEDGER_V1"
    assert seen["e6"]["phase"] == "PRE_THESIS_E1_E5"
    assert seen["e6"]["brains"]["E4"]["proof_state"] == "PENDING"
    assert "decision" not in seen["e6"]

    final_upstream = dict(upstream)
    final_upstream["E6"] = EngineResult("E6", "E6", True, 80.0, {"direction": "SELL", "setup": "SELL_PULLBACK", "finding": "SELL THESIS"}, ())
    final_upstream["E7"] = EngineResult("E7", "E7", True, 80.0, {"confirmation_state": "CONFIRMED"}, ())
    final_upstream["E8"] = EngineResult("E8", "E8", True, 80.0, {"economic_state": "READY"}, ())
    snapshot = {}
    e9_module.analyze_e9(snapshot, final_upstream)

    assert seen["e9"]["schema"] == "EVIDENCE_LEDGER_V1"
    assert seen["e9"]["phase"] == "FINAL_GOVERNANCE_E1_E8"
    assert seen["e9"]["decision"] is None
    assert set(seen["e9"]["brains"]) == set(final_upstream)

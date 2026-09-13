from types import SimpleNamespace

from production_v2.contracts import DecisionResult, EngineResult
from production_v2.opportunity_repricing_continuation import apply_opportunity_repricing
import production_v2.opportunity_repricing_runtime as repricing_runtime


def test_early_screen_geometry_blocker_enters_reprice_wait():
    lifecycle = {"state": "WATCHING", "lifecycle_stage": "WATCH", "direction": "BUY", "opportunity_id": "BUY|LOW_SWEEP|1"}
    e4 = {"auction_state": "PENDING"}
    e5 = {"available_space_atr_long": 0.89}
    e8 = {
        "economic_stage": "EARLY_OPPORTUNITY_SCREEN",
        "trade_authorized": False,
        "reason_codes": ["REAL_RR_BELOW_MINIMUM", "ENTRY_CONFIRMATION"],
    }
    result = apply_opportunity_repricing(lifecycle, e4=e4, e5=e5, e8=e8)
    assert result["lifecycle_stage"] == "REPRICE_WAIT"
    assert result["state"] == "REPRICE_WAIT"
    assert result["wait_for"] == "NEXT_CLOSED_M5_CANDLE_REPRICE"
    assert result["trade_authorized"] is False
    assert result["opportunity_id"] == lifecycle["opportunity_id"]


def test_terminal_opportunity_is_never_repriced():
    lifecycle = {"state": "INVALIDATED", "lifecycle_stage": "INVALIDATED", "direction": "BUY", "opportunity_id": "BUY|X|1"}
    e4 = {"auction_state": "PENDING"}
    e8 = {"economic_stage": "EARLY_OPPORTUNITY_SCREEN", "reason_codes": ["REAL_RR_BELOW_MINIMUM"]}
    result = apply_opportunity_repricing(lifecycle, e4=e4, e8=e8)
    assert result == lifecycle


def test_mature_economics_does_not_force_reprice():
    lifecycle = {"state": "WATCHING", "lifecycle_stage": "CONFIRMED", "direction": "BUY", "opportunity_id": "BUY|CONFIRM|1"}
    e4 = {"auction_state": "CONFIRMED"}
    e8 = {"economic_stage": "TRADE_READY", "trade_authorized": False, "reason_codes": []}
    result = apply_opportunity_repricing(lifecycle, e4=e4, e8=e8)
    assert result == lifecycle


def test_runtime_binding_updates_real_decision_result_not_only_dicts():
    class FakePipeline:
        def run(self, *args, **kwargs):
            engines = (
                EngineResult("E4", "E4", True, 60.0, {"auction_state": "PENDING"}),
                EngineResult("E5", "E5", True, 60.0, {"available_space_atr_long": 0.89}),
                EngineResult(
                    "E8",
                    "E8",
                    False,
                    0.0,
                    {
                        "economic_stage": "EARLY_OPPORTUNITY_SCREEN",
                        "trade_authorized": False,
                        "reason_codes": ["REAL_RR_BELOW_MINIMUM"],
                    },
                ),
                EngineResult("E9", "E9", False, 0.0, {"decision": "NO_TRADE", "reasons": []}),
            )
            risk = {
                "opportunity_lifecycle": {
                    "state": "WATCHING",
                    "lifecycle_stage": "WATCH",
                    "direction": "BUY",
                    "opportunity_id": "BUY|LOW_SWEEP|1",
                }
            }
            return DecisionResult("BTC/USD", "M5", "NO_TRADE", False, 0.0, engines, risk)

    fake_module = SimpleNamespace(ProductionPipeline=FakePipeline)
    repricing_runtime._INSTALLED = False
    assert repricing_runtime.install(fake_module) is True
    result = fake_module.ProductionPipeline().run({"bars": []})
    assert result.risk["opportunity_lifecycle"]["lifecycle_stage"] == "REPRICE_WAIT"
    assert result.risk["opportunity_lifecycle"]["opportunity_id"] == "BUY|LOW_SWEEP|1"
    assert result.risk["opportunity_repricing"]["reprice_required"] is True
    assert result.e9["action"] == "REPRICE_WAIT"
    assert result.e9["trade_authorized"] is False

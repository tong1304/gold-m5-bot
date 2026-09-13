from types import SimpleNamespace

from production_v2.contracts import DecisionResult, EngineResult
from production_v2.e8_early_opportunity_surgery import install as install_e8_early
from production_v2.opportunity_state_reconciliation import install as install_reconciliation


def _engine(engine_id, output, gate=False):
    return EngineResult(engine_id, engine_id, gate, 0.0, output, tuple(output.get("reason_codes", ())))


def test_early_opportunity_gets_economics_screen_without_authorization():
    calls = []

    def analyze(snapshot, results):
        calls.append(results["E6"].output.copy())
        e6 = results["E6"].output
        if e6.get("watch_only") or e6.get("setup") == "OPPORTUNITY_WATCH":
            return _engine("E8", {"finding": "NOT_APPLICABLE", "reason_codes": ["E6_THESIS_REQUIRED"]})
        return _engine("E8", {"finding": "UNRESOLVED", "economic_state": "NOT_EVALUABLE", "gate_passed": False})

    module = SimpleNamespace(analyze_e8=analyze)
    install_e8_early(module)
    e6 = _engine("E6", {
        "direction": "BUY",
        "setup": "OPPORTUNITY_WATCH",
        "watch_only": True,
        "early_candidate": True,
        "candidate_type": "EARLY_OPPORTUNITY_CANDIDATE",
    })
    result = module.analyze_e8({}, {"E6": e6})
    assert result.output["economic_stage"] == "EARLY_OPPORTUNITY_SCREEN"
    assert result.output["trade_authorized"] is False
    assert result.gate_passed is False
    assert calls[-1]["setup"] == "EARLY_OPPORTUNITY"
    assert calls[-1]["watch_only"] is False


def test_stale_confirmed_lifecycle_is_reconciled_to_watch():
    lifecycle = {
        "lifecycle_stage": "CONFIRMED",
        "state": "WAITING",
        "direction": "BUY",
        "opportunity_id": "BUY|OPPORTUNITY_WATCH|event-1",
        "event_id": "event-1",
        "opportunities": {"BUY": {"lifecycle_stage": "CONFIRMED", "state": "WAITING", "direction": "BUY", "opportunity_id": "BUY|OPPORTUNITY_WATCH|event-1"}},
        "trade_authorized": False,
    }
    engines = (
        _engine("E4", {"auction_state": "PENDING"}),
        _engine("E6", {"direction": "BUY", "watch_only": True, "e6_thesis_proven": False}),
        _engine("E7", {"confirmation_state": "PENDING"}),
        _engine("E8", {"economic_state": "NOT_APPLICABLE", "risk_ready": False}),
        _engine("E9", {"decision": "NO_TRADE"}),
    )
    base = DecisionResult(symbol="BTC/USD", engines=engines, risk={"opportunity_lifecycle": lifecycle})

    class Pipeline:
        def run(self, market_data, **kwargs):
            return base

    module = SimpleNamespace(ProductionPipeline=Pipeline)
    install_reconciliation(module)
    pipeline = module.ProductionPipeline()
    repaired = pipeline.run({"symbol": "BTC/USD", "candle_close_timestamp": "2026-09-13T16:40:00Z"})
    repaired_lifecycle = repaired.risk["opportunity_lifecycle"]
    assert repaired_lifecycle["lifecycle_stage"] == "WATCH"
    assert repaired_lifecycle["state"] == "WATCHING"
    assert repaired_lifecycle["trade_authorized"] is False
    assert repaired.decision == "NO_TRADE"
    assert "LIFECYCLE_STATE_RECONCILED" in repaired.reason_codes

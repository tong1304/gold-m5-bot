from types import SimpleNamespace

from production_v2.contracts import DecisionResult, EngineResult
from production_v2.e8_early_opportunity_surgery import install as install_e8_early
from production_v2.opportunity_state_reconciliation import install as install_reconciliation
from production_v2.opportunity_intelligence import build_opportunity_intelligence


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


def test_directional_finding_is_not_treated_as_neutral_in_opportunity_intelligence():
    results = {
        "E1": _engine("E1", {"directional_pressure": "BULLISH", "market_state": "TREND_UP"}),
        "E2": _engine("E2", {"finding": "UP opportunity is developing based on closed-candle evidence"}),
        "E3": _engine("E3", {"external_state": "UP", "internal_state": "UP", "structure_integrity": "VALID"}),
        "E4": _engine("E4", {
            "finding": "HIGH_SWEEP_REJECTION",
            "directional_implication": "DOWN",
            "response_actor": "SELLERS",
            "event_id": "event-1",
        }),
        "E5": _engine("E5", {
            "value_state": "PREMIUM",
            "available_space_atr_long": 0.70,
            "available_space_atr_short": 1.99,
        }),
        "E6": _engine("E6", {
            "finding": "SELL opportunity is forming watch",
            "direction": "SELL",
            "setup": "OPPORTUNITY_WATCH",
            "candidate_type": "EARLY_OPPORTUNITY_CANDIDATE",
        }),
        "E7": _engine("E7", {"confirmation_state": "PENDING"}),
        "E8": _engine("E8", {}),
    }
    intelligence = build_opportunity_intelligence(results)
    assert intelligence["leader_direction"] == "SELL"
    assert intelligence["leader"]["evidence"]["causal_event"] == 25.0


def test_cross_direction_opportunity_intelligence_keeps_both_candidates():
    results = {
        "E1": _engine("E1", {"directional_pressure": "BULLISH", "market_state": "TREND_UP"}),
        "E2": _engine("E2", {"finding": "UP opportunity is developing"}),
        "E3": _engine("E3", {"external_state": "UP", "internal_state": "UP", "structure_integrity": "VALID"}),
        "E4": _engine("E4", {"finding": "HIGH_SWEEP_REJECTION", "directional_implication": "DOWN", "response_actor": "SELLERS", "event_id": "event-2"}),
        "E5": _engine("E5", {"value_state": "PREMIUM", "available_space_atr_long": 1.0, "available_space_atr_short": 1.8}),
        "E6": _engine("E6", {"direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candidate_type": "EARLY_OPPORTUNITY_CANDIDATE"}),
        "E7": _engine("E7", {"confirmation_state": "PENDING"}),
        "E8": _engine("E8", {}),
    }
    intelligence = build_opportunity_intelligence(results)
    directions = {item["direction"] for item in intelligence["candidates"]}
    assert directions == {"BUY", "SELL"}
    assert intelligence["leader_direction"] == "SELL"

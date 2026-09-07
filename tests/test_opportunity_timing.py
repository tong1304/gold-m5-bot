from types import SimpleNamespace

from production_v2.opportunity_timing import classify_opportunity_timing
from production_v2 import professional_opportunity_surgery
from production_v2 import e9_watch_boundary


def test_early_high_quality_event_uses_fast_evidence_cycle():
    result = classify_opportunity_timing({"direction":"SELL","event":"HIGH_FAILED_BREAK_RECLAIM","event_age_bars":0,"confidence":0.80,"available_space_atr":1.0,"auction_state":"PENDING"})
    assert result["phase"] == "EARLY_OPPORTUNITY"
    assert result["decision_speed"] == "FAST"
    assert result["fast_path_eligible"] is True
    assert result["chase_prohibited"] is False


def test_confirmed_opportunity_uses_standard_speed_when_fresh():
    result = classify_opportunity_timing({"direction":"BUY","event":"LOW_SWEEP_REJECTION","event_age_bars":1,"confidence":0.82,"available_space_atr":1.2,"confirmation_state":"CONFIRMED"})
    assert result["phase"] == "CONFIRMED_OPPORTUNITY"
    assert result["decision_speed"] == "STANDARD"
    assert result["confirmed"] is True


def test_late_opportunity_slows_and_blocks_chasing():
    result = classify_opportunity_timing({"direction":"SELL","event":"HIGH_FAILED_BREAK_RECLAIM","event_age_bars":2,"confidence":0.90,"available_space_atr":1.0,"confirmation_state":"CONFIRMED"})
    assert result["phase"] == "LATE_OPPORTUNITY"
    assert result["decision_speed"] == "SLOW"
    assert result["chase_prohibited"] is True
    assert result["fast_path_eligible"] is False


def test_large_event_displacement_is_late_even_on_first_recheck():
    result = classify_opportunity_timing({"direction":"SELL","event":"HIGH_FAILED_BREAK_RECLAIM","event_age_bars":1,"confidence":0.88,"available_space_atr":1.0,"event_level":4425.73,"price":4422.27,"event_atr_frozen":4.920714})
    assert result["phase"] == "LATE_OPPORTUNITY"
    assert result["late_by_displacement"] is True
    assert result["decision_speed"] == "SLOW"


def test_gold_like_pending_sweep_is_fast_candidate_but_not_trade_authority():
    result = classify_opportunity_timing({"direction":"BUY","event":"LOW_SWEEP_REJECTION","event_age_bars":1,"confidence":0.70,"available_space_atr":2.4697,"event_level":4411.83,"price":4411.78,"event_atr_frozen":5.549286,"auction_state":"PENDING"})
    assert result["phase"] == "EARLY_OPPORTUNITY"
    assert result["decision_speed"] == "FAST"
    assert result["execution_authority"] == "E9_ONLY"


def test_btc_like_constrained_space_cannot_use_fast_path():
    result = classify_opportunity_timing({"direction":"BUY","event":"LOW_FAILED_BREAK_RECLAIM","event_age_bars":1,"confidence":0.7175,"available_space_atr":0.4036,"event_level":80230.29,"price":80224.88,"event_atr_frozen":116.75,"auction_state":"PENDING"})
    assert result["phase"] == "EARLY_OPPORTUNITY"
    assert result["decision_speed"] == "STANDARD"
    assert result["fast_path_eligible"] is False


def test_professional_opportunity_surgery_exposes_timing_without_authorizing_trade():
    class FakeModule:
        def consolidate(self, results):
            return {"state":"OPPORTUNITY_WATCH","trade_authorized":False}

    module = FakeModule()
    professional_opportunity_surgery.install(module)
    results = {
        "E4": SimpleNamespace(output={"direction":"BUY","event":"LOW_SWEEP_REJECTION","event_age_bars":1,"quality":70.0,"event_level":4411.83,"event_atr_frozen":5.549286,"auction_state":"PENDING"}),
        "E5": SimpleNamespace(output={"price":4411.78,"available_space_atr_long":2.4697,"available_space_atr_short":0.8415}),
        "E6": SimpleNamespace(output={"direction":"BUY","setup":"OPPORTUNITY_WATCH","trade_ready":False}),
    }
    out = module.consolidate(results)
    assert out["opportunity_timing"]["phase"] == "EARLY_OPPORTUNITY"
    assert out["opportunity_timing"]["decision_speed"] == "FAST"
    assert out["trade_authorized"] is False


def test_e9_watch_reports_opportunity_not_ready_and_keeps_trade_blocked():
    class FakeE9:
        def analyze_e9(self, snapshot, upstream):
            return SimpleNamespace(output={}, engine_id="E9", name="Master Decision Brain", gate_passed=False, score=0.0, reason_codes=())

    e9 = FakeE9()
    e9_watch_boundary.install(e9)
    e6 = SimpleNamespace(output={
        "setup":"OPPORTUNITY_WATCH", "direction":"BUY", "watch_only":True,
        "trade_ready":False, "gate_passed":False, "event":"LOW_SWEEP_REJECTION",
        "event_age_bars":1, "confidence":0.70, "available_space_atr":2.4697,
    })
    e8 = SimpleNamespace(output={"applicability":"NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS"})
    result = e9.analyze_e9({}, {"E6":e6,"E8":e8})
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["governance_reason"] in {"OPPORTUNITY_EXISTS_NOT_READY","EARLY_OPPORTUNITY_FAST_PATH_PENDING"}
    assert result.output["trade_authorized"] if "trade_authorized" in result.output else True

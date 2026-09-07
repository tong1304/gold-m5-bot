from types import SimpleNamespace

from production_v2.opportunity_timing import classify_opportunity_timing
from production_v2 import professional_opportunity_surgery
from production_v2 import e6_runtime_authority
from production_v2 import e7_thesis_boundary
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


def test_e6_runtime_authority_attaches_timing_to_live_callable():
    class FakeE6:
        def analyze_e6(self, market_data, upstream):
            return SimpleNamespace(engine_id="E6", name="Setup Brain", gate_passed=False, score=0.0, output={
                "setup":"OPPORTUNITY_WATCH",
                "direction":"SELL",
                "watch_only":True,
                "trade_ready":False,
                "candidate_type":"OPPORTUNITY_CANDIDATE",
            }, reason_codes=())

    e6 = FakeE6()
    e6_runtime_authority.install(e6)
    result = e6.analyze_e6({}, {
        "E4": SimpleNamespace(output={"event":"HIGH_SWEEP_REJECTION","event_age_bars":0,"auction_state":"PENDING","event_level":4409.78,"event_atr_frozen":7.75,"auction_quality":73.0}),
        "E5": SimpleNamespace(output={"price":4408.69,"available_space_atr_short":2.50,"available_space_atr_long":2.16}),
    })
    assert result.output["opportunity_timing"]["phase"] == "EARLY_OPPORTUNITY"
    assert result.output["opportunity_timing"]["decision_speed"] == "FAST"
    assert result.output["opportunity_fast_path"] is True
    assert result.output["execution_authority"] == "E9"


def test_early_opportunity_candidate_is_handed_to_e7_as_pending_confirmation():
    class FakeE7:
        def analyze_e7(self, snapshot, upstream):
            return SimpleNamespace(
                output={"state":"WAIT","confirmation":"UNRESOLVED","confirmation_state":"NOT_APPLICABLE","trade_decision_authority":False},
                engine_id="E7",
                name="Confirmation Brain",
                gate_passed=False,
                score=0.0,
                reason_codes=("CONFIRMATION_NOT_APPLICABLE",),
            )

    e7 = FakeE7()
    e7_thesis_boundary.install(e7)
    e6 = SimpleNamespace(output={
        "setup":"OPPORTUNITY_WATCH",
        "direction":"SELL",
        "candidate_type":"EARLY_OPPORTUNITY_CANDIDATE",
        "watch_only":True,
        "trade_ready":False,
        "gate_passed":False,
        "setup_exists":False,
        "thesis_status":"CONTESTED",
        "opportunity_phase_speed":"EARLY_OPPORTUNITY",
        "opportunity_decision_speed":"FAST",
        "opportunity_fast_path":True,
        "event":"HIGH_SWEEP_REJECTION",
        "event_age_bars":0,
        "available_space_atr":2.5,
        "thesis":"SELL liquidity-response hypothesis; confirmation still required.",
    })
    result = e7.analyze_e7({}, {"E6":e6})
    assert result.output["state"] == "WAIT"
    assert result.output["confirmation_state"] == "PENDING"
    assert result.output["trigger_status"] == "NOT_OBSERVED"
    assert result.output["trade_decision_authority"] is False
    assert "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION" in result.output["missing_evidence"]
    assert "E6_OPPORTUNITY_WATCH_NOT_SETUP" not in result.output["reason_codes"]


def test_e9_watch_reports_opportunity_not_ready_and_keeps_trade_blocked():
    class FakeE9:
        def analyze_e9(self, snapshot, upstream):
            return SimpleNamespace(output={}, engine_id="E9", name="Master Decision Brain", gate_passed=False, score=0.0, reason_codes=())

    e9 = FakeE9()
    e9_watch_boundary.install(e9)
    e6 = SimpleNamespace(output={"setup":"OPPORTUNITY_WATCH","direction":"BUY","watch_only":True,"trade_ready":False,"gate_passed":False,"event":"LOW_SWEEP_REJECTION","event_age_bars":1,"confidence":0.70,"available_space_atr":2.4697})
    e8 = SimpleNamespace(output={"applicability":"NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS"})
    result = e9.analyze_e9({}, {"E6":e6,"E8":e8})
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["governance_reason"] in {"OPPORTUNITY_EXISTS_NOT_READY","EARLY_OPPORTUNITY_FAST_PATH_PENDING"}
    assert result.output.get("trade_authorized", False) is False

from production_v2.e2_brain import analyze_e2


def _bars(n=80):
    bars=[]; price=3000.0
    for i in range(n):
        close=price-i*1.5; bars.append({"open":close+0.5,"high":close+1.0,"low":close-1.0,"close":close})
    return bars

def _uptrend_bars(n=100):
    bars=[]; price=3000.0
    for i in range(n):
        close=price+i*2.0; bars.append({"open":close-1.0,"high":close+1.2,"low":close-1.2,"close":close})
    return bars

def _transition_bars(n=100):
    bars=[]; price=3000.0
    for i in range(n):
        if i<n-12: close=price-i*1.8
        else: close=price-(n-12)*1.8+(i-(n-12))*7.0
        bars.append({"open":close-0.2,"high":close+1.5,"low":close-1.5,"close":close})
    return bars

def _balanced_range_bars(n=100):
    bars=[]
    for i in range(n):
        close=3000.0+(0.8 if i%4 in (0,1) else -0.8)
        bars.append({"open":close,"high":close+2.0,"low":close-2.0,"close":close})
    return bars

def _result(bars,e1=None):
    snapshot={"bars":bars}
    if e1 is not None: snapshot["E1"]=e1
    return analyze_e2(snapshot)

def test_e2_uses_core_brain_without_running_subengines():
    e1={"engine_id":"E1","evidence":{"output":{"directional_pressure":"BEARISH","market_state":"TREND_DOWN","confidence":0.9}},"reason_codes":[]}
    output=_result(_bars(),e1)
    assert output["architecture"]=="E2_PROFESSIONAL_OPPORTUNITY_CORE_V9"
    assert output["sub_engines_active"] is False
    assert output["direction"] in {"UP","DOWN","NEUTRAL"}
    assert output["opportunity_direction"] in {"UP","DOWN","NEUTRAL"}
    assert output["decision"] is None
    assert output["gate"] is None

def test_e2_does_not_convert_market_thesis_into_trade_decision():
    output=_result(_bars())
    assert output["decision"] is None
    assert output["entry"] is None
    assert output["trigger"] is None
    assert output.get("risk") is None
    assert output["gate"] is None
    assert output["opportunity_decision"] in {"WAIT","WATCH","NO_TRADE"}

def test_e2_professional_brain_publishes_a_complete_independent_thesis():
    output=_result(_uptrend_bars())
    assert output["regime"] in {"TREND","BREAKOUT"}
    assert output["direction"]=="UP"
    assert output["opportunity_direction"]=="UP"
    assert output["opportunity_state"] in {"ACTIONABLE_CONTEXT","DEVELOPING","WATCH","WAIT","VISIBLE","VISIBLE_PENDING_PROOF"}
    reasoning=output["professional_reasoning"]
    assert reasoning["question"]=="What opportunity is the market offering right now?"
    assert reasoning["thesis"]
    assert reasoning["independent_thesis"] is True
    assert reasoning["e1_used_as"]=="CROSS_CHECK_ONLY"
    assert reasoning["entry_authorized"] is False
    assert output["auction_state"] in {"ACCEPTING_UP","BALANCED","REPRICING_UP"}
    assert output["location_context"] in {"MID_RANGE","EDGE_HIGH","EDGE_LOW","FAVORABLE"}
    assert output["regime_confidence"]>0.0
    assert output["decision"] is None
    assert output["gate"] is None

def test_e2_does_not_turn_old_ema_bias_into_a_false_trend_during_repricing():
    output=_result(_transition_bars())
    assert output["regime"] in {"TREND","TRANSITION","BREAKOUT"}
    assert output["decision"] is None
    assert output["entry"] is None
    assert output["trigger"] is None
    assert output["gate"] is None
    if output["regime"]=="TRANSITION":
        assert output["direction"]=="NEUTRAL"
        assert output["opportunity_direction"]=="NEUTRAL"
        assert output["opportunity_state"]=="WAIT"

def test_e2_never_calls_the_middle_of_a_range_a_range_rotation_entry_opportunity():
    output=_result(_balanced_range_bars())
    assert output["regime"]=="RANGE"
    assert output["location_context"] in {"MID_RANGE","FAVORABLE"}
    assert output["opportunity_state"] in {"WAIT","VISIBLE","VISIBLE_PENDING_PROOF"}
    assert output["opportunity_decision"]=="WAIT"
    assert output["opportunity_direction"]=="NEUTRAL"
    assert output["decision"] is None
    assert output["gate"] is None

def test_e2_e1_is_only_cross_check_not_a_direction_override():
    bearish_e1={"engine_id":"E1","evidence":{"output":{"directional_pressure":"BEARISH","market_state":"TREND_DOWN","structure":"BEARISH"}},"reason_codes":[]}
    output=_result(_uptrend_bars(),bearish_e1)
    assert output["direction"]=="UP"
    assert output["opportunity_direction"]=="UP"
    assert output["independence"]=="E2_FIRST_E1_CROSS_CHECK"
    assert output["professional_reasoning"]["independent_thesis"] is True
    assert output["professional_reasoning"]["e1_used_as"]=="CROSS_CHECK_ONLY"
    assert output["decision"] is None
    assert output["gate"] is None

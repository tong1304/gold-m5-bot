from production_v2.e4_brain import analyze_e4


class _EngineResult:
    def __init__(self, output):
        self.output = output


def _bars(n=40, start=100.0):
    bars=[]
    price=start
    for i in range(n):
        o=price; c=price+(0.15 if i%2==0 else -0.05); h=max(o,c)+0.25; l=min(o,c)-0.25
        bars.append({'open':o,'high':h,'low':l,'close':c,'closed':True}); price=c
    return bars


def test_e4_professional_reasoning_contract():
    result=analyze_e4({'bars':_bars()})
    reasoning=result['professional_reasoning']
    for key in ('liquidity_event','take','response','acceptance','rejection','follow_through','thesis_status','counter_evidence','invalidation'):
        assert key in reasoning


def test_e4_never_claims_actual_participants_from_ohlc():
    result=analyze_e4({'bars':_bars()})
    assert result['professional_reasoning']['actor_identification']=='OHLC_INFERENCE_ONLY'
    assert result['audit']['actor_identification']=='PRICE_ACTION_INFERENCE_ONLY'


def test_e4_does_not_turn_pending_interaction_into_directional_confirmation():
    result=analyze_e4({'bars':_bars()})
    if result['professional_reasoning']['liquidity_event']['state']=='INTERACTION':
        assert result['professional_reasoning']['thesis_status']=='UNRESOLVED'
        assert result['direction_confirmed'] is False


def test_e4_accepts_production_pipeline_engine_results_without_using_upstream_decisions():
    bus={'E1':_EngineResult({'decision':'BUY','finding':'MARKET_STATE=TREND_UP'}),'E3':_EngineResult({'decision':'SELL','finding':'STRUCTURE_TRANSITION'})}
    result=analyze_e4({'bars':_bars()},bus)
    assert result['decision_authority']=='E9_ONLY'
    assert result['trade_decision_authority'] is False
    assert result['upstream_decisions_used'] is False
    assert result['upstream_gates_used'] is False
    assert result['scores_used'] is False

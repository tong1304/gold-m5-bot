import production_v2

from trading_system.engines.e1.a_data_quality import SubEngine as E1A
from trading_system.engines.e3.b_structure_classification import SubEngine as E3B
from trading_system.engines.e4.b_sweep_detection import SubEngine as E4B
from trading_system.engines.e6.f_setup_maturity import SubEngine as E6F


def market_snapshot():
    bars=[]; price=100.0
    for i in range(80):
        price += 0.35 if i < 55 else (-0.20 if i < 68 else 0.45)
        bars.append({'open':price-0.20,'high':price+0.45,'low':price-0.45,'close':price,'volume':100+i*3})
    return {'symbol':'XAU/USD','timeframe':'M5','bars':bars}


def test_subengines_emit_professional_evidence_contract():
    for cls in (E1A,E3B,E4B,E6F):
        r=cls().run(market_snapshot())
        for key in ('evidence_type','observations','analysis','evidence','counter_evidence','confidence','thesis','missing_evidence'):
            assert key in r.output


def test_specialists_do_not_return_static_scores_for_identical_market_state():
    rs=[E1A().run(market_snapshot()),E3B().run(market_snapshot()),E4B().run(market_snapshot()),E6F().run(market_snapshot())]
    assert len({r.score for r in rs}) >= 2
    assert len({r.output.get('evidence_type') for r in rs}) == 4


def test_context_is_evidence_only():
    s=market_snapshot();s['E3_result']={'3B':{'decision':'BUY','gate':True,'state':'BULLISH','direction':'UP'}}
    r=E6F().run(s)
    assert r.output.get('upstream_decisions_used') is False
    assert r.output.get('upstream_gates_used') is False

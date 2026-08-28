from __future__ import annotations
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
E1_PATH=ROOT/'production_v2'/'e1_professional_layer_v10.py'

def _bars(closes):
    out=[]
    for i,close in enumerate(closes):
        prev=closes[i-1] if i else close
        out.append({'open':prev,'high':max(prev,close)+.25,'low':min(prev,close)-.25,'close':close})
    return out

def test_v10_has_no_dependency_on_older_e1_layers():
    tree=ast.parse(E1_PATH.read_text(encoding='utf-8')); imported=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom): imported.append(node.module or '')
        elif isinstance(node,ast.Import): imported.extend(a.name for a in node.names)
    assert not any('e1_professional_layer_v' in name for name in imported)
    assert 'e1_brain' not in imported

def test_v10_is_market_state_only_and_exposes_professional_contract():
    from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10
    r=analyze_e1_professional_v10(_bars([5000.-i*2. for i in range(120)]))
    assert r['analysis_status']=='COMPLETE'
    assert r['market_state'] in {'TREND_UP','TREND_DOWN','RANGE','COMPRESSION','EXPANSION','TRANSITION','UNCLEAR'}
    assert r['dominant_direction'] in {'UP','DOWN','NEUTRAL'}
    assert r['e1_trade_authority'] is False and r['trade_decision_authority'] is False
    assert 'setup' not in r and 'entry' not in r and 'risk' not in r and 'decision' not in r
    assert r['e1_contract_version']=='PROFESSIONAL_MARKET_STATE_V10'

def test_v10_does_not_turn_one_counter_candle_into_reversal():
    from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10
    closes=[5000.-i*2. for i in range(119)]; closes.append(closes[-1]+12.)
    r=analyze_e1_professional_v10(_bars(closes))
    assert r['dominant_direction']=='DOWN'
    assert r['market_state']=='TREND_DOWN'
    assert r['counter_pressure']=='PULLBACK_WITHIN_TREND'
    assert r['transition_confirmed'] is False

def test_v10_withholds_classification_on_bad_data():
    from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10
    bars=_bars([5000.-i for i in range(80)]); bars[20]['close']='not-a-number'
    r=analyze_e1_professional_v10(bars)
    assert r['analysis_status']=='INCOMPLETE'
    assert r['market_state']=='UNCLEAR' and r['dominant_direction']=='NEUTRAL'
    assert r['trade_decision_authority'] is False

from __future__ import annotations
from typing import Any
from .e1_reconciliation import analyze_e1 as _base

def _atr14(bars):
    trs=[]; prev=None
    for b in bars[-14:]:
        h,l,c=float(b['high']),float(b['low']),float(b['close'])
        trs.append(h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev))); prev=c
    return sum(trs)/len(trs) if trs else 0.0

def analyze_e1(bars:list[dict[str,Any]]|None)->dict[str,Any]:
    r=_base(bars)
    if r.get('analysis_status')!='COMPLETE': return r
    clean=[b for b in (bars or []) if isinstance(b,dict) and all(k in b for k in ('high','low','close'))]
    if len(clean)<80:return r
    c=[float(b['close']) for b in clean];a=_atr14(clean)
    if a<=0:return r
    # Prior regime is measured before the latest 30 candles; recent impulse is
    # measured on the latest 10. This separates a regime handoff from ordinary
    # trend continuation.
    prior=(c[-31]-c[-71])/a;recent=(c[-1]-c[-11])/a
    if abs(prior)>=.35 and abs(recent)>=.80 and (prior>0)!=(recent>0):
        conflicts=list(r.get('conflicts',[]))
        if 'RECENT_IMPULSE_VS_PRIOR_CONTEXT' not in conflicts:conflicts.append('RECENT_IMPULSE_VS_PRIOR_CONTEXT')
        r['market_state']='TRANSITION';r['trend_state']='NONE';r['transition']='PRESENT';r['conflicts']=conflicts;r['reasons']=conflicts+['REGIME_CONFLICT_ACTIVE']
        pr=r['professional_reasoning'];pr['primary_state']='TRANSITION';pr['market_state']='TRANSITION';pr['trend_confirmed']=False;pr['trend_maturity']='DIRECTIONAL_ONLY';pr['classification_reason']='recent_impulse_conflicts_with_prior_persistent_context';pr['prior_context_slope_atr']=round(prior,4);pr['recent_impulse_slope_atr']=round(recent,4)
        r['reasoning_trace'].append(f'TRANSITION_GUARD -> prior_context40_atr={prior:.3f} recent10_atr={recent:.3f}')
        r['reasoning_trace'].append('TRANSITION_GUARD -> prior regime replaced by recent impulse; confirmation withheld')
    return r

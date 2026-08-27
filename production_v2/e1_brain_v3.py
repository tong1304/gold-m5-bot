from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
QUESTION = "What is the market doing right now?"
OWNERSHIP = {"owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "market_regime", "regime_transition"], "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution"]}

def _num(x):
    try: x=float(x)
    except (TypeError,ValueError): return None
    return x if isfinite(x) else None

def _ema(xs,p):
    if not xs:return []
    a=2/(p+1); cur=xs[0]; out=[cur]
    for x in xs[1:]: cur=a*x+(1-a)*cur; out.append(cur)
    return out

def _atr(bars,n=14):
    trs=[]; prev=None
    for b in bars[-n:]:
        h,l,c=b['high'],b['low'],b['close']; trs.append(h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev))); prev=c
    return mean(trs) if trs else 0.0

def _slope(xs,a,n): return 0.0 if len(xs)<=n or a<=0 else (xs[-1]-xs[-1-n])/a

def _eff(xs,n):
    x=xs[-n:]
    if len(x)<2:return 0.0
    path=sum(abs(x[i]-x[i-1]) for i in range(1,len(x)))
    return abs(x[-1]-x[0])/max(path,1e-12)

def _structure(bars):
    hs=[];ls=[];w=2
    for i in range(w,len(bars)-w):
        win=bars[i-w:i+w+1]; h,l=bars[i]['high'],bars[i]['low']
        if h>=max(x['high'] for x in win):hs.append(h)
        if l<=min(x['low'] for x in win):ls.append(l)
    hs,ls=hs[-6:],ls[-6:]
    hh=sum(hs[i]>hs[i-1] for i in range(1,len(hs)));lh=sum(hs[i]<hs[i-1] for i in range(1,len(hs)));hl=sum(ls[i]>ls[i-1] for i in range(1,len(ls)));ll=sum(ls[i]<ls[i-1] for i in range(1,len(ls)))
    bull,bear=min(hh,hl),min(lh,ll)
    if bull>=2 and bull>bear:return 'BULLISH',min(1,.65+.08*bull)
    if bear>=2 and bear>bull:return 'BEARISH',min(1,.65+.08*bear)
    if hh+hl>=2 and hh+hl>lh+ll:return 'BULLISH',.55
    if lh+ll>=2 and lh+ll>hh+hl:return 'BEARISH',.55
    return 'MIXED',.30

def analyze_e1(bars:list[dict[str,Any]]|None)->dict[str,Any]:
    valid=[];bad=[]
    for i,b in enumerate(bars or []):
        if not isinstance(b,dict):bad.append(f'bar_{i}_not_mapping');continue
        v={k:_num(b.get(k)) for k in ('open','high','low','close')}
        if any(x is None for x in v.values()):bad.append(f'bar_{i}_ohlc_invalid');continue
        if v['high']<max(v['open'],v['close']) or v['low']>min(v['open'],v['close']) or v['high']<v['low']:bad.append(f'bar_{i}_ohlc_inconsistent');continue
        valid.append({**b,**v})
    base={'question':QUESTION,'reasoning_role':'MARKET_STATE_ANALYST','trade_decision_authority':False,'decision_authority':'E9_ONLY'}
    if len(valid)<60:return {**base,'market_state':'UNCLEAR','directional_pressure':'NEUTRAL','trend_state':'NONE','volatility_state':'UNKNOWN','structure_state':'UNCLEAR','structure_quality':0.0,'compression':'UNKNOWN','expansion':'UNKNOWN','transition':'UNKNOWN','confidence':0.0,'evidence':['valid_candles_below_minimum'],'conflicts':bad[:6],'reasons':['insufficient reliable candles; classification withheld'],'analysis_status':'INCOMPLETE','professional_reasoning':{'task':'DESCRIBE_MARKET_STATE_ONLY','trend_maturity':'UNAVAILABLE','trend_confirmed':False,'classification_reason':'insufficient reliable candles; classification withheld','ownership_boundaries':OWNERSHIP}}
    c=[b['close'] for b in valid];a=_atr(valid)
    if a<=0:return {**base,'market_state':'UNCLEAR','directional_pressure':'NEUTRAL','trend_state':'NONE','volatility_state':'UNKNOWN','structure_state':'UNCLEAR','structure_quality':0.0,'compression':'UNKNOWN','expansion':'UNKNOWN','transition':'UNKNOWN','confidence':0.0,'evidence':['atr_invalid'],'conflicts':['ATR_INVALID'],'reasons':['ATR invalid; classification withheld'],'analysis_status':'INCOMPLETE','professional_reasoning':{'task':'DESCRIBE_MARKET_STATE_ONLY','trend_maturity':'UNAVAILABLE','trend_confirmed':False,'classification_reason':'ATR invalid; classification withheld','ownership_boundaries':OWNERSHIP}}
    e20s,e50s=_ema(c,20),_ema(c,50);rel='UP' if e20s[-1]>e50s[-1] else 'DOWN' if e20s[-1]<e50s[-1] else 'FLAT';gap=(e20s[-1]-e50s[-1])/a
    es20,es50=_slope(e20s,a,5),_slope(e50s,a,5);ss,ms,ls=(_slope(c,a,n) for n in (5,10,20))
    dirs=['UP' if ss>.15 else 'DOWN' if ss<-.15 else 'FLAT','UP' if ms>.20 else 'DOWN' if ms<-.20 else 'FLAT','UP' if ls>.30 else 'DOWN' if ls<-.30 else 'FLAT'];up,down=dirs.count('UP'),dirs.count('DOWN');pressure='UP' if up>down else 'DOWN' if down>up else 'BALANCED'
    aligned=sum((ss>=.20,ms>=.30,ls>=.45)) if pressure=='UP' else sum((ss<=-.20,ms<=-.30,ls<=-.45)) if pressure=='DOWN' else 0;persistence=aligned/3;e10,e20=_eff(c,10),_eff(c,20);structure,sq=_structure(valid);sd='UP' if structure=='BULLISH' else 'DOWN' if structure=='BEARISH' else 'FLAT'
    ema_ok=pressure in ('UP','DOWN') and rel==pressure and ((pressure=='UP' and es20>=-.05 and es50>=-.10) or (pressure=='DOWN' and es20<=.05 and es50<=.10));ema_conflict=pressure in ('UP','DOWN') and rel in ('UP','DOWN') and rel!=pressure;struct_conflict=pressure in ('UP','DOWN') and sd in ('UP','DOWN') and sd!=pressure;horizon_conflict=len({x for x in dirs if x in ('UP','DOWN')})>1
    conflicts=[]
    if bad:conflicts.append('DATA_QUALITY_ANOMALIES')
    if ema_conflict:conflicts.append('EMA_VS_PRICE_PRESSURE')
    if struct_conflict:conflicts.append('STRUCTURE_VS_PRICE_PRESSURE')
    if horizon_conflict:conflicts.append('SHORT_VS_LONG_HORIZON')
    if pressure=='BALANCED':conflicts.append('DIRECTIONAL_PRESSURE_BALANCED')
    consensus=pressure in ('UP','DOWN') and max(up,down)>=2 and persistence>=2/3;strong_structure=sd==pressure and sq>=.55
    trend=consensus and ema_ok and abs(gap)>=.10 and e20>=.12 and not ema_conflict and not struct_conflict and (strong_structure or persistence==1.0)
    transition=(not trend) and ((ema_conflict and persistence>=1/3) or (struct_conflict and persistence>=1/3) or (horizon_conflict and e20<.45))
    ar=_atr(valid,14)/max(_atr(valid,50),1e-12);compression=ar<.78;expansion=ar>1.18
    if compression and pressure=='BALANCED':state,fp,reason='COMPRESSION','BALANCED','volatility_compression_with_balanced_direction'
    elif transition:state,fp,reason='TRANSITION',pressure,'material_conflict_between_regime_dimensions'
    elif trend:state,fp,reason=('TREND_UP' if pressure=='UP' else 'TREND_DOWN'),pressure,'persistent_multi_horizon_direction_with_ema_and_structure_coherence'
    elif expansion and pressure in ('UP','DOWN') and e10>=.25:state,fp,reason='EXPANSION',pressure,'volatility_expansion_with_directional_displacement'
    elif pressure=='BALANCED' and e20<.35:state,fp,reason='RANGE','BALANCED','low_directional_efficiency_and_balanced_pressure'
    elif pressure in ('UP','DOWN') and consensus and ema_ok and e20>=.12:state,fp,reason='DEVELOPING',pressure,'directional_regime_developing_without_full_confirmation'
    elif pressure in ('UP','DOWN'):state,fp,reason='UNCLEAR',pressure,'directional_evidence_exists_but_regime_confirmation_is_insufficient'
    else:state,fp,reason='UNCLEAR','BALANCED','directional_evidence_is_balanced'
    maturity='ESTABLISHED' if trend else 'DEVELOPING' if pressure in ('UP','DOWN') and consensus and ema_ok else 'DIRECTIONAL_ONLY' if pressure in ('UP','DOWN') else 'NONE';pl='BULLISH' if fp=='UP' else 'BEARISH' if fp=='DOWN' else 'NEUTRAL';ts='UP' if state=='TREND_UP' else 'DOWN' if state=='TREND_DOWN' else 'NONE';tr='PRESENT' if state=='TRANSITION' else 'ABSENT';conf=round(min(.99,max(0,.45+.25*sq+.20*persistence+.10*min(1,e20/.7)+.10*float(ema_ok)-.05*len(conflicts))),3)
    evidence=[f'ema20_vs_ema50={rel}',f'ema_gap_atr={gap:.3f}',f'ema20_slope_atr={es20:.3f}',f'ema50_slope_atr={es50:.3f}',f'price_slope_atr={ss:.3f}',f'price_medium_slope_atr={ms:.3f}',f'price_long_slope_atr={ls:.3f}',f'structure={structure}',f'structure_quality={sq:.3f}',f'directional_pressure={pl}',f'price_consensus={max(up,down)}/3',f'trend_persistence={persistence:.3f}',f'price_efficiency_10={e10:.3f}',f'price_efficiency_20={e20:.3f}',f'trend_maturity={maturity}']
    reasons=list(conflicts)+(['REGIME_CONFLICT_ACTIVE'] if state=='TRANSITION' else ['REGIME_CONFIRMATION_INSUFFICIENT'] if state=='UNCLEAR' else [])
    return {**base,'market_state':state,'directional_pressure':pl,'trend_state':ts,'volatility_state':'EXPANDING' if expansion else 'CONTRACTING' if compression else 'NORMAL','structure_state':structure,'structure_quality':round(sq,3),'compression':'PRESENT' if compression else 'ABSENT','expansion':'PRESENT' if expansion else 'ABSENT','transition':tr,'confidence':conf,'evidence':evidence,'conflicts':conflicts,'reasons':reasons,'reasoning_trace':[f'QUESTION -> {QUESTION}',f'STRUCTURE -> {structure} quality={sq:.2f}',f'PRESSURE -> {pl} short={dirs[0]} medium={dirs[1]} long={dirs[2]}',f'PERSISTENCE -> {persistence:.2f}',f'REGIME_CONFIRMATION -> trend_confirmed={trend} maturity={maturity}',f'STATE -> {state} because={reason}',f'TRANSITION -> {tr}'],'professional_reasoning':{'task':'DESCRIBE_MARKET_STATE_ONLY','primary_state':state,'market_state':state,'direction':fp,'directional_pressure':pl,'trend_maturity':maturity,'trend_confirmed':trend,'conflict_detected':bool(conflicts),'conflict_count':len(conflicts),'classification_reason':reason,'directional_consensus':{'ema':rel,'short':dirs[0],'medium':dirs[1],'long':dirs[2],'confirmed':ema_ok and consensus,'count':max(up,down),'required_count':2},'independent_evidence':{'ema_gap_atr':round(gap,4),'structure':structure,'structure_quality':round(sq,3),'efficiency_10':round(e10,4),'efficiency_20':round(e20,4)},'ownership_boundaries':OWNERSHIP},'analysis_status':'COMPLETE'}

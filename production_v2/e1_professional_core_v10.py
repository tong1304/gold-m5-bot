"""Standalone E1 V10 market-state core. No dependency on other engines."""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

QUESTION="What is the market doing right now?"
MIN_BARS=60

def _num(x:Any)->float|None:
    try:x=float(x)
    except(TypeError,ValueError):return None
    return x if isfinite(x) else None

def _clean(bs):
    good=[]; bad=0
    for raw in bs or []:
        if not isinstance(raw,dict):bad+=1;continue
        v={k:_num(raw.get(k)) for k in ('open','high','low','close')}
        if any(x is None for x in v.values()):bad+=1;continue
        o,h,l,c=v['open'],v['high'],v['low'],v['close']
        if h<l or h<max(o,c) or l>min(o,c):bad+=1;continue
        good.append({**raw,**v})
    return good,bad

def _ema(xs,n):
    if not xs:return []
    a=2/(n+1);cur=xs[0];out=[cur]
    for x in xs[1:]:cur=a*x+(1-a)*cur;out.append(cur)
    return out

def _atr(bs,n=14):
    trs=[];prev=None
    for b in bs[-n:]:
        h,l,c=float(b['high']),float(b['low']),float(b['close'])
        trs.append(h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev)));prev=c
    return mean(trs) if trs else 0.

def _slope(xs,atr,n):return 0. if atr<=0 or len(xs)<=n else (xs[-1]-xs[-1-n])/atr

def _eff(xs,n):
    s=xs[-n:]
    if len(s)<2:return 0.
    path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return abs(s[-1]-s[0])/max(path,1e-12)

def _structure(bs,atr):
    hs=[];ls=[];w=2
    for i in range(w,len(bs)-w):
        z=bs[i-w:i+w+1];h=float(bs[i]['high']);l=float(bs[i]['low'])
        if h>=max(float(x['high']) for x in z):hs.append(h)
        if l<=min(float(x['low']) for x in z):ls.append(l)
    hs,ls=hs[-8:],ls[-8:]
    hh=sum(hs[i]>hs[i-1] for i in range(1,len(hs)));lh=sum(hs[i]<hs[i-1] for i in range(1,len(hs)))
    hl=sum(ls[i]>ls[i-1] for i in range(1,len(ls)));ll=sum(ls[i]<ls[i-1] for i in range(1,len(ls)))
    bull,bear=min(hh,hl),min(lh,ll)
    if bull>=2 and bull>bear:state,q='BULLISH',min(1.,.62+.07*bull)
    elif bear>=2 and bear>bull:state,q='BEARISH',min(1.,.62+.07*bear)
    elif hh+hl>=2 and hh+hl>lh+ll:state,q='BULLISH',.52
    elif lh+ll>=2 and lh+ll>hh+hl:state,q='BEARISH',.52
    else:state,q='MIXED',.30
    last=float(bs[-1]['close']);hi=max(hs,default=last);lo=min(ls,default=last);buf=max(.1*atr,1e-12)
    return {'state':state,'quality':q,'counts':{'HH':hh,'HL':hl,'LH':lh,'LL':ll},'bos':'UP' if last>hi+buf else 'DOWN' if last<lo-buf else 'NONE'}

def _dir(s):return 'UP' if s=='BULLISH' else 'DOWN' if s=='BEARISH' else 'NEUTRAL'
def _opp(d):return 'DOWN' if d=='UP' else 'UP' if d=='DOWN' else 'NEUTRAL'

def _incomplete(reason,v,b):
    return {'question':QUESTION,'reasoning_role':'MARKET_STATE_ANALYST','trade_decision_authority':False,'decision_authority':'E9_ONLY','architecture':'E1_STANDALONE_PROFESSIONAL_V10','market_state':'UNCLEAR','trend_state':'NONE','volatility_state':'UNKNOWN','structure_state':'UNCLEAR','structure_quality':0.,'directional_pressure':'NEUTRAL','current_pressure':'NEUTRAL','counter_pressure':'NONE','dominant_direction':'NEUTRAL','directional_state':'UNRESOLVED','market_phase':'UNRESOLVED','range_state':'UNKNOWN','compression':'UNKNOWN','expansion':'UNKNOWN','transition':'UNKNOWN','transition_status':'UNRESOLVED','transition_confirmed':False,'transition_committed':False,'structural_persistence':False,'confidence':0.,'evidence':[f'valid_candles={v}',f'invalid_candles={b}'],'observations':[f'valid_candles={v}',f'invalid_candles={b}'],'conflicts':['DATA_QUALITY_ANOMALIES'] if b else [],'reasons':[reason],'reasoning_trace':[f'QUESTION -> {QUESTION}',f'STATE -> UNCLEAR because={reason}'],'professional_reasoning':{'task':'DESCRIBE_MARKET_STATE_ONLY','market_state':'UNCLEAR','direction':'NEUTRAL','status':'UNRESOLVED','decision_boundary':'MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION'},'e1_contract_version':'PROFESSIONAL_MARKET_STATE_V10','e1_trade_authority':False,'analysis_status':'INCOMPLETE'}

def analyze_e1_professional_v10(bs):
    good,bad=_clean(bs)
    if len(good)<MIN_BARS:return _incomplete('INSUFFICIENT_RELIABLE_CLOSED_CANDLES',len(good),bad)
    if bad:return _incomplete('DATA_QUALITY_ANOMALIES_PRESENT_CLASSIFICATION_WITHHELD',len(good),bad)
    c=[float(b['close']) for b in good];atr=_atr(good);atr50=_atr(good,50)
    if atr<=0 or atr50<=0:return _incomplete('ATR_INVALID',len(good),bad)
    e20s,e50s=_ema(c,20),_ema(c,50);e20,e50=e20s[-1],e50s[-1];ema='UP' if e20>e50 else 'DOWN' if e20<e50 else 'NEUTRAL';gap=(e20-e50)/atr
    hz=(5,10,20,40);th=(.15,.20,.30,.40);sl=[_slope(c,atr,n) for n in hz];states=['UP' if s>=t else 'DOWN' if s<=-t else 'FLAT' for s,t in zip(sl,th)]
    up,down=states.count('UP'),states.count('DOWN');pressure='UP' if up>down else 'DOWN' if down>up else 'NEUTRAL';cons=max(up,down)/4;longs=states[1:];lu,ld=longs.count('UP'),longs.count('DOWN');lcons=max(lu,ld)/3
    if pressure=='UP':persist=sum(s>=t for s,t in zip(sl,(.20,.25,.35,.45)))/4;lp=sum(s>=t for s,t in zip(sl[1:],(.25,.35,.45)))/3
    elif pressure=='DOWN':persist=sum(s<=-t for s,t in zip(sl,(.20,.25,.35,.45)))/4;lp=sum(s<=-t for s,t in zip(sl[1:],(.25,.35,.45)))/3
    else:persist=lp=0.
    st=_structure(good,atr);sd=_dir(st['state']);sr=_dir(_structure(good[-80:],_atr(good[-80:]))['state']);s40=_dir(_structure(good[-40:],_atr(good[-40:]))['state']);sp=sd in ('UP','DOWN') and sd==sr==s40
    prior=_atr(good[-64:-14],50) if len(good)>=64 else atr50;vr=atr/max(prior,1e-12);eff20,eff40=_eff(c,20),_eff(c,40);compression=vr<.78;expansion=vr>1.20
    recent_delta=c[-1]-c[-6];recent='UP' if recent_delta>=.15*atr else 'DOWN' if recent_delta<=-.15*atr else 'NEUTRAL';ctx=_slope(c,atr,30);recent8=_slope(c,atr,8);flip=abs(ctx)>=.45 and abs(recent8)>=.65 and (ctx>0)!=(recent8>0)
    strong=sd in ('UP','DOWN') and st['quality']>=.52;long_dir='UP' if lu>ld else 'DOWN' if ld>lu else 'NEUTRAL';long_aligned=long_dir in ('UP','DOWN') and lcons>=2/3 and lp>=2/3
    if strong and sd==ema and long_aligned:dom,basis=sd,'PERSISTENT_STRUCTURE_EMA_LONG_HORIZON_ALIGNMENT'
    elif strong and sd==ema and abs(gap)>=.50:dom,basis=sd,'STRUCTURE_EMA_ALIGNMENT'
    elif long_aligned and ema==long_dir and abs(gap)>=.50:dom,basis=long_dir,'LONG_HORIZON_EMA_ALIGNMENT'
    elif strong and long_aligned:dom,basis=sd,'STRUCTURE_LONG_HORIZON_ALIGNMENT'
    else:dom,basis='NEUTRAL','NO_DOMINANT_REGIME'
    opp=_opp(dom);os=strong and sd==opp;orc=sr==opp;ol=s40==opp;oe=ema==opp;osl=(sl[2]>=.30 and sl[3]>=.40) if opp=='UP' else (sl[2]<=-.30 and sl[3]<=-.40) if opp=='DOWN' else False;opr=recent==opp;ts=sum((os,orc,ol,oe,osl,opr,flip));confirmed=dom in ('UP','DOWN') and os and orc and ol and oe and osl and opr and flip
    if confirmed:state,transition='TRANSITION','CONFIRMED'
    elif dom in ('UP','DOWN'):state,transition=('TREND_UP' if dom=='UP' else 'TREND_DOWN'),('WATCH' if ts>=2 else 'ABSENT')
    elif compression:state,transition='COMPRESSION',('WATCH' if flip else 'ABSENT')
    elif expansion:state,transition='EXPANSION',('WATCH' if flip else 'ABSENT')
    elif abs(sl[2])<.65 and eff20<.35 and eff40<.40:state,transition='RANGE','ABSENT'
    else:state,transition='UNCLEAR',('WATCH' if flip else 'ABSENT')
    phase='IMPULSE' if recent==dom else 'PULLBACK' if dom in ('UP','DOWN') and recent==opp else 'CONSOLIDATION' if dom in ('UP','DOWN') else 'UNRESOLVED';current='BULLISH' if recent=='UP' else 'BEARISH' if recent=='DOWN' else 'NEUTRAL';counter='PULLBACK_WITHIN_TREND' if phase=='PULLBACK' else 'NONE'
    align=1. if dom in ('UP','DOWN') and sd==dom else 0.;ealign=1. if dom in ('UP','DOWN') and ema==dom else 0.;support=.30*cons+.20*lcons+.20*lp+.20*align+.10*ealign;stability=.40*lcons+.30*lp+.20*align+.10*(0 if flip else 1);cscore=ts/7;confidence=max(0.,min(.99,.65*support+.25*stability+.10*max(eff20,eff40)-.25*cscore));
    if state=='UNCLEAR':confidence=min(confidence,.60)
    if confirmed:confidence=min(confidence,.80)
    dstate='CONFIRMED' if state in ('TREND_UP','TREND_DOWN') and confidence>=.60 else 'DEVELOPING' if dom in ('UP','DOWN') else 'NEUTRAL'
    conflicts=[]
    if ema in ('UP','DOWN') and pressure in ('UP','DOWN') and ema!=pressure:conflicts.append('EMA_VS_PRICE_PRESSURE')
    if sd in ('UP','DOWN') and recent in ('UP','DOWN') and sd!=recent:conflicts.append('STRUCTURE_VS_RECENT_PRESSURE')
    if up and down:conflicts.append('MULTI_HORIZON_DISAGREEMENT')
    if flip:conflicts.append('CONTEXT_FLIP_CONFIRMED' if confirmed else 'CONTEXT_FLIP_UNCONFIRMED')
    reasons=['V10_STANDALONE_E1','V10_DATA_INTEGRITY_VALIDATED','V10_STRUCTURE_FIRST_HIERARCHY','V10_LONG_HORIZON_CONFIRMATION','V10_COUNTER_PRESSURE_IS_PHASE_NOT_REVERSAL','V10_TRANSITION_REQUIRES_PERSISTENT_OPPOSITE_EVIDENCE','V10_MARKET_STATE_ONLY_BOUNDARY']+(['COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL'] if counter else [])+(['V10_TRANSITION_CONFIRMED'] if confirmed else [])+(['V10_CONTEXT_FLIP_REQUIRES_STRUCTURAL_CONFIRMATION'] if flip and not confirmed else [])+conflicts
    trans={'status':transition,'confirmed':confirmed,'committed':confirmed,'score':ts,'evidence':[n for ok,n in ((os,'OPPOSITE_STRUCTURE'),(orc,'OPPOSITE_RECENT_STRUCTURE'),(ol,'OPPOSITE_LOOKBACK_STRUCTURE'),(oe,'OPPOSITE_EMA'),(osl,'OPPOSITE_LONG_HORIZON_SLOPES'),(opr,'OPPOSITE_RECENT_PRESSURE'),(flip,'CONTEXT_FLIP')) if ok],'required_for_commitment':['PERSISTENT_OPPOSITE_STRUCTURE','OPPOSITE_EMA_CONTEXT','OPPOSITE_LONG_HORIZON_SLOPES','OPPOSITE_RECENT_PRESSURE','CONTEXT_REPRICING']}
    thesis={'direction':dom,'label':'BULLISH' if dom=='UP' else 'BEARISH' if dom=='DOWN' else 'NEUTRAL','status':dstate,'market_state':state,'phase':phase,'support_score':round(support,3),'counter_score':round(cscore,3),'supporting_evidence':[basis,'LONG_HORIZON_ALIGNED' if long_aligned else 'LONG_HORIZON_NOT_ALIGNED'],'counter_evidence':conflicts+(['COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL'] if counter else [])}
    pr={'task':'DESCRIBE_MARKET_STATE_ONLY','question':QUESTION,'primary_thesis':thesis,'market_state':state,'trend_state':dom if state in ('TREND_UP','TREND_DOWN') else 'NONE','dominant_direction':dom,'market_phase':phase,'current_pressure':current,'counter_pressure':counter,'transition_status':transition,'state_stability':{'score':round(stability,3),'status':'STABLE' if stability>=.70 and not confirmed else 'WATCH' if stability>=.45 else 'UNSTABLE'},'transition_evidence':trans,'decision_boundary':'MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION','e1_telemetry_authority':'TOP_LEVEL_E1_OUTPUT'}
    evidence=[f'valid_candles={len(good)}',f'invalid_candles={bad}',f'ema20_vs_ema50={ema}',f'ema_gap_atr={gap:.3f}',*(f'price_slope_{n}_atr={s:.3f}' for n,s in zip(hz,sl)),f'multi_horizon={",".join(states)}',f'directional_consensus={cons:.3f}',f'long_horizon_consensus={lcons:.3f}',f'long_horizon_persistence={lp:.3f}',f'structure={st["state"]}',f'structure_quality={st["quality"]:.3f}',f'structure_persistence={sp}',f'volatility_ratio={vr:.3f}',f'volatility={"CONTRACTING" if compression else "EXPANDING" if expansion else "NORMAL"}',f'recent_pressure={recent}',f'dominant_direction={dom}']
    trace=[f'QUESTION -> {QUESTION}','DATA -> closed-candle OHLC validated',f'STRUCTURE -> {st["state"]} quality={st["quality"]:.2f} persistent={sp}',f'PRESSURE -> current={current} multi_horizon={",".join(states)}',f'LONG_HORIZON -> consensus={lcons:.3f} persistence={lp:.3f}',f'DOMINANT_CONTEXT -> {dom} basis={basis}',f'PHASE -> {phase}',f'TRANSITION -> {transition} score={ts} confirmed={confirmed}','RULE -> persistent structure and long-horizon context outrank short counter-pressure','BOUNDARY -> E1 reports market state only']
    return {'question':QUESTION,'reasoning_role':'MARKET_STATE_ANALYST','trade_decision_authority':False,'decision_authority':'E9_ONLY','architecture':'E1_STANDALONE_PROFESSIONAL_V10','market_state':state,'trend_state':dom if state in ('TREND_UP','TREND_DOWN') else 'NONE','volatility_state':'CONTRACTING' if compression else 'EXPANDING' if expansion else 'NORMAL','structure_state':st['state'],'structure_quality':round(st['quality'],3),'directional_pressure':dom,'current_pressure':current,'counter_pressure':counter,'dominant_direction':dom,'directional_state':dstate,'market_phase':phase,'range_state':'RANGE' if state=='RANGE' else 'NOT_RANGE','compression':'YES' if compression else 'NO','expansion':'YES' if expansion else 'NO','transition':transition,'transition_status':transition,'transition_confirmed':confirmed,'transition_committed':confirmed,'structural_regime':sd,'structural_regime_recent':sr,'structural_regime_lookback':s40,'structural_persistence':sp,'confidence':round(confidence,3),'evidence':evidence,'observations':evidence,'conflicts':conflicts,'reasons':list(dict.fromkeys(reasons)),'reasoning_trace':trace,'professional_reasoning':pr,'independent_evidence':{'data_quality':{'valid_candles':len(good),'invalid_candles':bad},'structure':st,'pressure':{'direction':pressure,'recent':recent,'consensus':cons},'persistence':{'score':persist,'long_horizon_score':lp,'efficiency20':eff20,'efficiency40':eff40},'ema':{'relation':ema,'gap_atr':gap},'volatility':{'atr14':atr,'prior':prior,'ratio':vr},'transition':trans},'e1_contract_version':'PROFESSIONAL_MARKET_STATE_V10','e1_trade_authority':False,'analysis_status':'COMPLETE'}

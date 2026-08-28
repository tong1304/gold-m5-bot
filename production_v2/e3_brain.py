from __future__ import annotations
from statistics import mean
from typing import Any

QUESTION='What is price structure communicating?'
ARCHITECTURE='E3_SINGLE_PROFESSIONAL_BRAIN_V9'
UP,DOWN,NEUTRAL,MIXED='UP','DOWN','NEUTRAL','MIXED'
MIN_CANDLES=40
IR,ER=2,5
PROMINENCE_ATR=.10
EQ_TOLERANCE_ATR=.10
BOS_CLOSE_ATR=.08
BOS_BODY_ATR=.20
BOS_CLOSE_LOCATION=.55
FOLLOW_THROUGH_BARS=2

def _num(v:Any):
    try:
        x=float(v); return x if x==x and abs(x)!=float('inf') else None
    except (TypeError,ValueError): return None

def _clean(bars):
    out=[]; reasons=[]
    for i,b in enumerate(bars or []):
        if not isinstance(b,dict): reasons.append(f'bar_{i}_not_mapping'); continue
        o,h,l,c=[_num(b.get(k)) for k in ('open','high','low','close')]
        if any(x is None for x in (o,h,l,c)): reasons.append(f'bar_{i}_ohlc_invalid'); continue
        if h<max(o,c) or l>min(o,c) or h<l: reasons.append(f'bar_{i}_ohlc_inconsistent'); continue
        out.append({'open':o,'high':h,'low':l,'close':c})
    return out,reasons

def _tr(b,i):
    if i<=0:return 0.
    x,p=b[i],b[i-1]['close']; return max(x['high']-x['low'],abs(x['high']-p),abs(x['low']-p))

def _atr(b,p=14): return mean(_tr(b,i) for i in range(max(1,len(b)-p),len(b))) if len(b)>1 else 0.

def _atr_at(b,i,p=14): return mean(_tr(b,j) for j in range(max(1,i-p+1),i+1)) if i>0 else 0.

def _pivots(b,side,r):
    out=[]
    for i in range(r,len(b)-r):
        x=b[i][side]; L=[b[j][side] for j in range(i-r,i)]; R=[b[j][side] for j in range(i+1,i+r+1)]; prom=PROMINENCE_ATR*max(_atr_at(b,i),1e-12)
        ok=(x>=max(L) and x>max(R) and min(x-max(L),x-max(R))>=prom) if side=='high' else (x<=min(L) and x<min(R) and min(min(L)-x,min(R)-x)>=prom)
        if ok: out.append((i,x,i+r))
    return out

def _compress(points,atr,side,spacing=2):
    out=[]; tol=max(atr*EQ_TOLERANCE_ATR,1e-12)
    for p in points:
        if not out or p[0]-out[-1][0]>=spacing: out.append(p); continue
        q=out[-1]
        if abs(p[1]-q[1])<=tol or (side=='high' and p[1]>q[1]) or (side=='low' and p[1]<q[1]): out[-1]=p
    return out

def _label(hp,lp,atr):
    tol=max(atr*EQ_TOLERANCE_ATR,1e-12); hs=[]; prev=None
    for i,p,ci in hp:
        d=0 if prev is None else p-prev[1]; lab='SWING_HIGH' if prev is None else 'EQH' if abs(d)<=tol else 'HH' if d>0 else 'LH'; hs.append({'index':i,'price':round(p,8),'label':lab,'confirmation_index':ci}); prev=(i,p)
    ls=[]; prev=None
    for i,p,ci in lp:
        d=0 if prev is None else p-prev[1]; lab='SWING_LOW' if prev is None else 'EQL' if abs(d)<=tol else 'HL' if d>0 else 'LL'; ls.append({'index':i,'price':round(p,8),'label':lab,'confirmation_index':ci}); prev=(i,p)
    return hs,ls

def _latest(xs,labels,max_confirm=None):
    for x in reversed(xs):
        if x['label'] in labels and (max_confirm is None or x['confirmation_index']<=max_confirm): return x
    return None

def _count(h,l,n=8):
    z=h[-n:]+l[-n:]; b=sum(x['label'] in {'HH','HL'} for x in z); s=sum(x['label'] in {'LH','LL'} for x in z)
    return UP if b>=s+2 else DOWN if s>=b+2 else NEUTRAL if b==s==0 else MIXED

def _counts(h,l,n=8):
    c={k:0 for k in ('HH','HL','LH','LL','EQH','EQL')}
    for x in h[-n:]+l[-n:]:
        if x['label'] in c:c[x['label']]+=1
    return c

def _classify(h,l):
    if len(h)<2 or len(l)<2:return NEUTRAL
    hu=h[-1]['price']>h[-2]['price']; hd=h[-1]['price']<h[-2]['price']; lu=l[-1]['price']>l[-2]['price']; ld=l[-1]['price']<l[-2]['price']
    return UP if hu and lu else DOWN if hd and ld else MIXED

def _protected(s,h,l):
    return {'protected_low':_latest(l,{'HL'} if s==UP else {'LL','EQL'} if s==DOWN else {'HL','LL','EQL'}),'protected_high':_latest(h,{'HH','EQH'} if s==UP else {'LH','EQH'} if s==DOWN else {'HH','LH','EQH'})}

def _quality(bar,level,d,atr):
    if atr<=0 or level is None:return {'confirmed':False}
    rng=max(bar['high']-bar['low'],1e-12); body=abs(bar['close']-bar['open'])/atr; loc=(bar['close']-bar['low'])/rng; dist=((bar['close']-level) if d==UP else (level-bar['close']))/atr
    return {'confirmed':dist>=BOS_CLOSE_ATR and (body>=BOS_BODY_ATR or (loc>=BOS_CLOSE_LOCATION if d==UP else loc<=1-BOS_CLOSE_LOCATION)),'distance_atr':round(max(0,dist),4),'body_atr':round(body,4),'close_location':round(loc,4),'displacement_ok':body>=BOS_BODY_ATR,'close_beyond_level':dist>=BOS_CLOSE_ATR}

def _event(bar,p,d,atr,event,scope,idx):
    q=_quality(bar,p['price'] if p else None,d,atr)
    if not q['confirmed']:return {'event':'NO_BOS','direction':NEUTRAL,'confirmed':False,'scope':scope}
    return {'event':event,'direction':d,'confirmed':True,'scope':scope,'level':p['price'],'swing_index':p['index'],'swing_label':p['label'],'break_candle_index':idx,**{k:q[k] for k in ('distance_atr','body_atr','close_location','displacement_ok','close_beyond_level')}}

def _current_break(bars,h,l,atr,structure,scope='EXTERNAL',idx=None):
    idx=len(bars)-1 if idx is None else idx
    if idx<=0 or atr<=0:return {'event':'NO_BOS','direction':NEUTRAL,'confirmed':False,'scope':scope}
    out=[]; hi=_latest(h,{'HH','LH','EQH'},idx); lo=_latest(l,{'HL','LL','EQL'},idx)
    if hi and hi['index']<idx and bars[idx-1]['close']<=hi['price']:
        q=_quality(bars[idx],hi['price'],UP,atr)
        if q['confirmed']:out.append((q['distance_atr'],_event(bars[idx],hi,UP,atr,'CONFIRMED_CHOCH' if structure==DOWN else 'CONFIRMED_BOS',scope,idx)))
    if lo and lo['index']<idx and bars[idx-1]['close']>=lo['price']:
        q=_quality(bars[idx],lo['price'],DOWN,atr)
        if q['confirmed']:out.append((q['distance_atr'],_event(bars[idx],lo,DOWN,atr,'CONFIRMED_CHOCH' if structure==UP else 'CONFIRMED_BOS',scope,idx)))
    return max(out,key=lambda x:x[0])[1] if out else {'event':'NO_BOS','direction':NEUTRAL,'confirmed':False,'scope':scope}

def _break_history(bars,h,l,atr,structure):
    events=[]; active=None
    for i in range(1,len(bars)):
        if active:
            active['follow_through_bars']+=1; lv,d=active['level'],active['direction']
            if (d==UP and bars[i]['close']<lv) or (d==DOWN and bars[i]['close']>lv): active['status']='FAILED_BREAK_RECLAIMED'; active['failure_candle_index']=i; events.append(active.copy()); active=None
            elif active['follow_through_bars']>=FOLLOW_THROUGH_BARS: active['status']='ACCEPTED_BREAK_WITH_FOLLOW_THROUGH'; events.append(active.copy()); active=None
        if active is None:
            e=_current_break(bars,h,l,atr,structure,'EXTERNAL',i)
            if e['confirmed']: active={'event':e['event'],'direction':e['direction'],'level':e['level'],'swing_index':e['swing_index'],'break_candle_index':i,'status':'BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH','follow_through_bars':0}
    return events,active

def _failure(bars,active,atr):
    if not active:return {'event':'NO_FAILURE','direction':NEUTRAL,'confirmed':False}
    lv,d=active['level'],active['direction']
    for i in range(active['break_candle_index']+1,len(bars)):
        if (d==UP and bars[i]['close']<lv) or (d==DOWN and bars[i]['close']>lv): return {'event':'FAILED_BOS','direction':DOWN if d==UP else UP,'confirmed':True,'level':lv,'break_candle_index':active['break_candle_index'],'failure_candle_index':i,'scope':'EXTERNAL','reclaim_distance_atr':round(abs(bars[i]['close']-lv)/max(atr,1e-12),4)}
    return {'event':'NO_FAILURE','direction':NEUTRAL,'confirmed':False}

def _lifecycle(bars,current,failure,history,active):
    if failure['confirmed']:return {'stage':'FAILED_BREAK_RECLAIM','active':False,'accepted':False,'follow_through':False,'failure':True,'level':failure['level'],'break_candle_index':failure['break_candle_index'],'failure_candle_index':failure['failure_candle_index']}
    if current['confirmed']:
        i,lv,d=current['break_candle_index'],current['level'],current['direction']; a=bars[i+1:i+1+FOLLOW_THROUGH_BARS]; follow=len(a)>=FOLLOW_THROUGH_BARS and all(x['close']>lv if d==UP else x['close']<lv for x in a)
        return {'stage':'ACCEPTED_BREAK_WITH_FOLLOW_THROUGH' if follow else 'BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH','active':True,'accepted':True,'follow_through':follow,'failure':False,'level':lv,'break_candle_index':i}
    if active:return {'stage':active['status'],'active':True,'accepted':True,'follow_through':False,'failure':False,'level':active['level'],'break_candle_index':active['break_candle_index']}
    if history:
        x=history[-1]; return {'stage':x['status'],'active':False,'accepted':True,'follow_through':x['status']=='ACCEPTED_BREAK_WITH_FOLLOW_THROUGH','failure':False,'level':x['level'],'break_candle_index':x['break_candle_index']}
    return {'stage':'NO_CONFIRMED_BREAK','active':False,'accepted':False,'follow_through':False,'failure':False,'level':None,'break_candle_index':None}

def _invalidation(s,p):
    ph,pl=p.get('protected_high'),p.get('protected_low')
    if s==UP and pl:return {'direction':UP,'level':pl['price'],'type':'CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW','source_label':pl['label'],'source_index':pl['index']}
    if s==DOWN and ph:return {'direction':DOWN,'level':ph['price'],'type':'CLOSED_CANDLE_ACCEPTANCE_ABOVE_PROTECTED_HIGH','source_label':ph['label'],'source_index':ph['index']}
    return {'direction':s,'level':None,'type':'NO_DIRECTIONAL_INVALIDATION_LEVEL','source_label':None,'source_index':None}

def _slope(b,n=20):
    if len(b)<5:return NEUTRAL,0.
    c=[x['close'] for x in b[-n:]]; z=(c[-1]-c[0])/(max(_atr(b),1e-12)*max(1,len(c)-1)); return (UP if z>.035 else DOWN if z<-.035 else NEUTRAL),round(min(1,abs(z)*8),4)

def _authority(ext,inte,ec,ic,bos,fail,p,slope,sq,life):
    score=0.; sup=[]; pen=[]
    if ext in {UP,DOWN}:score+=.35;sup.append(f'EXTERNAL_{ext}')
    else:pen.append('EXTERNAL_STRUCTURE_UNRESOLVED')
    if inte==ext and ext in {UP,DOWN}:score+=.20;sup.append(f'INTERNAL_ALIGNS_{ext}')
    elif inte in {UP,DOWN}:pen.append('INTERNAL_COUNTER_STRUCTURE')
    if ec==ext and ext in {UP,DOWN}:score+=.15;sup.append('EXTERNAL_COUNT_CONFIRMS')
    elif ext in {UP,DOWN}:pen.append('EXTERNAL_COUNT_DIVERGES')
    if p['protected_high'] or p['protected_low']:score+=.10;sup.append('PROTECTED_STRUCTURE_IDENTIFIED')
    else:pen.append('PROTECTED_STRUCTURE_MISSING')
    if bos['confirmed']:score+=.15;sup.append('CURRENT_CLOSED_CANDLE_BREAK')
    if life.get('follow_through'):score+=.05;sup.append('FOLLOW_THROUGH_CONFIRMED')
    if fail['confirmed']:score-=.30;pen.append('BREAK_FAILED_RECLAIMED')
    if slope!=ext and ext in {UP,DOWN}:score-=min(.10,.10*sq);pen.append('SLOPE_CONFLICT')
    score=round(max(0,min(1,score)),4);return {'score':score,'level':'HIGH' if score>=.8 else 'MEDIUM' if score>=.55 else 'LOW','support':sup,'penalties':pen,'explanation':'support='+','.join(sup)+'; penalties='+','.join(pen)}

def _state(ext,inte,bos,fail,life):
    if fail['confirmed']:return 'STRUCTURE_FAILURE'
    if bos['confirmed']:return 'CHANGE_OF_CHARACTER' if bos['event']=='CONFIRMED_CHOCH' else 'BREAKOUT_CONFIRMED'
    if life.get('follow_through'):return 'CONTINUATION'
    if ext in {UP,DOWN} and inte==ext:return 'CONTINUATION'
    if ext in {UP,DOWN} and inte==MIXED:return 'INTERNAL_CONFLICT'
    if ext==MIXED and inte in {UP,DOWN}:return 'INTERNAL_COUNTER_MOVE'
    return 'RANGE_OR_UNCLEAR'

def _empty(status,reasons):
    return {'architecture':ARCHITECTURE,'reasoning_role':'MARKET_STRUCTURE_ANALYST','question':QUESTION,'analysis_status':status,'finding':'INSUFFICIENT_DATA','direction':NEUTRAL,'structure_state':'RANGE_OR_UNCLEAR','internal_structure':{'state':NEUTRAL,'count_state':NEUTRAL},'external_structure':{'state':NEUTRAL,'count_state':NEUTRAL},'internal_count_state':NEUTRAL,'external_count_state':NEUTRAL,'swing_map':{'internal_highs':[],'internal_lows':[],'external_highs':[],'external_lows':[]},'bos':{'event':'NO_BOS','direction':NEUTRAL,'confirmed':False},'failure':{'event':'NO_FAILURE','direction':NEUTRAL,'confirmed':False},'break_lifecycle':{'stage':'NO_CONFIRMED_BREAK','active':False},'protected_structure':{'protected_high':None,'protected_low':None},'structural_invalidation':_invalidation(NEUTRAL,{}),'structure_authority':0.,'authority_detail':{'score':0.,'level':'LOW','support':[],'penalties':[],'explanation':''},'structure_strength':0.,'confidence':0.,'evidence':[],'conflicts':reasons,'reason_codes':reasons,'observations':[f'closed_candles={status}'],'reasoning_trace':{'external_is_authority':True,'closed_candle_only':True,'upstream_inputs_used':False},'upstream_direction_used':False,'upstream_decisions_used':False,'upstream_gates_used':False,'score_used':False,'trade_decision_authority':False,'decision_authority':'E9_ONLY','decision':None,'gate':None,'specialists_active':False,'specialists_status':'PAUSED'}

def analyze_e3(bars):
    b,data=_clean(bars)
    if len(b)<MIN_CANDLES:return _empty('INCOMPLETE',['INSUFFICIENT_CANDLES']+data[:8])
    atr=_atr(b); ih=_compress(_pivots(b,'high',IR),atr,'high'); il=_compress(_pivots(b,'low',IR),atr,'low'); eh=_compress(_pivots(b,'high',ER),atr,'high'); el=_compress(_pivots(b,'low',ER),atr,'low'); ihl,ill=_label(ih,il,atr); ehl,ell=_label(eh,el,atr)
    inte,ext=_classify(ihl,ill),_classify(ehl,ell); ic,ec=_count(ihl,ill),_count(ehl,ell); ics,ecs=_counts(ihl,ill),_counts(ehl,ell); protected=_protected(ext,ehl,ell)
    eb=_current_break(b,ehl,ell,atr,ext,'EXTERNAL'); ib=_current_break(b,ihl,ill,atr,inte,'INTERNAL'); history,active=_break_history(b,ehl,ell,atr,ext); fail=_failure(b,active,atr); life=_lifecycle(b,eb,fail,history,active); slope,sq=_slope(b); state=_state(ext,inte,eb,fail,life); inv=_invalidation(ext,protected); auth=_authority(ext,inte,ec,ic,eb,fail,protected,slope,sq,life)
    reasons=[]
    if ext!=ec:reasons.append('EXTERNAL_COUNT_STATE_DIVERGENCE')
    if inte!=ic:reasons.append('INTERNAL_COUNT_STATE_DIVERGENCE')
    if ext==MIXED:reasons.append('STRUCTURE_UNRESOLVED')
    if slope!=ext and ext in {UP,DOWN}:reasons.append('SLOPE_DISAGREES_WITH_STRUCTURE')
    if ib['confirmed'] and not eb['confirmed']:reasons.append('INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY')
    if not eb['confirmed']:reasons.append('NO_CONFIRMED_EXTERNAL_BOS')
    if life['stage']=='BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH':reasons.append('BREAK_FOLLOW_THROUGH_PENDING')
    if life['stage']=='ACCEPTED_BREAK_WITH_FOLLOW_THROUGH':reasons.append('BREAK_FOLLOW_THROUGH_CONFIRMED')
    if fail['confirmed']:reasons.append('STRUCTURAL_BREAK_FAILED_AND_RECLAIMED')
    reasons=list(dict.fromkeys(reasons+data[:8])); direction=ext if ext in {UP,DOWN} else eb['direction'] if eb['confirmed'] else NEUTRAL
    finding='STRUCTURE_FAILURE='+fail['direction'] if fail['confirmed'] else eb['event'] if eb['confirmed'] else 'BULLISH_STRUCTURE' if ext==UP and inte==UP else 'BEARISH_STRUCTURE' if ext==DOWN and inte==DOWN else 'MIXED_STRUCTURE'
    conf=min(1.,.45+.45*auth['score']+(.10 if eb['confirmed'] else 0)); conf=min(conf,.55) if ext==MIXED else conf; conf=min(conf,.60) if fail['confirmed'] else conf; conf=min(conf,.72) if life['stage']=='BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH' else conf
    conflicts=[]
    if ext!=ec:conflicts.append('EXTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE')
    if inte!=ic:conflicts.append('INTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE')
    if slope!=ext and ext in {UP,DOWN}:conflicts.append('SLOPE_VS_EXTERNAL_STRUCTURE')
    if ext in {UP,DOWN} and inte in {UP,DOWN} and inte!=ext:conflicts.append('INTERNAL_VS_EXTERNAL_STRUCTURE')
    if ib['confirmed'] and not eb['confirmed']:conflicts.append('INTERNAL_BREAK_VS_EXTERNAL_AUTHORITY')
    if fail['confirmed']:conflicts.append('BREAK_FAILED_RECLAIMED')
    ev=[f'external_structure={ext}',f'internal_structure={inte}',f'external_count_state={ec}',f'internal_count_state={ic}',f'external_bos={eb["event"]}',f'internal_bos={ib["event"]}',f'break_lifecycle={life["stage"]}',f'protected_high={protected["protected_high"]["price"] if protected["protected_high"] else None}',f'protected_low={protected["protected_low"]["price"] if protected["protected_low"] else None}',f'invalidation={inv["type"]}@{inv["level"]}',f'slope_context={slope}',f'slope_quality={sq}',f'structure_authority={auth["score"]}']
    trace={'external_state':ext,'internal_state':inte,'external_count_state':ec,'internal_count_state':ic,'slope_context':slope,'slope_is_structural_authority':False,'external_bos_confirmed':eb['confirmed'],'internal_bos_confirmed':ib['confirmed'],'external_is_authority':True,'closed_candle_only':True,'protected_structure_is_invalidation_anchor':True,'break_lifecycle_stage':life['stage'],'authority_explanation':auth['explanation'],'upstream_inputs_used':False}
    return {'architecture':ARCHITECTURE,'reasoning_role':'MARKET_STRUCTURE_ANALYST','question':QUESTION,'analysis_status':'COMPLETE','finding':finding,'direction':direction,'structure_state':state,'internal_structure':{'state':inte,'count_state':ic,'counts':ics},'external_structure':{'state':ext,'count_state':ec,'counts':ecs},'internal_count_state':ic,'external_count_state':ec,'internal_counts':ics,'external_counts':ecs,'internal_sequence':'→'.join(x['label'] for x in sorted(ihl+ill,key=lambda x:x['index'])[-12:]),'external_sequence':'→'.join(x['label'] for x in sorted(ehl+ell,key=lambda x:x['index'])[-12:]),'swing_map':{'internal_highs':ihl,'internal_lows':ill,'external_highs':ehl,'external_lows':ell},'atr14':round(atr,8),'closed_candles':len(b),'bos':eb,'external_bos':eb['event'],'internal_bos':ib['event'],'external_bos_detail':eb,'internal_bos_detail':ib,'failure':fail,'break_lifecycle':life,'break_history':history[-5:],'protected_structure':protected,'protected_high':protected['protected_high']['price'] if protected['protected_high'] else None,'protected_low':protected['protected_low']['price'] if protected['protected_low'] else None,'structural_invalidation':inv,'structure_strength':auth['score'],'structure_authority':auth['score'],'authority_detail':auth,'confidence':round(conf,4),'evidence':ev,'conflicts':conflicts,'reason_codes':reasons,'observations':[f'closed_candles={len(b)}',f'atr14={round(atr,8)}']+ev,'reasoning_trace':trace,'slope_context':slope,'slope_quality':sq,'upstream_direction_used':False,'upstream_decisions_used':False,'upstream_gates_used':False,'score_used':False,'trade_decision_authority':False,'decision_authority':'E9_ONLY','decision':None,'gate':None,'specialists_active':False,'specialists_status':'PAUSED','specialists':{}}

__all__=['analyze_e3','_compress','_current_break','_break_history','_failure']

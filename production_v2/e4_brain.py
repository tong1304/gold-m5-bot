from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION="Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE="LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE="E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V24"
MIN_BARS=30; PIVOT_WING=2; LOOKBACK=80; EVENT_LOOKBACK=8; MAX_EVENT_AGE=8; MAX_CONFIRM_BARS=5
ZONE_ATR=.15; INTERACTION_ATR=.05; REJECTION_ATR=.10; ACCEPTANCE_ATR=.15; BODY=.55; WICK=.30; CONFIRM_BARS=2

def _num(v:Any):
    try:x=float(v)
    except (TypeError,ValueError):return None
    return x if isfinite(x) else None

def _bars(src):
    raw=src.get('bars') if isinstance(src,dict) else src;out=[]
    for b in raw if isinstance(raw,(list,tuple)) else []:
        if not isinstance(b,dict) or b.get('closed') is False or b.get('is_closed') is False:continue
        v={k:_num(b.get(k)) for k in ('open','high','low','close')}
        if any(x is None for x in v.values()):continue
        if v['high']<max(v['open'],v['close']) or v['low']>min(v['open'],v['close']) or v['high']<v['low']:continue
        out.append({**b,**v})
    return out

def _atr(bars,p=14):
    if len(bars)<2:return 0.0
    tr=[]
    for i in range(1,len(bars)):
        h,l,pc=bars[i]['high'],bars[i]['low'],bars[i-1]['close'];tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return mean(tr[-p:]) if tr else 0.0

def _pivots(bars):
    hi=[];lo=[]
    for i in range(PIVOT_WING,len(bars)-PIVOT_WING):
        w=bars[i-PIVOT_WING:i+PIVOT_WING+1]
        if bars[i]['high']>=max(x['high'] for x in w):hi.append((i,bars[i]['high']))
        if bars[i]['low']<=min(x['low'] for x in w):lo.append((i,bars[i]['low']))
    return hi[-LOOKBACK:],lo[-LOOKBACK:]

def _zones(levels,side,atr,current):
    tol=max(atr*ZONE_ATR,1e-9);groups=[]
    for item in sorted(levels,key=lambda x:x[1]):
        if not groups or abs(item[1]-mean(p for _,p in groups[-1]))>tol:groups.append([item])
        else:groups[-1].append(item)
    out=[]
    for g in groups:
        prices=[p for _,p in g];idx=[i for i,_ in g];last=max(idx);touches=len(idx);age=current-last
        out.append({'side':side,'price':mean(prices),'lower':min(prices),'upper':max(prices),'touches':touches,'separated_touches':sum(1 for a,b in zip(idx,idx[1:]) if b-a>=3),'last_touch_index':last,'age_bars':age,'freshness':'FRESH' if age<=24 else 'AGED','kind':'CLUSTER_LIQUIDITY' if touches>=3 else 'EQUAL_LIQUIDITY' if touches>=2 else 'SWING_LIQUIDITY'})
    return out

def _geom(b):
    span=max(b['high']-b['low'],1e-12)
    return {'body_ratio':abs(b['close']-b['open'])/span,'upper_wick_ratio':(b['high']-max(b['open'],b['close']))/span,'lower_wick_ratio':(min(b['open'],b['close'])-b['low'])/span,'range':span}

def _event(bars,z,atr,i):
    if i<=z['last_touch_index']:return None
    b,prev=bars[i],bars[i-1];level=z['upper'] if z['side']=='HIGH' else z['lower'];g=_geom(b);s=atr*INTERACTION_ATR;r=atr*REJECTION_ATR;a=atr*ACCEPTANCE_ATR
    if z['side']=='HIGH':
        swept=b['high']>level+s;reject=swept and b['close']<=level+r and g['upper_wick_ratio']>=WICK;failed=prev['close']>level+a and b['close']<=level+r;accept=prev['close']<=level+r and b['close']>level+a and g['body_ratio']>=BODY
        if failed:typ,state,d='HIGH_FAILED_BREAK_RECLAIM','FAILED_BREAK_RECLAIM','DOWN'
        elif reject:typ,state,d='HIGH_SWEEP_REJECTION','REJECTION','DOWN'
        elif accept:typ,state,d='HIGH_ACCEPTANCE_CANDIDATE','ACCEPTANCE','UP'
        elif swept:typ,state,d='HIGH_LIQUIDITY_INTERACTION','INTERACTION','NEUTRAL'
        else:return None
        taker='BUY_SIDE_PRESSURE_INFERENCE';response='SELL_SIDE_RESPONSE_INFERENCE' if d=='DOWN' else 'BUY_SIDE_CONTINUATION_INFERENCE' if d=='UP' else 'UNRESOLVED_PRICE_RESPONSE'
    else:
        swept=b['low']<level-s;reject=swept and b['close']>=level-r and g['lower_wick_ratio']>=WICK;failed=prev['close']<level-a and b['close']>=level-r;accept=prev['close']>=level-r and b['close']<level-a and g['body_ratio']>=BODY
        if failed:typ,state,d='LOW_FAILED_BREAK_RECLAIM','FAILED_BREAK_RECLAIM','UP'
        elif reject:typ,state,d='LOW_SWEEP_REJECTION','REJECTION','UP'
        elif accept:typ,state,d='LOW_ACCEPTANCE_CANDIDATE','ACCEPTANCE','DOWN'
        elif swept:typ,state,d='LOW_LIQUIDITY_INTERACTION','INTERACTION','NEUTRAL'
        else:return None
        taker='SELL_SIDE_PRESSURE_INFERENCE';response='BUY_SIDE_RESPONSE_INFERENCE' if d=='UP' else 'SELL_SIDE_CONTINUATION_INFERENCE' if d=='DOWN' else 'UNRESOLVED_PRICE_RESPONSE'
    return {'type':typ,'auction_state':state,'directional_implication':d,'liquidity_state':'REJECTED' if state=='REJECTION' else 'RECLAIMED' if state=='FAILED_BREAK_RECLAIM' else 'ACCEPTANCE_CANDIDATE' if state=='ACCEPTANCE' else 'TAKEN','liquidity_taker':taker,'response_actor':response,'actor_evidence_type':'PRICE_ACTION_INFERENCE_ONLY','actor_identification_limit':'OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW','strength':.95 if state=='REJECTION' else .94 if state=='FAILED_BREAK_RECLAIM' else .88 if state=='ACCEPTANCE' else .55,'zone':z,'index':i,'age_bars':len(bars)-1-i,'level':level,'event_candle':{k:b[k] for k in ('open','high','low','close')},'candle_geometry':g}

def _latest_event(bars,zones,atr):
    cur=len(bars)-1;events=[]
    for i in range(max(1,cur-EVENT_LOOKBACK),cur+1):
        for z in zones:
            e=_event(bars,z,atr,i)
            if e and e['age_bars']<=MAX_EVENT_AGE:events.append(e)
    if not events:return {'type':'NO_LIQUIDITY_EVENT','auction_state':'UNRESOLVED','directional_implication':'NEUTRAL','liquidity_state':'UNRESOLVED','liquidity_taker':'NONE','response_actor':'NONE','actor_evidence_type':'NONE','strength':.30,'zone':None,'index':cur,'age_bars':0}
    return max(events,key=lambda e:(e['index'],e['strength'],e['zone']['touches']))

def _follow(event,bars,atr):
    i=event['index'];z=event.get('zone')
    if not z or i>=len(bars)-1:return {'present':False,'bars':0,'available_bars':0,'required_bars':CONFIRM_BARS,'horizon_bars':0,'invalidated':False,'expired':False,'reason':'NO_POST_EVENT_CANDLE','checks':[],'decisive_single':False}
    g=event.get('candle_geometry',{});h=min(MAX_CONFIRM_BARS,2 if g.get('body_ratio',0)>=.8 else 3 if g.get('body_ratio',0)>=.65 else 4 if g.get('body_ratio',0)>=.25 else 5);level=event['level'];d=event['directional_implication'];checks=[];support=0;invalidated=False
    for j in range(i+1,min(len(bars),i+h+1)):
        b=bars[j];geo=_geom(b);hold=b['close']>level+atr*INTERACTION_ATR if d=='UP' else b['close']<level-atr*INTERACTION_ATR if d=='DOWN' else False;disp=(b['close']-level)/max(atr,1e-9) if d=='UP' else (level-b['close'])/max(atr,1e-9) if d=='DOWN' else 0;opp=b['close']<level-atr*INTERACTION_ATR if d=='UP' else b['close']>level+atr*INTERACTION_ATR if d=='DOWN' else False;meaningful=hold and disp>=.20 and geo['body_ratio']>=.45;support+=int(meaningful and not opp);invalidated|=opp;checks.append({'index':j,'close':b['close'],'hold':hold,'displacement_atr':disp,'body_ratio':geo['body_ratio'],'meaningful':meaningful,'opposite_reclaim':opp})
    available=len(checks);present=not invalidated and support>=CONFIRM_BARS;expired=not present and not invalidated and available>=h
    return {'present':present,'bars':support,'available_bars':available,'required_bars':CONFIRM_BARS,'horizon_bars':h,'invalidated':invalidated,'expired':expired,'reason':'FOLLOW_THROUGH_CONFIRMED' if present else 'POST_EVENT_RECLAMATION' if invalidated else 'EVENT_EXPIRED' if expired else 'FOLLOW_THROUGH_ABSENT','checks':checks,'decisive_single':False}

def _auction(event,bars,atr):
    if not event.get('zone'):return {'state':'UNRESOLVED','confirmed':False,'follow_through_bars':0,'lifecycle':'NO_EVENT','detail':{}}
    f=_follow(event,bars,atr);base=event['auction_state']
    if f['invalidated']:state='INVALIDATED';confirmed=False;life='INVALIDATED'
    elif f['expired']:state='EXPIRED';confirmed=False;life='EXPIRED'
    elif f['present'] and base in {'REJECTION','ACCEPTANCE','FAILED_BREAK_RECLAIM'}:state='ACCEPTANCE_CONFIRMED' if base=='ACCEPTANCE' else 'REJECTION_CONFIRMED';confirmed=True;life='CONFIRMED'
    else:state={'REJECTION':'REJECTION_PENDING','ACCEPTANCE':'ACCEPTANCE_PENDING','FAILED_BREAK_RECLAIM':'REJECTION_PENDING'}.get(base,'INTERACTION_PENDING');confirmed=False;life='PENDING'
    return {'state':state,'confirmed':confirmed,'follow_through_bars':f['bars'],'lifecycle':life,'detail':f}

def _context_hint(bus):
    votes=[]
    for eid in ('E1','E2','E3'):
        p=(bus or {}).get(eid,{})
        o=getattr(p,'output',None)
        if o is None:
            if isinstance(p,dict):o=p.get('output',p.get('evidence',p))
            else:o=p
        text=str(o).upper()
        if any(x in text for x in ('DIRECTION=UP','TREND_STATE=UP','PRESSURE=BULLISH','DIRECTION: UP')):votes.append('UP')
        if any(x in text for x in ('DIRECTION=DOWN','TREND_STATE=DOWN','PRESSURE=BEARISH','DIRECTION: DOWN')):votes.append('DOWN')
    return 'UP' if votes.count('UP')>votes.count('DOWN') else 'DOWN' if votes.count('DOWN')>votes.count('UP') else 'NEUTRAL'

def _reasoning(event,auction,counter,invalidation):
    s=event.get('auction_state','UNRESOLVED');d=auction.get('detail') or {}
    return {'liquidity_event':{'type':event.get('type','NONE'),'state':s,'level':event.get('level'),'side':(event.get('zone') or {}).get('side','NONE'),'kind':(event.get('zone') or {}).get('kind','NONE'),'age_bars':event.get('age_bars',0)},'take':{'status':'TAKEN' if event.get('zone') else 'NONE','taker':event.get('liquidity_taker','NONE'),'evidence':event.get('actor_evidence_type','NONE')},'response':{'status':'CONFIRMED' if auction.get('confirmed') else 'PENDING','direction':event.get('directional_implication','NEUTRAL'),'actor':event.get('response_actor','NONE')},'acceptance':{'candidate':s=='ACCEPTANCE','confirmed':auction.get('state')=='ACCEPTANCE_CONFIRMED'},'rejection':{'candidate':s in {'REJECTION','FAILED_BREAK_RECLAIM'},'confirmed':auction.get('state')=='REJECTION_CONFIRMED'},'follow_through':{'confirmed':d.get('present',False),'bars':d.get('bars',0),'required_bars':d.get('required_bars',CONFIRM_BARS),'reason':d.get('reason','NO_EVENT')},'thesis_status':'CONFIRMED' if auction.get('confirmed') else 'INVALIDATED' if auction.get('state')=='INVALIDATED' else 'EXPIRED' if auction.get('state')=='EXPIRED' else 'UNRESOLVED','actor_identification':'OHLC_INFERENCE_ONLY','counter_evidence':counter,'invalidation':invalidation}

def analyze_e4(snapshot=None,evidence_bus=None):
    bars=_bars(snapshot);atr=_atr(bars);base={'architecture':ARCHITECTURE,'professional_brain':True,'role':E4_ROLE,'question':PROFESSIONAL_QUESTION,'specialists_active':False,'specialists_status':'PAUSED','decision':None,'gate':None,'score':None,'trade_decision_authority':False,'decision_authority':'E9_ONLY','reasoning_role':E4_ROLE,'upstream_decisions_used':False,'upstream_gates_used':False,'scores_used':False,'score_used':False,'evidence':{'raw_market_data_used':True,'decisions_used':False,'gates_used':False,'scores_used':False}}
    if len(bars)<MIN_BARS or atr<=0:
        e={'type':'LIQUIDITY_DATA_INSUFFICIENT','auction_state':'UNRESOLVED','directional_implication':'NEUTRAL','liquidity_taker':'NONE','actor_evidence_type':'NONE'};a={'state':'UNRESOLVED','confirmed':False,'detail':{}};c=['INSUFFICIENT_DATA'];inv=['new closed-candle data']
        return {**base,'state':'UNAVAILABLE','analysis_status':'INCOMPLETE','finding':'LIQUIDITY_DATA_INSUFFICIENT','analyst_conclusion':'LIQUIDITY_DATA_INSUFFICIENT','direction':'NEUTRAL','directional_implication':'NEUTRAL','direction_confirmed':False,'confidence':0.0,'observations':[f'closed_candles={len(bars)}',f'atr14={atr:.6f}'],'liquidity_map':{},'event':e,'auction':a,'auction_state':'UNRESOLVED','follow_through':{'present':False},'follow_through_bars':0,'auction_confirmation':{'confirmed':False},'auction_confirmation_state':'UNRESOLVED','auction_quality':'UNRESOLVED','counter_evidence':c,'invalidation':inv,'reasons':['INSUFFICIENT_CLOSED_CANDLE_DATA'],'independent_thesis':'LIQUIDITY_DATA_INSUFFICIENT -> NO_DIRECTIONAL_THESIS','professional_reasoning':_reasoning(e,a,c,inv),'audit':{'closed_candle_only':True,'no_lookahead':True,'actor_identification':'PRICE_ACTION_INFERENCE_ONLY'}}
    hi,lo=_pivots(bars);cur=len(bars)-1;highs=_zones(hi,'HIGH',atr,cur);lows=_zones(lo,'LOW',atr,cur);event=_latest_event(bars,highs+lows,atr);auction=_auction(event,bars,atr);confirmed=auction['confirmed'];direction=event['directional_implication'] if confirmed else 'NEUTRAL';detail=auction.get('detail') or {}
    if auction['state']=='INVALIDATED':counter=['POST_EVENT_RECLAMATION','ORIGINAL_AUCTION_THESIS_REJECTED']
    elif auction['state']=='EXPIRED':counter=['NO_SUFFICIENT_FOLLOW_THROUGH','THESIS_EXPIRED']
    elif not event.get('zone'):counter=['NO_LIQUIDITY_EVENT']
    elif not confirmed:counter=['NO_FOLLOW_THROUGH','AUCTION_DIRECTION_REMAINS_UNRESOLVED']
    else:counter=['OPPOSITE_LIQUIDITY_EVENT_CHALLENGES_THESIS']
    finding=(event['type']+'_CONFIRMED' if confirmed else event['type']) if event.get('zone') else 'NO_LIQUIDITY_EVENT';quality='CONFIRMED' if confirmed else 'INVALIDATED' if auction['state']=='INVALIDATED' else 'EXPIRED' if auction['state']=='EXPIRED' else 'PENDING';inv=['newer confirmed liquidity event supersedes current event','post-event close through defended liquidity level invalidates thesis','event expiry without sufficient follow-through invalidates confirmation'];thesis=f"LIQUIDITY={event.get('type','NONE')}; TAKE={event.get('liquidity_state','UNRESOLVED')}; RESPONSE={event.get('response_actor','NONE')}; AUCTION={auction['state']}; DIRECTION={direction}; CONFIRMED={confirmed}";reasoning=_reasoning(event,auction,counter,inv);reasoning.update({'independent_thesis':thesis,'conclusion':finding,'direction':direction})
    obs=[f'closed_candles={len(bars)}',f'atr14={atr:.6f}',f'liquidity_map_high_zones={len(highs)}',f'liquidity_map_low_zones={len(lows)}',f"liquidity_side={(event.get('zone') or {}).get('side','NONE')}",f"liquidity_kind={(event.get('zone') or {}).get('kind','NONE')}",f"touches={(event.get('zone') or {}).get('touches',0)}",f"separated_touches={(event.get('zone') or {}).get('separated_touches',0)}",f"freshness={(event.get('zone') or {}).get('freshness','NONE')}",f"event={event.get('type','NONE')}",f"event_age_bars={event.get('age_bars',0)}",f"actor_identification={event.get('actor_evidence_type','NONE')}",f"actor_limit={event.get('actor_identification_limit','NONE')}",f"auction_state={auction['state']}",f"lifecycle={auction['lifecycle']}",f"follow_through_bars={auction['follow_through_bars']}",f"consecutive_confirmation_bars={detail.get('bars',0)}",f"required_confirmation_bars={detail.get('required_bars',CONFIRM_BARS)}",f"confirmation_horizon={detail.get('horizon_bars',0)}",'direction_authority=E4_AUCTION_EVIDENCE_ONLY','upstream_direction_used_as_context_only=True','confirmation_requires_consecutive_closed_candles=True','newer_causal_event_supersedes_older_event=True']
    return {**base,'state':'ANALYSIS_COMPLETE','analysis_status':'COMPLETE','finding':finding,'analyst_conclusion':finding,'direction':direction,'directional_implication':direction,'direction_confirmed':confirmed,'confidence':round(event.get('strength',.30) if confirmed else min(event.get('strength',.30),.45),3),'evidence_strength':round(event.get('strength',.30),3),'observations':obs,'liquidity_map':{'high_zones':highs,'low_zones':lows},'event':event,'auction':auction,'auction_state':auction['state'],'follow_through':detail,'follow_through_bars':auction['follow_through_bars'],'auction_confirmation':{'confirmed':confirmed,'state':auction['state']},'auction_confirmation_state':auction['state'],'auction_quality':quality,'counter_evidence':counter,'invalidation':inv,'reasons':[] if confirmed else ['TRUE_AUCTION_CONFIRMATION_NOT_PROVEN'],'independent_thesis':thesis,'professional_reasoning':reasoning,'audit':{'closed_candle_only':True,'no_lookahead':True,'actor_identification':'PRICE_ACTION_INFERENCE_ONLY','actor_identification_limit':'OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW','liquidity_map_high_zones':len(highs),'liquidity_map_low_zones':len(lows),'auction_state':auction['state'],'follow_through_bars':auction['follow_through_bars'],'required_confirmation_bars':detail.get('required_bars',CONFIRM_BARS),'confirmation_horizon':detail.get('horizon_bars',0)}}

__all__=['analyze_e4']

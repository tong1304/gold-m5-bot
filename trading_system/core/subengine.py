from __future__ import annotations
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

@dataclass(frozen=True)
class SubEngineResult:
    sub_engine_id: str
    output: dict[str, Any]
    gate_passed: bool
    score: float
    trace: dict[str, Any] = field(default_factory=dict)

class SubEngine:
    """Professional M5 specialist brain. E1-E8 analyse; E9 decides."""
    def __init__(self, sub_engine_id: str | None = None):
        self.sub_engine_id = sub_engine_id or self._derive_id()

    def _derive_id(self):
        p=self.__class__.__module__.split('.')
        e=next((x[1:] for x in p if x.startswith('e') and x[1:].isdigit()),'')
        return f"{e}{p[-1].split('_',1)[0].upper()}"

    @staticmethod
    def _bars(d):
        return [b for b in (d.get('bars') or []) if isinstance(b,dict) and all(k in b for k in ('open','high','low','close'))]

    @staticmethod
    def _ema(xs,n):
        if not xs:return 0.0
        a=2/(n+1); x=xs[0]
        for y in xs[1:]: x=a*y+(1-a)*x
        return x

    @staticmethod
    def _atr(bs,n=14):
        tr=[]; prev=None
        for b in bs[-n:]:
            h,l,c=map(float,(b['high'],b['low'],b['close']))
            tr.append(h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev))); prev=c
        return mean(tr) if tr else 0.0

    @staticmethod
    def _pivots(bs):
        hi=[];lo=[]
        for i in range(2,max(2,len(bs)-2)):
            w=bs[i-2:i+3]; h=float(bs[i]['high']); l=float(bs[i]['low'])
            if h>=max(float(x['high']) for x in w):hi.append(h)
            if l<=min(float(x['low']) for x in w):lo.append(l)
        return hi[-6:],lo[-6:]

    @staticmethod
    def _ctx(d,e):
        x=d.get(f'{e}_result') or {}
        return x if isinstance(x,dict) else {}

    def _analyse(self,d):
        bs=self._bars(d)
        if len(bs)<30:
            return {'state':'UNAVAILABLE','thesis':'INSUFFICIENT_DATA','observations':[],'evidence':[],'counter_evidence':['less than 30 valid candles'],'confidence':0.0,'missing_evidence':['valid OHLC history']},0.0,['INSUFFICIENT_MARKET_DATA']
        o=[float(b['open']) for b in bs];h=[float(b['high']) for b in bs];l=[float(b['low']) for b in bs];c=[float(b['close']) for b in bs]
        v=[float(b.get('volume',0) or 0) for b in bs]; last,prev=c[-1],c[-2]; atr=self._atr(bs)
        e20,e50=self._ema(c,20),self._ema(c,50); slope=c[-1]-c[-6]; ts=abs(slope)/max(atr,1e-12)
        direction='UP' if e20>e50 and slope>0 and last>=e20 else 'DOWN' if e20<e50 and slope<0 and last<=e20 else 'NEUTRAL'
        cr=max(h[-1]-l[-1],1e-12); body=abs(c[-1]-o[-1]); br=body/cr; cp=(last-l[-1])/cr
        avg=mean([h[i]-l[i] for i in range(max(0,len(bs)-20),len(bs))]); short=mean([h[i]-l[i] for i in range(-6,0)])
        comp=short<.70*max(avg,1e-12); expansion=cr>=1.35*max(avg,1e-12) or (br>=.65 and body>=.8*max(atr,1e-12))
        hi20,lo20=max(h[-20:-1]),min(l[-20:-1]); sweep_hi=h[-1]>hi20 and last<hi20; sweep_lo=l[-1]<lo20 and last>lo20
        ph,pl=self._pivots(bs); hh=len(ph)>1 and ph[-1]>ph[-2];lh=len(ph)>1 and ph[-1]<ph[-2];hl=len(pl)>1 and pl[-1]>pl[-2];ll=len(pl)>1 and pl[-1]<pl[-2]
        structure='BULLISH' if hh and hl else 'BEARISH' if lh and ll else ('BULLISH' if direction=='UP' else 'BEARISH' if direction=='DOWN' else 'NEUTRAL')
        pos=(last-min(l[-40:]))/max(max(h[-40:])-min(l[-40:]),1e-12);pos=max(0,min(1,pos))
        rejection=(sweep_hi and cp<.45) or (sweep_lo and cp>.55); acceptance=(last>hi20 and cp>.70) or (last<lo20 and cp<.30)
        failure=(direction=='UP' and last<prev-.35*atr) or (direction=='DOWN' and last>prev+.35*atr)
        sid=self.sub_engine_id; ev=[]; counter=[]; missing=[]; state='UNRESOLVED'; thesis='UNRESOLVED'; conf=.5

        if sid=='1A': state='DATA_READY';thesis='Closed-candle market data is usable.';ev=[f'valid_bars={len(bs)}','symbol_present','timeframe_present'];conf=1
        elif sid=='1B': state='EXPANSION' if expansion else 'COMPRESSION' if comp else 'NORMAL_VOLATILITY';thesis=f'Volatility state is {state}.';ev=[f'ATR={atr:.8f}',f'range_ratio={short/max(avg,1e-12):.3f}',f'expansion={expansion}',f'compression={comp}'];conf=.9 if state!='NORMAL_VOLATILITY' else .7
        elif sid=='1C': state='TREND_UP' if direction=='UP' else 'TREND_DOWN' if direction=='DOWN' else 'NO_CLEAR_TREND';thesis=f'Directional state={state}.';ev=[f'EMA20={e20:.8f}',f'EMA50={e50:.8f}',f'slope_ATR={ts:.3f}'];conf=min(1,.5+.35*min(ts,1)+.15*(direction!='NEUTRAL'))
        elif sid=='1D': state='RANGE' if short/max(avg,1e-12)<.45 and ts<.6 else 'DIRECTIONAL';thesis=f'Market structure is {state.lower()}.';ev=[f'10/40_range_ratio={(max(h[-10:])-min(l[-10:]))/max(max(h[-40:])-min(l[-40:]),1e-12):.3f}',f'trend_strength={ts:.3f}'];conf=.86
        elif sid=='1E': state='COMPRESSION' if comp else 'NO_COMPRESSION';thesis=f'Compression={comp}.';ev=[f'short_range={short:.8f}',f'avg_range={avg:.8f}'];conf=.9 if comp else .7
        elif sid=='1F': state='EXPANSION' if expansion else 'NO_EXPANSION';thesis=f'Expansion={expansion}.';ev=[f'body_ratio={br:.3f}',f'candle_vs_avg={cr/max(avg,1e-12):.3f}'];conf=.92 if expansion else .68
        elif sid=='1G': state='TRANSITION' if direction=='NEUTRAL' or ((sweep_hi or sweep_lo) and failure) else 'STABLE';thesis=f'Market state is {state.lower()}.';ev=[f'direction={direction}',f'structure={structure}',f'sweep_hi={sweep_hi}',f'sweep_lo={sweep_lo}'];conf=.82 if state=='TRANSITION' else .78
        elif sid.startswith('2'):
            trend=direction!='NEUTRAL' and ts>=.45 and structure==('BULLISH' if direction=='UP' else 'BEARISH'); rng=short/max(avg,1e-12)<.45 and not expansion; brk=expansion and (last>hi20 or last<lo20); mr=pos<.2 or pos>.8
            regime='TREND' if trend else 'RANGE' if rng else 'BREAKOUT' if brk else 'MEAN_REVERSION' if mr else 'TRANSITION'
            state={'2A':'TREND' if trend else 'NOT_TREND','2B':'RANGE' if rng else 'NOT_RANGE','2C':'MEAN_REVERSION' if mr else 'NOT_MEAN_REVERSION','2D':'BREAKOUT' if brk else 'NOT_BREAKOUT','2E':'EXPANSION_PHASE' if expansion else 'BALANCED_PHASE','2F':regime}[sid];thesis=f'Best-fit opportunity regime={regime}.';ev=[f'regime={regime}',f'direction={direction}',f'trend_strength={ts:.3f}',f'position={pos:.3f}'];conf=.88 if regime!='TRANSITION' else .55
        elif sid.startswith('3'):
            bos='BULLISH_BOS' if ph and last>ph[-1] else 'BEARISH_BOS' if pl and last<pl[-1] else 'NO_BOS'; strength=min(1,.4+.2*float(hh or hl)+.2*float(lh or ll)+.2*min(ts,1)); state={'3A':'SWINGS_IDENTIFIED','3B':structure,'3C':bos,'3D':'FAILURE' if failure else 'NO_FAILURE','3E':'STRONG' if strength>=.75 else 'MODERATE' if strength>=.55 else 'WEAK','3F':'ALIGNED' if direction!='NEUTRAL' and structure==('BULLISH' if direction=='UP' else 'BEARISH') else 'MIXED'}[sid];thesis=f'Structure={structure}; strength={strength:.2f}.';ev=[f'HH={hh}',f'HL={hl}',f'LH={lh}',f'LL={ll}',f'BOS={bos}'];conf=strength
        elif sid.startswith('4'):
            reclaim=(sweep_hi and last>hi20) or (sweep_lo and last<lo20);state={'4A':'POOLS_IDENTIFIED','4B':'SWEEP_HIGH' if sweep_hi else 'SWEEP_LOW' if sweep_lo else 'NO_SWEEP','4C':'REJECTION' if rejection else 'NO_REJECTION','4D':'ACCEPTANCE' if acceptance else 'NO_ACCEPTANCE','4E':'RECLAIM' if reclaim else 'FAILED_BREAK' if (sweep_hi or sweep_lo) else 'NO_RECLAIM','4F':'HIGH_QUALITY' if (sweep_hi or sweep_lo) and rejection and expansion else 'QUALITY_NOT_PROVEN'}[sid];thesis=f'Liquidity state={state}.';ev=[f'equal_high={len(ph)>1 and abs(ph[-1]-ph[-2])<=.15*atr}',f'equal_low={len(pl)>1 and abs(pl[-1]-pl[-2])<=.15*atr}',f'sweep_hi={sweep_hi}',f'sweep_lo={sweep_lo}',f'rejection={rejection}',f'acceptance={acceptance}'];conf=.94 if state=='HIGH_QUALITY' else .82 if state in ('REJECTION','RECLAIM','ACCEPTANCE') else .52
        elif sid.startswith('5'):
            loc='PREMIUM' if pos>.6 else 'DISCOUNT' if pos<.4 else 'EQUILIBRIUM'; ext=(direction=='UP' and pos>.85) or (direction=='DOWN' and pos<.15); room=not((direction=='UP' and pos>.8) or (direction=='DOWN' and pos<.2));state={'5A':loc,'5B':'STRUCTURAL_DISCOUNT' if direction=='UP' and pos<.5 else 'STRUCTURAL_PREMIUM' if direction=='DOWN' and pos>.5 else 'NEUTRAL','5C':'LIQUIDITY_ABOVE' if direction=='UP' else 'LIQUIDITY_BELOW' if direction=='DOWN' else 'LIQUIDITY_BOTH','5D':'EXTENDED' if ext else 'NOT_EXTENDED','5E':'SPACE_AVAILABLE' if room else 'LIMITED_SPACE','5F':'LOCATION_QUALITY_PASS' if room and not ext else 'LOCATION_QUALITY_FAIL'}[sid];thesis='Location offers usable space.' if room and not ext else 'Location is disadvantaged.';ev=[f'position={pos:.3f}',f'location={loc}',f'extended={ext}',f'room={room}'];conf=.9 if state=='LOCATION_QUALITY_PASS' else .58
        elif sid.startswith('6'):
            ctx=' '.join(str(self._ctx(d,e)).upper() for e in ('E1','E2','E3','E4','E5'));trend_hint=direction!='NEUTRAL' or 'TREND' in ctx;sweep_hint=sweep_hi or sweep_lo or 'SWEEP_' in ctx;reject_hint=rejection or 'REJECTION' in ctx
            archetype='LIQUIDITY_REVERSAL' if sweep_hint and reject_hint else 'BREAKOUT_RETEST' if expansion and acceptance else 'TREND_PULLBACK' if trend_hint else 'RANGE_REJECTION' if pos<.2 or pos>.8 else 'NO_VALID_SETUP';formed=archetype!='NO_VALID_SETUP';mature=formed and (expansion or rejection or acceptance)
            state={'6A':'CONTEXT_ALIGNED' if formed else 'CONTEXT_UNCLEAR','6B':archetype,'6C':'SETUP_FORMING' if formed else 'NO_SETUP','6D':'INVALIDATED' if failure else 'NOT_INVALIDATED','6E':'QUALITY_PASS' if mature and not failure else 'QUALITY_WEAK','6F':'MATURE' if mature and not failure else 'DEVELOPING' if formed else 'ABSENT'}[sid];thesis=f'{archetype} is {"mature" if mature else "developing"}.' if formed else 'No valid setup thesis.';ev=[f'archetype={archetype}',f'formed={formed}',f'expansion={expansion}',f'rejection={rejection}',f'acceptance={acceptance}',f'failure={failure}'];missing=['trigger/follow-through'] if formed and not mature else [];conf=.88 if mature and not failure else .62 if formed else .35
        elif sid.startswith('7'):
            ctx=' '.join(str(self._ctx(d,e)).upper() for e in ('E3','E4','E5','E6'));trigger=(expansion and direction!='NEUTRAL') or (sweep_lo and direction=='UP') or (sweep_hi and direction=='DOWN') or (expansion and acceptance);follow=trigger and abs(last-prev)>=.35*max(atr,1e-12);quality=trigger and br>=.60 and (cp>.65 if direction=='UP' else cp<.35 if direction=='DOWN' else True);confirmed=trigger and quality and follow and not failure
            state={'7A':'TRIGGER_OBSERVED' if trigger else 'NO_TRIGGER','7B':'QUALITY_PASS' if quality else 'QUALITY_WEAK','7C':'FOLLOW_THROUGH_OBSERVED' if follow else 'NO_FOLLOW_THROUGH','7D':'FAILURE' if failure else 'NO_FAILURE','7E':'EXECUTION_CONDITIONS_PASS' if confirmed else 'WAIT','7F':'CONFIRMATION_PASS' if confirmed else 'CONFIRMATION_WAIT'}[sid];thesis='Setup thesis is confirmed.' if confirmed else 'Confirmation is incomplete.';ev=[f'trigger={trigger}',f'quality={quality}',f'follow_through={follow}',f'failure={failure}',f'upstream_context={bool(ctx)}'];missing=['trigger'] if not trigger else ['follow-through'] if not follow else [];conf=.95 if confirmed else .58 if trigger else .35
        elif sid.startswith('8'):
            policy=d.get('risk_policy') or {};minrr=float(policy.get('min_rr',1.5));maxstop=float(policy.get('max_stop_atr',3));ctx=' '.join(str(self._ctx(d,e)).upper() for e in ('E4','E5','E6','E7'));setup=any(x in ctx for x in ('SETUP_FORMING','MATURE','CONFIRMATION_PASS','TREND_PULLBACK','LIQUIDITY_REVERSAL','BREAKOUT_RETEST'));room=not((direction=='UP' and pos>.8) or (direction=='DOWN' and pos<.2));risk_ready=setup and room and not failure
            state={'8A':'INVALIDATION_DEFINED' if setup else 'INVALIDATION_PENDING','8B':'STOP_MODEL_READY' if setup else 'STOP_PENDING','8C':'TARGET_OBJECTIVE_READY' if room else 'TARGET_SPACE_LIMITED','8D':f'RR_MIN_{minrr:.2f}','8E':'POSITION_SIZE_RISK_BUDGET_REQUIRED','8F':'EXPOSURE_LIMIT_REQUIRED','8G':'RISK_READY' if risk_ready else 'RISK_NOT_READY'}[sid];thesis='Trade economics are potentially executable.' if risk_ready else 'Trade economics are not ready.';ev=[f'min_rr={minrr:.2f}',f'max_stop_atr={maxstop:.2f}',f'setup_present={setup}',f'room={room}',f'failure={failure}'];missing=['account risk budget'] if sid=='8E' else ['exposure limits'] if sid=='8F' else [];conf=.84 if risk_ready else .52
        else: state='UNKNOWN';thesis='Unknown specialist.';counter=['unknown sub-engine'];conf=0
        out={'state':state,'thesis':thesis,'observations':ev,'evidence':ev,'counter_evidence':counter,'confidence':round(conf,3),'missing_evidence':missing,'direction':direction,'analysis_basis':{'atr':round(atr,8),'ema20':round(e20,8),'ema50':round(e50,8),'body_ratio':round(br,3),'position':round(pos,3)}}
        return out,round(conf*100,1),[]

    def run(self,data):
        out,score,reasons=self._analyse(data)
        trace={'sub_engine_id':self.sub_engine_id,'symbol':data.get('symbol'),'timeframe':data.get('timeframe'),'candle_close_timestamp':data.get('candle_close_timestamp'),'spec_version':'production-v2.3.0-professional-subengine-brain','role':'ANALYST','gate_semantics':'DISABLED_E1_E8','decision_authority':'E9_ONLY','upstream_decisions_used':False,'upstream_gates_used':False,'output':out,'reason_codes':reasons}
        return SubEngineResult(self.sub_engine_id,out,True,score,trace)

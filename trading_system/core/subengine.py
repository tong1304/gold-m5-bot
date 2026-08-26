from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any


@dataclass(frozen=True)
class SubEngineResult:
    sub_engine_id: str
    output: dict[str, Any]
    gate_passed: bool
    score: float
    trace: dict[str, Any] = field(default_factory=dict)


class SubEngine:
    """Professional M5 evidence engine.

    Every 1A-9H module shares the implementation contract but has a distinct
    decision role. Parent engines remain responsible for final BUY/SELL.
    The model is deliberately asset-neutral and candle-close based.
    """

    def __init__(self, sub_engine_id: str | None = None):
        self.sub_engine_id = sub_engine_id or self._derive_id()

    def _derive_id(self) -> str:
        parts = self.__class__.__module__.split('.')
        engine = next((p[1:] for p in parts if p.startswith('e') and p[1:].isdigit()), '')
        return f"{engine}{parts[-1].split('_', 1)[0].upper()}"

    @staticmethod
    def _bars(data: dict[str, Any]) -> list[dict[str, Any]]:
        bars = data.get('bars') or []
        return [b for b in bars if isinstance(b, dict) and all(k in b for k in ('open','high','low','close'))]

    @staticmethod
    def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
        recent = bars[-period:]
        trs, prev = [], None
        for b in recent:
            h, l, c = float(b['high']), float(b['low']), float(b['close'])
            trs.append(h-l if prev is None else max(h-l, abs(h-prev), abs(l-prev)))
            prev = c
        return mean(trs) if trs else 0.0

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if not values:
            return 0.0
        alpha = 2.0 / (period + 1)
        value = values[0]
        for x in values[1:]:
            value = alpha*x + (1-alpha)*value
        return value

    @staticmethod
    def _slope(values: list[float], lookback: int = 5) -> float:
        if len(values) <= lookback:
            return 0.0
        return values[-1] - values[-1-lookback]

    @staticmethod
    def _pivot_points(bars: list[dict[str, Any]], left: int = 2, right: int = 2):
        highs, lows = [], []
        for i in range(left, len(bars)-right):
            hi = float(bars[i]['high']); lo = float(bars[i]['low'])
            if hi >= max(float(x['high']) for x in bars[i-left:i+right+1]):
                highs.append((i, hi))
            if lo <= min(float(x['low']) for x in bars[i-left:i+right+1]):
                lows.append((i, lo))
        return highs, lows

    @staticmethod
    def _direction_from_context(data: dict[str, Any]) -> str:
        for root in ('E1_result', 'E3_result', 'E6_result', 'E7_result'):
            ctx = data.get(root) or {}
            for key in ('1C','3B','6B','7A','7B'):
                d = str((ctx.get(key) or {}).get('direction','NEUTRAL')).upper()
                if d in {'UP','DOWN'}:
                    return d
        return 'NEUTRAL'

    def _analyse(self, data: dict[str, Any]):
        bars = self._bars(data)
        sid = self.sub_engine_id
        if len(bars) < 30 or not data.get('symbol') or not data.get('timeframe'):
            return {'state':'UNAVAILABLE'}, False, 0.0, ['INSUFFICIENT_OR_INVALID_MARKET_DATA']

        o = [float(b['open']) for b in bars]; h = [float(b['high']) for b in bars]
        l = [float(b['low']) for b in bars]; c = [float(b['close']) for b in bars]
        v = [float(b.get('volume',0) or 0) for b in bars]
        atr = self._atr(bars)
        ema20 = self._ema(c,20); ema50 = self._ema(c,50)
        last = c[-1]; prev = c[-2]
        candle_range = max(h[-1]-l[-1], 1e-12); body = abs(c[-1]-o[-1]); body_ratio = body/candle_range
        close_location = (c[-1]-l[-1])/candle_range
        returns = [c[i]/c[i-1]-1 for i in range(1,len(c)) if c[i-1]]
        vol = pstdev(returns[-30:]) if len(returns)>=2 else 0.0
        avg_range = mean([h[i]-l[i] for i in range(max(0,len(bars)-20),len(bars))])
        recent_range = max(h[-10:])-min(l[-10:]); base_range = max(h[-40:])-min(l[-40:])
        range_ratio = recent_range/base_range if base_range else 0.0
        slope20 = self._slope(c,5)
        trend_up = ema20 > ema50 and slope20 > 0 and last > ema20
        trend_down = ema20 < ema50 and slope20 < 0 and last < ema20
        direction = 'UP' if trend_up else 'DOWN' if trend_down else 'NEUTRAL'
        atr_strength = abs(slope20)/atr if atr else 0.0
        piv_h, piv_l = self._pivot_points(bars)
        ph = piv_h[-6:]; pl = piv_l[-6:]
        hh = len(ph)>=2 and ph[-1][1] > ph[-2][1]; lh = len(ph)>=2 and ph[-1][1] < ph[-2][1]
        hl = len(pl)>=2 and pl[-1][1] > pl[-2][1]; ll = len(pl)>=2 and pl[-1][1] < pl[-2][1]
        structure = 'BULLISH' if hh and hl else 'BEARISH' if lh and ll else ('BULLISH' if trend_up else 'BEARISH' if trend_down else 'NEUTRAL')
        recent_high = max(h[-20:-1]); recent_low = min(l[-20:-1])
        sweep_high = h[-1] > recent_high and last < recent_high
        sweep_low = l[-1] < recent_low and last > recent_low
        displacement = body_ratio >= .65 and body >= .8*atr
        volume_expansion = bool(v[-1] and len(v)>=20 and v[-1] >= 1.25*mean(v[-20:]))
        expansion = (h[-1]-l[-1]) >= 1.35*max(avg_range,1e-12) or displacement
        compression = avg_range > 0 and mean([h[i]-l[i] for i in range(max(0,len(bars)-6),len(bars))]) < .70*avg_range
        position = (last-min(l[-40:]))/(max(h[-40:])-min(l[-40:])) if max(h[-40:]) != min(l[-40:]) else .5
        reasons=[]; gate=True; score=70.0; ev={'bars':len(bars),'last_close':last,'atr':round(atr,8),'ema20':round(ema20,8),'ema50':round(ema50,8)}

        # E1: market state
        if sid=='1A':
            ev.update(data_quality='VALID', state='READY'); score=100; reasons=['OHLC/timeframe/symbol valid']
        elif sid=='1B':
            state='EXPANSION' if expansion else 'COMPRESSION' if compression else 'NORMAL_VOLATILITY'
            ev.update(state=state, volatility=round(vol,8), range_ratio=round(range_ratio,4)); score=90 if state!='NORMAL_VOLATILITY' else 78
        elif sid=='1C':
            ev.update(direction=direction, state='TREND_UP' if direction=='UP' else 'TREND_DOWN' if direction=='DOWN' else 'NEUTRAL', trend_strength_atr=round(atr_strength,3), ema_alignment=direction!='NEUTRAL'); score=92 if direction!='NEUTRAL' and atr_strength>=.45 else 62
        elif sid=='1D':
            state='RANGE' if range_ratio<.45 and atr_strength<.6 else 'DIRECTIONAL'
            ev.update(state=state, high=max(h[-40:]), low=min(l[-40:]), width=round(max(h[-40:])-min(l[-40:]),8)); score=88 if state=='RANGE' else 82
        elif sid=='1E':
            ev.update(state='COMPRESSION' if compression else 'NO_COMPRESSION', range_ratio=round(range_ratio,4)); score=90 if compression else 65
        elif sid=='1F':
            ev.update(state='EXPANSION' if expansion else 'NO_EXPANSION', displacement=displacement, volume_expansion=volume_expansion); score=92 if expansion else 64
        elif sid=='1G':
            dominant = direction!='NEUTRAL' and structure==('BULLISH' if direction=='UP' else 'BEARISH') and atr_strength>=.45 and not (sweep_high or sweep_low)
            state='DOMINANT' if dominant else 'TRANSITION' if (direction=='NEUTRAL' or (sweep_high and sweep_low)) else 'NON_DOMINANT'
            ev.update(state=state,direction=direction,structure=structure,trend_strength_atr=round(atr_strength,3)); score=94 if dominant else 55
            if state=='TRANSITION': gate=False; reasons=['market state is transitioning']

        # E2: regime
        elif sid in {'2A','2B','2C','2D','2E','2F'}:
            regime='TREND' if direction!='NEUTRAL' and atr_strength>=.45 and structure==('BULLISH' if direction=='UP' else 'BEARISH') else 'RANGE' if range_ratio<.45 and not expansion else 'BREAKOUT' if expansion and (last>recent_high or last<recent_low) else 'MEAN_REVERSION' if position<.2 or position>.8 else 'TRANSITION'
            mapping={'2A':('TREND' if regime=='TREND' else 'NOT_TREND'),'2B':('RANGE' if regime=='RANGE' else 'NOT_RANGE'),'2C':('MEAN_REVERSION' if regime=='MEAN_REVERSION' else 'NOT_MEAN_REVERSION'),'2D':('BREAKOUT' if regime=='BREAKOUT' else 'NOT_BREAKOUT'),'2E':('EXPANSION_PHASE' if expansion else 'BALANCED_PHASE'),'2F':regime}
            label=mapping[sid]; ev.update(regime=label,direction=direction,range_ratio=round(range_ratio,4),trend_strength_atr=round(atr_strength,3)); score=90 if not label.startswith('NOT_') and label!='TRANSITION' else 60
            if sid=='2F' and regime=='TRANSITION': gate=False; reasons=['regime transition']

        # E3: structure
        elif sid in {'3A','3B','3C','3D','3E','3F'}:
            bos_up=bool(ph and last>ph[-1][1]); bos_down=bool(pl and last<pl[-1][1]); bos='BULLISH_BOS' if bos_up else 'BEARISH_BOS' if bos_down else 'NO_BOS'
            failure='BULLISH_FAILURE' if structure=='BULLISH' and last < (pl[-1][1] if pl else -float('inf')) else 'BEARISH_FAILURE' if structure=='BEARISH' and last > (ph[-1][1] if ph else float('inf')) else 'NO_FAILURE'
            strength=min(100, round(45 + 20*int(hh or hl) + 20*int(lh or ll) + 20*min(1,atr_strength),1))
            labels={'3A':'SWINGS_IDENTIFIED','3B':structure,'3C':bos,'3D':failure,'3E':('STRONG' if strength>=75 else 'MODERATE' if strength>=55 else 'WEAK'),'3F':('INTERNAL_EXTERNAL_ALIGNED' if direction!='NEUTRAL' and structure==('BULLISH' if direction=='UP' else 'BEARISH') else 'INTERNAL_EXTERNAL_MIXED')}
            label=labels[sid]; ev.update(state=label,direction=direction,higher_high=hh,higher_low=hl,lower_high=lh,lower_low=ll,structure_strength=strength); score=90 if structure!='NEUTRAL' else 58
            if sid=='3D' and failure!='NO_FAILURE': gate=False; reasons=['structural failure detected']

        # E4: liquidity
        elif sid in {'4A','4B','4C','4D','4E','4F'}:
            equal_high=bool(ph and abs(ph[-1][1]-(ph[-2][1] if len(ph)>1 else ph[-1][1])) <= .15*atr)
            equal_low=bool(pl and abs(pl[-1][1]-(pl[-2][1] if len(pl)>1 else pl[-1][1])) <= .15*atr)
            rejection=(sweep_high and close_location<.45) or (sweep_low and close_location>.55)
            acceptance=(last>recent_high and close_location>.7) or (last<recent_low and close_location<.3)
            reclaim=(sweep_high and last>recent_high) or (sweep_low and last<recent_low)
            labels={'4A':'LIQUIDITY_POOLS_IDENTIFIED','4B':'SWEEP_HIGH' if sweep_high else 'SWEEP_LOW' if sweep_low else 'NO_SWEEP','4C':'REJECTION' if rejection else 'NO_REJECTION','4D':'ACCEPTANCE' if acceptance else 'NO_ACCEPTANCE','4E':'RECLAIM' if reclaim else 'FAILED_BREAK' if (sweep_high or sweep_low) and not rejection else 'NO_RECLAIM','4F':'HIGH_QUALITY' if (sweep_high or sweep_low) and rejection and displacement else 'QUALITY_MEASURABLE'}
            label=labels[sid]; ev.update(state=label,sweep_high=sweep_high,sweep_low=sweep_low,equal_high=equal_high,equal_low=equal_low,rejection=rejection,acceptance=acceptance); score=93 if label=='HIGH_QUALITY' else 82

        # E5: location
        elif sid in {'5A','5B','5C','5D','5E','5F'}:
            loc='PREMIUM' if position>.6 else 'DISCOUNT' if position<.4 else 'EQUILIBRIUM'
            ext='EXTENDED' if (direction=='UP' and position>.85) or (direction=='DOWN' and position<.15) else 'NOT_EXTENDED'
            room='LIMITED_SPACE' if (direction=='UP' and position>.80) or (direction=='DOWN' and position<.20) else 'SPACE_AVAILABLE'
            liquidity_side='ABOVE' if direction=='UP' else 'BELOW' if direction=='DOWN' else 'BOTH'
            labels={'5A':loc,'5B':('STRUCTURAL_DISCOUNT' if direction=='UP' and position<.5 else 'STRUCTURAL_PREMIUM' if direction=='DOWN' and position>.5 else 'NEUTRAL_LOCATION'),'5C':liquidity_side,'5D':ext,'5E':room,'5F':'LOCATION_QUALITY_PASS' if ext=='NOT_EXTENDED' and room=='SPACE_AVAILABLE' else 'LOCATION_QUALITY_FAIL'}
            label=labels[sid]; ev.update(state=label,position_in_range=round(position,4),location=loc); score=92 if label=='LOCATION_QUALITY_PASS' else 60
            if sid=='5F' and label!='LOCATION_QUALITY_PASS': gate=False; reasons=['poor location or insufficient room']

        # E6: setup state machine
        elif sid in {'6A','6B','6C','6D','6E','6F'}:
            e2=data.get('E2_result') or {}; e4=data.get('E4_result') or {}
            regime=next((str((e2.get(k) or {}).get('regime','')) for k in ('2F','2A','2B','2C','2D') if (e2.get(k) or {}).get('regime')), '')
            sweep=bool((e4.get('4B') or {}).get('state') in {'SWEEP_HIGH','SWEEP_LOW'})
            rejection=bool((e4.get('4C') or {}).get('state')=='REJECTION')
            archetype='TREND_PULLBACK' if regime=='TREND' and not sweep else 'LIQUIDITY_REVERSAL' if sweep and rejection else 'BREAKOUT_RETEST' if regime=='BREAKOUT' else 'RANGE_REJECTION' if regime=='RANGE' else 'MEAN_REVERSION'
            formation='SETUP_FORMING' if (direction!='NEUTRAL' or sweep or regime in {'RANGE','MEAN_REVERSION','BREAKOUT'}) else 'NO_SETUP'
            valid=formation!='NO_SETUP' and not ((sweep_high or sweep_low) and not rejection and not displacement)
            maturity='MATURE' if valid and displacement and (rejection or direction!='NEUTRAL') else 'DEVELOPING'
            labels={'6A':'CONTEXT_ALIGNED' if formation!='NO_SETUP' else 'CONTEXT_INVALID','6B':archetype,'6C':formation,'6D':'NOT_INVALIDATED' if valid else 'SETUP_INVALIDATED','6E':'QUALITY_PASS' if valid and (rejection or displacement) else 'QUALITY_WEAK','6F':maturity}
            label=labels[sid]; ev.update(state=label,archetype=archetype,direction=direction,displacement=displacement,rejection=rejection); score=94 if label in {'MATURE','QUALITY_PASS'} else 65
            if sid=='6D' and not valid: gate=False; reasons=['setup invalidated']

        # E7: trigger/confirmation
        elif sid in {'7A','7B','7C','7D','7E','7F'}:
            e6=data.get('E6_result') or {}; archetype=next((str((e6.get(k) or {}).get('archetype','')) for k in ('6B',) if e6.get(k)), '')
            breakout_up=last>recent_high and displacement; breakout_down=last<recent_low and displacement
            trigger=(displacement and direction!='NEUTRAL') or (archetype=='LIQUIDITY_REVERSAL' and ((sweep_low and direction=='UP') or (sweep_high and direction=='DOWN'))) or breakout_up or breakout_down
            follow=trigger and abs(last-prev)>=.35*atr
            failure=(direction=='UP' and last<prev-.35*atr) or (direction=='DOWN' and last>prev+.35*atr)
            quality=trigger and (body_ratio>=.60) and (close_location>.65 if direction=='UP' else close_location<.35 if direction=='DOWN' else True)
            confirmation=trigger and quality and follow and not failure
            labels={'7A':'TRIGGER_OBSERVED' if trigger else 'NO_TRIGGER','7B':'QUALITY_PASS' if quality else 'QUALITY_WEAK','7C':'FOLLOW_THROUGH_OBSERVED' if follow else 'NO_FOLLOW_THROUGH','7D':'FAILURE' if failure else 'NO_FAILURE','7E':'EXECUTION_CONDITIONS_PASS' if confirmation else 'EXECUTION_CONDITIONS_WAIT','7F':'CONFIRMATION_PASS' if confirmation else 'CONFIRMATION_WAIT'}
            label=labels[sid]; ev.update(state=label,direction=direction,trigger=trigger,quality=quality,follow_through=follow,failure=failure,body_ratio=round(body_ratio,3)); score=95 if confirmation else 65
            if sid=='7F' and not confirmation: gate=False; reasons=['trigger confirmation incomplete']

        # E8: risk evidence; actual plan is built by production_v2/engines.py
        elif sid in {'8A','8B','8C','8D','8E','8F','8G'}:
            policy=data.get('risk_policy') or {}; min_rr=float(policy.get('min_rr',1.5)); max_stop=float(policy.get('max_stop_atr',3.0))
            labels={'8A':'STRUCTURAL_INVALIDATION_REQUIRED','8B':'STOP_MUST_BE_BEYOND_INVALIDATION','8C':'TARGET_MUST_USE_LIQUIDITY_OR_RR','8D':'RR>=MINIMUM_REQUIRED','8E':'POSITION_SIZE_RISK_BUDGET_REQUIRED','8F':'EXPOSURE_LIMIT_REQUIRED','8G':'RISK_GATE_READY'}
            label=labels[sid]; ev.update(state=label,min_rr=min_rr,max_stop_atr=max_stop); score=88

        # E9: final authority evidence
        elif sid in {'9A','9B','9C','9D','9E','9F','9G','9H'}:
            labels={'9A':'DATA_GATE','9B':'CONTEXT_GATE','9C':'SETUP_GATE','9D':'CONFIRMATION_GATE','9E':'RISK_GATE','9F':'EXECUTION_GATE','9G':'FINAL_DECISION_SYNTHESIS','9H':'DECISION_LOGGING'}
            label=labels[sid]; ev.update(state=label,authority='E9'); score=90
        else:
            gate=False; score=0; reasons=['UNKNOWN_SUB_ENGINE_ID']; ev['state']='UNKNOWN'

        return ev, gate, round(score,1), reasons

    def run(self, data: dict[str, Any]) -> SubEngineResult:
        output, gate, score, reasons=self._analyse(data)
        trace={'sub_engine_id':self.sub_engine_id,'symbol':data.get('symbol'),'timeframe':data.get('timeframe'),'candle_close_timestamp':data.get('candle_close_timestamp'),'spec_version':'production-v2.1.0-professional-m5','input_references':{'bar_count':len(self._bars(data))},'output':output,'gate':'PASS' if gate else 'FAIL','score':score,'reason_codes':reasons}
        return SubEngineResult(self.sub_engine_id,output,gate,score,trace)

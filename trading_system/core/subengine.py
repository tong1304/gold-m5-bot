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
    """Independent professional M5 analyst.

    E1-E8 are analysts, not trade gates. Each specialist derives observations
    from the closed-candle snapshot, may read permitted evidence context, and
    returns a thesis with supporting/counter evidence. E9 owns the final trade
    decision. No specialist is allowed to manufacture BUY/SELL authority.
    """

    def __init__(self, sub_engine_id: str | None = None):
        self.sub_engine_id = sub_engine_id or self._derive_id()

    def _derive_id(self) -> str:
        parts = self.__class__.__module__.split('.')
        engine = next((p[1:] for p in parts if p.startswith('e') and p[1:].isdigit()), '')
        leaf = parts[-1].split('_', 1)[0].upper()
        return f"{engine}{leaf}"

    @staticmethod
    def _bars(data: dict[str, Any]) -> list[dict[str, Any]]:
        bars = data.get('bars') or []
        return [b for b in bars if isinstance(b, dict) and all(k in b for k in ('open', 'high', 'low', 'close'))]

    @staticmethod
    def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
        if not bars:
            return 0.0
        trs, prev = [], None
        for b in bars[-period:]:
            h, l, c = float(b['high']), float(b['low']), float(b['close'])
            trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
            prev = c
        return mean(trs) if trs else 0.0

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if not values:
            return 0.0
        alpha = 2.0 / (period + 1)
        x = values[0]
        for value in values[1:]:
            x = alpha * value + (1 - alpha) * x
        return x

    @staticmethod
    def _pivots(bars: list[dict[str, Any]], left: int = 2, right: int = 2):
        highs, lows = [], []
        for i in range(left, max(left, len(bars) - right)):
            hi = float(bars[i]['high']); lo = float(bars[i]['low'])
            window = bars[i-left:i+right+1]
            if hi >= max(float(x['high']) for x in window): highs.append((i, hi))
            if lo <= min(float(x['low']) for x in window): lows.append((i, lo))
        return highs, lows

    @staticmethod
    def _ctx(data: dict[str, Any], engine: str) -> dict[str, Any]:
        value = data.get(f'{engine}_result') or {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _state_from_ctx(data: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        found = []
        for engine in keys:
            ctx = SubEngine._ctx(data, engine)
            for sid, item in ctx.items():
                if isinstance(item, dict):
                    found.append({'source': sid, **item})
        return found

    def _analyse(self, data: dict[str, Any]):
        bars = self._bars(data)
        if len(bars) < 30 or not data.get('symbol') or not data.get('timeframe'):
            return ({'state': 'UNAVAILABLE', 'thesis': 'INSUFFICIENT_DATA', 'evidence': [],
                     'counter_evidence': ['insufficient closed candles'], 'confidence': 0.0,
                     'missing_evidence': ['valid OHLC history']}, True, 0.0, ['INSUFFICIENT_MARKET_DATA'])

        o = [float(b['open']) for b in bars]; h = [float(b['high']) for b in bars]
        l = [float(b['low']) for b in bars]; c = [float(b['close']) for b in bars]
        v = [float(b.get('volume', 0) or 0) for b in bars]
        atr = self._atr(bars); last, prev = c[-1], c[-2]
        ema20, ema50 = self._ema(c, 20), self._ema(c, 50)
        slope = c[-1] - c[-6] if len(c) >= 6 else 0.0
        trend_strength = abs(slope) / atr if atr else 0.0
        direction = 'UP' if ema20 > ema50 and slope > 0 and last >= ema20 else 'DOWN' if ema20 < ema50 and slope < 0 and last <= ema20 else 'NEUTRAL'
        candle_range = max(h[-1] - l[-1], 1e-12); body = abs(c[-1] - o[-1]); body_ratio = body / candle_range
        close_pos = (last - l[-1]) / candle_range
        ranges = [h[i] - l[i] for i in range(max(0, len(bars)-20), len(bars))]
        avg_range = mean(ranges) if ranges else candle_range
        recent_range = max(h[-10:]) - min(l[-10:]); base_range = max(h[-40:]) - min(l[-40:])
        range_ratio = recent_range / base_range if base_range else 1.0
        compression = mean([h[i]-l[i] for i in range(max(0, len(bars)-6), len(bars))]) < 0.70 * max(avg_range, 1e-12)
        displacement = body_ratio >= 0.65 and body >= 0.80 * max(atr, 1e-12)
        vol_expansion = bool(v[-1] and len(v) >= 20 and v[-1] >= 1.25 * max(mean(v[-20:]), 1e-12))
        expansion = candle_range >= 1.35 * max(avg_range, 1e-12) or displacement
        hi20, lo20 = max(h[-20:-1]), min(l[-20:-1])
        sweep_high = h[-1] > hi20 and last < hi20
        sweep_low = l[-1] < lo20 and last > lo20
        piv_h, piv_l = self._pivots(bars); ph, pl = piv_h[-6:], piv_l[-6:]
        hh = len(ph) >= 2 and ph[-1][1] > ph[-2][1]; lh = len(ph) >= 2 and ph[-1][1] < ph[-2][1]
        hl = len(pl) >= 2 and pl[-1][1] > pl[-2][1]; ll = len(pl) >= 2 and pl[-1][1] < pl[-2][1]
        structure = 'BULLISH' if hh and hl else 'BEARISH' if lh and ll else ('BULLISH' if direction == 'UP' else 'BEARISH' if direction == 'DOWN' else 'NEUTRAL')
        position = (last - min(l[-40:])) / max(max(h[-40:]) - min(l[-40:]), 1e-12)
        position = max(0.0, min(1.0, position))
        rejection = (sweep_high and close_pos < 0.45) or (sweep_low and close_pos > 0.55)
        acceptance = (last > hi20 and close_pos > 0.70) or (last < lo20 and close_pos < 0.30)
        failure = (direction == 'UP' and last < prev - 0.35*atr) or (direction == 'DOWN' and last > prev + 0.35*atr)
        body_direction = 'UP' if c[-1] > o[-1] else 'DOWN' if c[-1] < o[-1] else 'FLAT'

        sid = self.sub_engine_id
        evidence: list[str] = []; counter: list[str] = []; missing: list[str] = []
        state = 'UNRESOLVED'; thesis = 'UNRESOLVED'; confidence = 0.50; score = 50.0

        if sid == '1A':
            state = 'DATA_READY'; thesis = 'Market snapshot is usable.'
            evidence = [f'{len(bars)} valid OHLC candles', 'symbol/timeframe present', 'closed-candle evaluation']
            confidence = 1.0; score = 100
        elif sid == '1B':
            state = 'EXPANSION' if expansion else 'COMPRESSION' if compression else 'NORMAL_VOLATILITY'
            thesis = f'Volatility regime is {state}.'
            evidence = [f'range_ratio={range_ratio:.3f}', f'ATR={atr:.8f}', f'displacement={displacement}', f'volume_expansion={vol_expansion}']
            confidence = min(1.0, 0.55 + 0.25*float(expansion or compression) + 0.20*float(vol_expansion)); score = 100*confidence
        elif sid == '1C':
            state = 'TREND_UP' if direction == 'UP' else 'TREND_DOWN' if direction == 'DOWN' else 'NO_CLEAR_TREND'
            thesis = 'Directional trend is present.' if direction != 'NEUTRAL' else 'Directional trend is not sufficiently established.'
            evidence = [f'EMA20={ema20:.8f}', f'EMA50={ema50:.8f}', f'slope_ATR={trend_strength:.3f}', f'direction={direction}']
            counter = ['EMA/slope alignment is incomplete.'] if direction == 'NEUTRAL' else []
            confidence = min(1.0, 0.50 + 0.35*min(trend_strength, 1.0) + 0.15*float(direction != 'NEUTRAL')); score = 100*confidence
        elif sid == '1D':
            state = 'RANGE' if range_ratio < 0.45 and trend_strength < 0.60 else 'DIRECTIONAL'
            thesis = f'Market is {state.lower()} rather than assuming a trend.'
            evidence = [f'40-bar range={max(h[-40:])-min(l[-40:]):.8f}', f'10/40 range ratio={range_ratio:.3f}', f'trend_strength_ATR={trend_strength:.3f}']
            confidence = 0.88 if state == 'RANGE' else 0.78; score = 100*confidence
        elif sid == '1E':
            state = 'COMPRESSION' if compression else 'NO_COMPRESSION'; thesis = 'Volatility is compressing.' if compression else 'No material compression detected.'
            evidence = [f'6-bar average range={mean([h[i]-l[i] for i in range(-6,0)]):.8f}', f'20-bar average range={avg_range:.8f}']; confidence = 0.90 if compression else 0.72; score=100*confidence
        elif sid == '1F':
            state = 'EXPANSION' if expansion else 'NO_EXPANSION'; thesis = 'Expansion is active.' if expansion else 'Expansion is not proven.'
            evidence = [f'body_ratio={body_ratio:.3f}', f'candle_range/avg={candle_range/max(avg_range,1e-12):.3f}', f'volume_expansion={vol_expansion}']; confidence=0.92 if expansion and displacement else 0.68; score=100*confidence
        elif sid == '1G':
            transition = direction == 'NEUTRAL' or ((sweep_high or sweep_low) and failure)
            state = 'TRANSITION' if transition else 'STABLE'
            thesis = 'Market state may be transitioning.' if transition else 'Current state is relatively stable.'
            evidence=[f'direction={direction}', f'structure={structure}', f'sweep_high={sweep_high}', f'sweep_low={sweep_low}']; confidence=0.82 if transition else 0.78; score=100*confidence

        elif sid.startswith('2'):
            trend = direction != 'NEUTRAL' and trend_strength >= 0.45 and structure == ('BULLISH' if direction=='UP' else 'BEARISH')
            range_regime = range_ratio < 0.45 and not expansion
            breakout = expansion and (last > hi20 or last < lo20)
            meanrev = position < 0.20 or position > 0.80
            regime = 'TREND' if trend else 'RANGE' if range_regime else 'BREAKOUT' if breakout else 'MEAN_REVERSION' if meanrev else 'TRANSITION'
            labels={'2A':'TREND' if trend else 'NOT_TREND','2B':'RANGE' if range_regime else 'NOT_RANGE','2C':'MEAN_REVERSION' if meanrev else 'NOT_MEAN_REVERSION','2D':'BREAKOUT' if breakout else 'NOT_BREAKOUT','2E':'EXPANSION_PHASE' if expansion else 'BALANCED_PHASE','2F':regime}
            state=labels.get(sid,'TRANSITION'); thesis=f'Best-fit market opportunity is {regime}.'
            evidence=[f'regime={regime}',f'direction={direction}',f'trend_strength_ATR={trend_strength:.3f}',f'range_ratio={range_ratio:.3f}',f'expansion={expansion}']
            counter=['Competing regime characteristics exist.'] if regime=='TRANSITION' else []
            confidence=0.88 if regime!='TRANSITION' else 0.55; score=100*confidence

        elif sid.startswith('3'):
            bos_up=bool(ph and last > ph[-1][1]); bos_down=bool(pl and last < pl[-1][1])
            bos='BULLISH_BOS' if bos_up else 'BEARISH_BOS' if bos_down else 'NO_BOS'
            structural_failure='FAILURE' if failure else 'NO_FAILURE'
            strength=min(1.0,0.40+0.20*float(hh or hl)+0.20*float(lh or ll)+0.20*min(trend_strength,1.0))
            labels={'3A':'SWINGS_IDENTIFIED','3B':structure,'3C':bos,'3D':structural_failure,'3E':'STRONG' if strength>=0.75 else 'MODERATE' if strength>=0.55 else 'WEAK','3F':'ALIGNED' if direction!='NEUTRAL' and structure==('BULLISH' if direction=='UP' else 'BEARISH') else 'MIXED'}
            state=labels[sid]; thesis=f'Structure is {structure.lower()} with {state.lower()} evidence.'
            evidence=[f'HH={hh}',f'HL={hl}',f'LH={lh}',f'LL={ll}',f'BOS={bos}',f'strength={strength:.2f}']; counter=['Internal/external structure is mixed.'] if state=='MIXED' else []
            confidence=strength; score=100*confidence

        elif sid.startswith('4'):
            equal_high=bool(len(ph)>=2 and abs(ph[-1][1]-ph[-2][1]) <= 0.15*max(atr,1e-12))
            equal_low=bool(len(pl)>=2 and abs(pl[-1][1]-pl[-2][1]) <= 0.15*max(atr,1e-12))
            reclaim=(sweep_high and last>hi20) or (sweep_low and last<lo20)
            labels={'4A':'POOLS_IDENTIFIED','4B':'SWEEP_HIGH' if sweep_high else 'SWEEP_LOW' if sweep_low else 'NO_SWEEP','4C':'REJECTION' if rejection else 'NO_REJECTION','4D':'ACCEPTANCE' if acceptance else 'NO_ACCEPTANCE','4E':'RECLAIM' if reclaim else 'FAILED_BREAK' if (sweep_high or sweep_low) else 'NO_RECLAIM','4F':'HIGH_QUALITY' if (sweep_high or sweep_low) and rejection and displacement else 'QUALITY_NOT_PROVEN'}
            state=labels[sid]; thesis='Liquidity event is actionable.' if state in {'REJECTION','HIGH_QUALITY','RECLAIM'} else 'Liquidity event is not yet proven.'
            evidence=[f'equal_high={equal_high}',f'equal_low={equal_low}',f'sweep_high={sweep_high}',f'sweep_low={sweep_low}',f'rejection={rejection}',f'acceptance={acceptance}',f'reclaim={reclaim}']; counter=['No confirmed sweep/reaction.'] if not (sweep_high or sweep_low or acceptance) else []
            confidence=0.94 if state=='HIGH_QUALITY' else 0.82 if state in {'REJECTION','RECLAIM','ACCEPTANCE'} else 0.52; score=100*confidence

        elif sid.startswith('5'):
            location='PREMIUM' if position>0.60 else 'DISCOUNT' if position<0.40 else 'EQUILIBRIUM'
            extended=(direction=='UP' and position>0.85) or (direction=='DOWN' and position<0.15)
            room=not ((direction=='UP' and position>0.80) or (direction=='DOWN' and position<0.20))
            labels={'5A':location,'5B':'STRUCTURAL_DISCOUNT' if direction=='UP' and position<0.50 else 'STRUCTURAL_PREMIUM' if direction=='DOWN' and position>0.50 else 'NEUTRAL','5C':'LIQUIDITY_ABOVE' if direction=='UP' else 'LIQUIDITY_BELOW' if direction=='DOWN' else 'LIQUIDITY_BOTH','5D':'EXTENDED' if extended else 'NOT_EXTENDED','5E':'SPACE_AVAILABLE' if room else 'LIMITED_SPACE','5F':'LOCATION_QUALITY_PASS' if room and not extended else 'LOCATION_QUALITY_FAIL'}
            state=labels[sid]; thesis='Location offers usable asymmetric space.' if state=='LOCATION_QUALITY_PASS' else 'Location is less attractive or space is constrained.'
            evidence=[f'position_40bar={position:.3f}',f'location={location}',f'extended={extended}',f'room={room}']; counter=['Price is extended or available space is limited.'] if not room or extended else []
            confidence=0.90 if state=='LOCATION_QUALITY_PASS' else 0.58; score=100*confidence

        elif sid.startswith('6'):
            upstream=self._state_from_ctx(data,('E1','E2','E3','E4','E5'))
            text=' '.join(str(x).upper() for x in upstream)
            trend_hint='TREND' in text or direction!='NEUTRAL'; sweep_hint='SWEEP_' in text or sweep_high or sweep_low; reject_hint='REJECTION' in text or rejection
            archetype='LIQUIDITY_REVERSAL' if sweep_hint and reject_hint else 'BREAKOUT_RETEST' if expansion and acceptance else 'TREND_PULLBACK' if trend_hint and not extended if False else ('TREND_PULLBACK' if trend_hint else 'RANGE_REJECTION' if position<0.20 or position>0.80 else 'NO_VALID_SETUP')
            # The expression above intentionally keeps setup selection deterministic and asset-neutral.
            formation = archetype != 'NO_VALID_SETUP'
            mature = formation and (displacement or rejection or acceptance)
            labels={'6A':'CONTEXT_ALIGNED' if formation else 'CONTEXT_UNCLEAR','6B':archetype,'6C':'SETUP_FORMING' if formation else 'NO_SETUP','6D':'NOT_INVALIDATED' if formation and not failure else 'INVALIDATED','6E':'QUALITY_PASS' if mature and not failure else 'QUALITY_WEAK','6F':'MATURE' if mature and not failure else 'DEVELOPING' if formation else 'ABSENT'}
            state=labels[sid]; thesis=f'{archetype} is {"mature" if mature else "developing"}.' if formation else 'No valid setup thesis is formed.'
            evidence=[f'archetype={archetype}',f'formation={formation}',f'displacement={displacement}',f'rejection={rejection}',f'acceptance={acceptance}',f'failure={failure}',f'upstream_evidence_items={len(upstream)}']; counter=['Setup lacks confirmation-quality price behavior.'] if formation and not mature else []
            missing=['trigger/follow-through'] if formation and not mature else []; confidence=0.88 if mature and not failure else 0.62 if formation else 0.35; score=100*confidence

        elif sid.startswith('7'):
            upstream=self._state_from_ctx(data,('E3','E4','E5','E6'))
            text=' '.join(str(x).upper() for x in upstream)
            trigger=(displacement and direction!='NEUTRAL') or (sweep_low and direction=='UP') or (sweep_high and direction=='DOWN') or (expansion and acceptance)
            follow=trigger and abs(last-prev)>=0.35*max(atr,1e-12)
            quality=trigger and body_ratio>=0.60 and (close_pos>0.65 if direction=='UP' else close_pos<0.35 if direction=='DOWN' else True)
            confirmed=trigger and quality and follow and not failure
            labels={'7A':'TRIGGER_OBSERVED' if trigger else 'NO_TRIGGER','7B':'QUALITY_PASS' if quality else 'QUALITY_WEAK','7C':'FOLLOW_THROUGH_OBSERVED' if follow else 'NO_FOLLOW_THROUGH','7D':'FAILURE' if failure else 'NO_FAILURE','7E':'EXECUTION_CONDITIONS_PASS' if confirmed else 'WAIT','7F':'CONFIRMATION_PASS' if confirmed else 'CONFIRMATION_WAIT'}
            state=labels[sid]; thesis='Price has confirmed the setup thesis.' if confirmed else 'Setup thesis is not yet confirmed.'
            evidence=[f'trigger={trigger}',f'quality={quality}',f'follow_through={follow}',f'failure={failure}',f'body_ratio={body_ratio:.3f}',f'upstream_evidence_items={len(upstream)}']; counter=['Follow-through or trigger quality is insufficient.'] if not confirmed else []
            missing=['follow-through'] if trigger and not follow else ['trigger'] if not trigger else []; confidence=0.95 if confirmed else 0.58 if trigger else 0.35; score=100*confidence

        elif sid.startswith('8'):
            policy=data.get('risk_policy') or {}; min_rr=float(policy.get('min_rr',1.5)); max_stop=float(policy.get('max_stop_atr',3.0))
            setup_text=' '.join(str(x).upper() for x in self._state_from_ctx(data,('E6','E7','E4','E5')))
            setup_present=any(x in setup_text for x in ('SETUP_FORMING','MATURE','CONFIRMATION_PASS','TREND_PULLBACK','LIQUIDITY_REVERSAL','BREAKOUT_RETEST'))
            risk_ready=setup_present and not failure and room_available(position,direction)
            stop_distance=min(max(atr,1e-12)*1.5, max_stop*max(atr,1e-12))
            target_distance=stop_distance*min_rr
            labels={'8A':'INVALIDATION_DEFINED' if setup_present else 'INVALIDATION_PENDING','8B':'STOP_MODEL_READY' if setup_present else 'STOP_PENDING','8C':'TARGET_OBJECTIVE_READY' if room_available(position,direction) else 'TARGET_SPACE_LIMITED','8D':'RR_REQUIREMENT_DEFINED','8E':'POSITION_SIZE_REQUIRES_RISK_BUDGET','8F':'EXPOSURE_LIMIT_REQUIRES_ACCOUNT_STATE','8G':'RISK_READY' if risk_ready else 'RISK_NOT_READY'}
            state=labels[sid]; thesis='Trade economics can be modeled.' if risk_ready else 'Trade economics are not ready for commitment.'
            evidence=[f'min_rr={min_rr:.2f}',f'max_stop_atr={max_stop:.2f}',f'setup_present={setup_present}',f'room_available={room_available(position,direction)}',f'failure={failure}',f'provisional_stop_atr={stop_distance/max(atr,1e-12):.2f}',f'provisional_target_atr={target_distance/max(atr,1e-12):.2f}']; counter=['Setup/space/invalidation evidence is incomplete.'] if not risk_ready else []
            missing=['account risk budget'] if sid=='8E' else ['exposure limits'] if sid=='8F' else []; confidence=0.84 if risk_ready else 0.52; score=100*confidence
        else:
            state='UNKNOWN'; thesis='Unknown specialist.'; counter=['Unknown sub-engine']; confidence=0.0; score=0.0

        output={'state':state,'thesis':thesis,'observations':evidence,'evidence':evidence,'counter_evidence':counter,'confidence':round(confidence,3),'missing_evidence':missing,'direction':direction,'analysis_basis':{'atr':round(atr,8),'ema20':round(ema20,8),'ema50':round(ema50,8),'body_ratio':round(body_ratio,3),'position':round(position,3)}}
        return output, True, round(score,1), []

    def run(self, data: dict[str, Any]) -> SubEngineResult:
        output, _, score, reasons = self._analyse(data)
        trace={'sub_engine_id':self.sub_engine_id,'symbol':data.get('symbol'),'timeframe':data.get('timeframe'),'candle_close_timestamp':data.get('candle_close_timestamp'),'spec_version':'production-v2.2.0-professional-subengine-brain','output':output,'role':'ANALYST','gate_semantics':'DISABLED_E1_E8','decision_authority':'E9_ONLY','upstream_decisions_used':False,'upstream_gates_used':False,'reason_codes':reasons}
        return SubEngineResult(self.sub_engine_id, output, True, score, trace)


def room_available(position: float, direction: str) -> bool:
    if direction == 'UP':
        return position < 0.80
    if direction == 'DOWN':
        return position > 0.20
    return 0.20 <= position <= 0.80

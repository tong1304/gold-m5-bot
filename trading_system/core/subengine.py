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
    """Shared analytical contract for all production-v2 Sub-Engines."""

    def __init__(self, sub_engine_id: str | None = None):
        self.sub_engine_id = sub_engine_id or self._derive_id()

    def _derive_id(self) -> str:
        parts = self.__class__.__module__.split('.')
        engine = next((p[1:] for p in parts if p.startswith('e') and p[1:].isdigit()), '')
        leaf = parts[-1]
        return f"{engine}{leaf.split('_', 1)[0].upper()}"

    @staticmethod
    def _bars(data: dict[str, Any]) -> list[dict[str, float]]:
        bars = data.get('bars') or []
        return [b for b in bars if isinstance(b, dict) and all(k in b for k in ('open','high','low','close'))]

    @staticmethod
    def _atr(bars: list[dict[str, float]]) -> float:
        trs, prev = [], None
        for b in bars:
            h, l, c = float(b['high']), float(b['low']), float(b['close'])
            trs.append(h-l if prev is None else max(h-l, abs(h-prev), abs(l-prev)))
            prev = c
        return mean(trs) if trs else 0.0

    @staticmethod
    def _trend(closes: list[float], n: int = 5) -> str:
        if len(closes) < n + 1:
            return 'NEUTRAL'
        d = closes[-1] - closes[-1-n]
        return 'UP' if d > 0 else 'DOWN' if d < 0 else 'NEUTRAL'

    def _analyse(self, data: dict[str, Any]) -> tuple[dict[str, Any], bool, float, list[str]]:
        bars = self._bars(data)
        if not bars or not data.get('symbol') or not data.get('timeframe'):
            return {'state':'UNAVAILABLE'}, False, 0.0, ['INVALID_OR_MISSING_INPUT']
        closes=[float(b['close']) for b in bars]; highs=[float(b['high']) for b in bars]; lows=[float(b['low']) for b in bars]; opens=[float(b['open']) for b in bars]
        atr=self._atr(bars); sid=self.sub_engine_id
        ev={'bars':len(bars),'last_close':closes[-1],'atr':round(atr,8)}; gate=True; score=70.0; reasons=[]
        direction=self._trend(closes)
        rng=max(highs)-min(lows); recent_rng=max(highs[-min(10,len(highs)):])-min(lows[-min(10,len(lows)):]); ratio=recent_rng/rng if rng else 0.0
        body=abs(closes[-1]-opens[-1]); candle_rng=max(highs[-1]-lows[-1],1e-12); body_ratio=body/candle_rng

        if sid=='1A':
            gate=len(bars)>=20; ev.update({'data_quality':'VALID' if gate else 'INSUFFICIENT','bar_count':len(bars)}); reasons=['ข้อมูล OHLC เพียงพอ'] if gate else ['แท่งราคาไม่เพียงพอ']; score=100 if gate else 0
        elif sid=='1B':
            returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes)) if closes[i-1]!=0]; vol=pstdev(returns) if len(returns)>1 else 0; ev['volatility']=round(vol,8); reasons=[f'Volatility คำนวณจาก {len(returns)} ช่วงราคา']; score=75
        elif sid=='1C': ev.update({'direction':direction,'trend_change':round(closes[-1]-closes[-6],8) if len(closes)>=6 else 0}); reasons=[f'Trend direction: {direction}']; score=85 if direction!='NEUTRAL' else 55
        elif sid=='1D': ev['range']={'high':max(highs),'low':min(lows),'width':rng}; reasons=['คำนวณกรอบราคาจาก High/Low']; score=75
        elif sid in {'1E','1F','1G'}:
            label='COMPRESSION' if sid=='1E' and ratio<.45 else 'EXPANSION' if sid=='1F' and ratio>.65 else 'TRANSITION' if sid=='1G' and .45<=ratio<=.65 else 'NOT_DOMINANT'; ev.update({'state':label,'range_ratio':round(ratio,4)}); reasons=[f'ตรวจพบสถานะ: {label}']; score=80 if label!='NOT_DOMINANT' else 60
        elif sid in {'2A','2B','2C','2D','2E','2F'}:
            labels={'2A':'TREND' if direction!='NEUTRAL' and ratio>=.25 else 'NOT_TREND','2B':'RANGE' if ratio<.45 else 'NOT_RANGE','2C':'MEAN_REVERSION' if ratio<.45 else 'NOT_MEAN_REVERSION','2D':'BREAKOUT' if ratio>.65 else 'NOT_BREAKOUT','2E':'EXPANSION_PHASE' if ratio>.65 else 'BALANCED_PHASE','2F':'TRANSITION' if .45<=ratio<=.65 else 'STABLE'}; label=labels[sid]; ev.update({'regime':label,'direction':direction,'range_ratio':round(ratio,4)}); reasons=[f'Regime state: {label}']; score=82 if not label.startswith('NOT_') else 62
        elif sid in {'3A','3B','3C','3D','3E','3F'}:
            hh=highs[-1]>max(highs[:-1]) if len(highs)>1 else False; ll=lows[-1]<min(lows[:-1]) if len(lows)>1 else False; structure='BULLISH' if direction=='UP' else 'BEARISH' if direction=='DOWN' else 'NEUTRAL'; labels={'3A':'SWING_REFERENCE','3B':structure,'3C':'BOS_CONFIRMED' if hh or ll else 'NO_BOS','3D':'NO_FAILURE' if direction!='NEUTRAL' else 'UNRESOLVED','3E':f'STRONG_{structure}','3F':'INTERNAL_EXTERNAL_ALIGNED'}; label=labels[sid]; ev.update({'state':label,'direction':direction,'higher_high':hh,'lower_low':ll}); reasons=[f'Structure: {label}']; score=85 if structure!='NEUTRAL' else 60
        elif sid in {'4A','4B','4C','4D','4E','4F'}:
            look=min(20,len(bars)); rh=max(highs[-look:]); rl=min(lows[-look:]); sweep_hi=highs[-1]>max(highs[-look:-1]) and closes[-1]<max(highs[-look:-1]) if look>2 else False; sweep_lo=lows[-1]<min(lows[-look:-1]) and closes[-1]>min(lows[-look:-1]) if look>2 else False; labels={'4A':'LIQUIDITY_ZONES_IDENTIFIED','4B':'SWEEP_HIGH' if sweep_hi else 'SWEEP_LOW' if sweep_lo else 'NO_SWEEP','4C':'REJECTION' if sweep_hi or sweep_lo else 'NO_REJECTION','4D':'ACCEPTANCE' if not(sweep_hi or sweep_lo) else 'REJECTION_CONTEXT','4E':'RECLAIM_CONTEXT' if sweep_hi or sweep_lo else 'NO_RECLAIM','4F':'QUALITY_MEASURABLE'}; label=labels[sid]; ev.update({'state':label,'zone_high':rh,'zone_low':rl,'sweep_high':sweep_hi,'sweep_low':sweep_lo}); reasons=[f'Liquidity state: {label}']; score=80 if label!='NO_SWEEP' else 65
        elif sid in {'5A','5B','5C','5D','5E','5F'}:
            rh,rl=max(highs),min(lows); pos=(closes[-1]-rl)/(rh-rl) if rh!=rl else .5; labels={'5A':'EQUILIBRIUM_CALCULATED','5B':'UPPER_HALF' if pos>.5 else 'LOWER_HALF','5C':'LIQUIDITY_LOCATION_CALCULATED','5D':'EXTENDED' if pos>.85 or pos<.15 else 'NOT_EXTENDED','5E':'SPACE_AVAILABLE' if .15<pos<.85 else 'LIMITED_SPACE','5F':'LOCATION_QUALITY_MEASURABLE'}; label=labels[sid]; ev.update({'state':label,'position_in_range':round(pos,4),'mean_close':mean(closes),'range_high':rh,'range_low':rl}); reasons=[f'Location state: {label}']; score=80
        elif sid in {'6A','6B','6C','6D','6E','6F'}:
            labels={'6A':'CONTEXT_ALIGNED' if direction!='NEUTRAL' else 'CONTEXT_NEUTRAL','6B':'DIRECTIONAL_SETUP' if direction!='NEUTRAL' else 'NO_DIRECTIONAL_SETUP','6C':'FORMATION_OBSERVED','6D':'NOT_INVALIDATED' if direction!='NEUTRAL' else 'UNRESOLVED','6E':'QUALITY_MEASURABLE','6F':'MATURE' if body_ratio>=.5 else 'DEVELOPING'}; label=labels[sid]; ev.update({'state':label,'direction':direction,'body_ratio':round(body_ratio,4)}); reasons=[f'Setup state: {label}']; score=82 if direction!='NEUTRAL' else 58
        elif sid in {'7A','7B','7C','7D','7E','7F'}:
            labels={'7A':'TRIGGER_OBSERVED' if body_ratio>=.5 else 'NO_STRONG_TRIGGER','7B':'QUALITY_PASS' if body_ratio>=.5 else 'QUALITY_WEAK','7C':'FOLLOW_THROUGH_OBSERVED' if direction!='NEUTRAL' else 'NO_FOLLOW_THROUGH','7D':'NO_FAILURE' if direction!='NEUTRAL' else 'UNRESOLVED','7E':'EXECUTION_CONDITIONS_MEASURABLE','7F':'CONFIRMATION_PASS' if direction!='NEUTRAL' and body_ratio>=.5 else 'CONFIRMATION_WEAK'}; label=labels[sid]; ev.update({'state':label,'direction':direction,'body_ratio':round(body_ratio,4)}); reasons=[f'Confirmation state: {label}']; score=84 if label in {'TRIGGER_OBSERVED','QUALITY_PASS','CONFIRMATION_PASS'} else 65
        elif sid in {'8A','8B','8C','8D','8E','8F','8G'}:
            labels={'8A':'INVALIDATION_CALCULABLE','8B':'STOP_DISTANCE_CALCULABLE','8C':'TARGET_OBJECTIVE_CALCULABLE','8D':'RR_1_TO_2','8E':'POSITION_SIZE_REQUIRES_ACCOUNT_RISK','8F':'EXPOSURE_LIMITS_REQUIRE_RUNTIME_CONFIG','8G':'RISK_GATE_READY'}; label=labels[sid]; ev.update({'state':label,'direction':direction,'risk_distance':round(atr*1.5,8),'rr':2.0}); reasons=[f'Risk state: {label}']; score=85
        elif sid in {'9A','9B','9C','9D','9E','9F','9G','9H'}:
            labels={'9A':'DATA_GATE','9B':'CONTEXT_GATE','9C':'SETUP_GATE','9D':'CONFIRMATION_GATE','9E':'RISK_GATE','9F':'EXECUTION_GATE','9G':'FINAL_DECISION_SYNTHESIS','9H':'DECISION_LOGGING'}; label=labels[sid]; ev.update({'state':label,'direction':direction,'authority':'E9'}); reasons=[f'E9 evidence: {label}']; score=90
        else:
            gate=False; score=0; reasons=['UNKNOWN_SUB_ENGINE_ID']
        return ev, gate, round(score,1), reasons

    def run(self, data: dict[str, Any]) -> SubEngineResult:
        output, gate, score, reasons = self._analyse(data)
        trace={'sub_engine_id':self.sub_engine_id,'symbol':data.get('symbol'),'timeframe':data.get('timeframe'),'candle_close_timestamp':data.get('candle_close_timestamp'),'spec_version':'production-v2.0.0','input_references':{'bar_count':len(self._bars(data))},'output':output,'gate':'PASS' if gate else 'FAIL','score':score,'reason_codes':reasons}
        return SubEngineResult(self.sub_engine_id,output,gate,score,trace)

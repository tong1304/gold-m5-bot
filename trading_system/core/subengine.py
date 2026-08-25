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
    """Shared analytical contract for production-v2 sub-engines.

    Sub-engines describe evidence. They do not decide BUY/SELL. Parent engines
    decide whether evidence is required, optional, waiting, or invalidating.
    Calculations are intentionally short-term/M5 aware and remain asset-neutral.
    """

    def __init__(self, sub_engine_id: str | None = None):
        self.sub_engine_id = sub_engine_id or self._derive_id()

    def _derive_id(self) -> str:
        parts = self.__class__.__module__.split('.')
        engine = next((p[1:] for p in parts if p.startswith('e') and p[1:].isdigit()), '')
        return f"{engine}{parts[-1].split('_', 1)[0].upper()}"

    @staticmethod
    def _bars(data):
        bars = data.get('bars') or []
        return [b for b in bars if isinstance(b, dict) and all(k in b for k in ('open', 'high', 'low', 'close'))]

    @staticmethod
    def _atr(bars):
        trs, prev = [], None
        for b in bars:
            h, l, c = map(float, (b['high'], b['low'], b['close']))
            trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
            prev = c
        return mean(trs) if trs else 0.0

    @staticmethod
    def _trend(closes, n=5):
        if len(closes) < n + 1:
            return 'NEUTRAL'
        d = closes[-1] - closes[-1 - n]
        return 'UP' if d > 0 else 'DOWN' if d < 0 else 'NEUTRAL'

    def _analyse(self, data):
        bars = self._bars(data)
        if not bars or not data.get('symbol') or not data.get('timeframe'):
            return {'state': 'UNAVAILABLE'}, False, 0.0, ['INVALID_OR_MISSING_INPUT']

        closes = [float(b['close']) for b in bars]
        highs = [float(b['high']) for b in bars]
        lows = [float(b['low']) for b in bars]
        opens = [float(b['open']) for b in bars]
        atr = self._atr(bars)
        sid = self.sub_engine_id
        direction = self._trend(closes)
        rng = max(highs) - min(lows)
        recent = max(highs[-min(10, len(highs)):]) - min(lows[-min(10, len(lows)):])
        ratio = recent / rng if rng else 0.0
        body = abs(closes[-1] - opens[-1])
        candle_range = max(highs[-1] - lows[-1], 1e-12)
        body_ratio = body / candle_range
        ev = {'bars': len(bars), 'last_close': closes[-1], 'atr': round(atr, 8)}
        gate = True
        score = 70.0
        reasons = []

        if sid == '1A':
            ev.update({'data_quality': 'VALID', 'bar_count': len(bars)})
            reasons = ['OHLC data valid']
            score = 100
        elif sid == '1B':
            rs = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1] != 0]
            ev['volatility'] = round(pstdev(rs) if len(rs) > 1 else 0, 8)
            reasons = ['volatility state calculated']
            score = 75
        elif sid == '1C':
            change = closes[-1] - closes[-6] if len(closes) >= 6 else 0
            ev.update({'direction': direction, 'trend_change': round(change, 8), 'trend_strength_atr': round(abs(change) / atr, 3) if atr else 0})
            reasons = [f'trend state: {direction}']
            score = 85 if direction != 'NEUTRAL' else 55
        elif sid == '1D':
            ev['range'] = {'high': max(highs), 'low': min(lows), 'width': rng}
            reasons = ['range state calculated']
            score = 75
        elif sid == '1E':
            label = 'COMPRESSION' if ratio < .45 else 'NOT_DOMINANT'
            ev.update({'state': label, 'range_ratio': round(ratio, 4)})
            reasons = [f'volatility state: {label}']
            score = 80 if label == 'COMPRESSION' else 60
        elif sid == '1F':
            label = 'EXPANSION' if ratio > .65 else 'NOT_DOMINANT'
            ev.update({'state': label, 'range_ratio': round(ratio, 4)})
            reasons = [f'volatility state: {label}']
            score = 80 if label == 'EXPANSION' else 60
        elif sid == '1G':
            change = abs(closes[-1] - closes[-6]) if len(closes) >= 6 else 0
            strength = change / atr if atr else 0.0
            label = 'DOMINANT' if direction != 'NEUTRAL' and ratio >= .55 and strength >= .50 else 'TRANSITION' if .45 <= ratio < .55 else 'NOT_DOMINANT'
            ev.update({'state': label, 'range_ratio': round(ratio, 4), 'trend_strength_atr': round(strength, 3), 'direction': direction})
            reasons = [f'market dominance: {label}']
            score = 90 if label == 'DOMINANT' else 65 if label == 'TRANSITION' else 55
        elif sid in {'2A', '2B', '2C', '2D', '2E', '2F'}:
            labels = {
                '2A': 'TREND' if direction != 'NEUTRAL' and ratio >= .25 else 'NOT_TREND',
                '2B': 'RANGE' if ratio < .45 else 'NOT_RANGE',
                '2C': 'MEAN_REVERSION' if ratio < .45 else 'NOT_MEAN_REVERSION',
                '2D': 'BREAKOUT' if ratio > .65 else 'NOT_BREAKOUT',
                '2E': 'EXPANSION_PHASE' if ratio > .65 else 'BALANCED_PHASE',
                '2F': 'TRANSITION' if .45 <= ratio <= .65 else 'STABLE',
            }
            label = labels[sid]
            ev.update({'regime': label, 'direction': direction, 'range_ratio': round(ratio, 4)})
            reasons = [f'regime state: {label}']
            score = 82 if not label.startswith('NOT_') else 62
        elif sid in {'3A', '3B', '3C', '3D', '3E', '3F'}:
            hh = highs[-1] > max(highs[:-1]) if len(highs) > 1 else False
            ll = lows[-1] < min(lows[:-1]) if len(lows) > 1 else False
            structure = 'BULLISH' if direction == 'UP' else 'BEARISH' if direction == 'DOWN' else 'NEUTRAL'
            labels = {
                '3A': 'SWING_REFERENCE',
                '3B': structure,
                '3C': 'BOS_CONFIRMED' if hh or ll else 'NO_BOS',
                '3D': 'NO_FAILURE' if direction != 'NEUTRAL' else 'UNRESOLVED',
                '3E': f'STRONG_{structure}',
                '3F': 'INTERNAL_EXTERNAL_ALIGNED' if direction != 'NEUTRAL' else 'INTERNAL_EXTERNAL_MIXED',
            }
            label = labels[sid]
            ev.update({'state': label, 'direction': direction, 'higher_high': hh, 'lower_low': ll})
            reasons = [f'structure evidence: {label}']
            score = 85 if structure != 'NEUTRAL' else 60
        elif sid in {'4A', '4B', '4C', '4D', '4E', '4F'}:
            look = min(20, len(bars))
            rh, rl = max(highs[-look:]), min(lows[-look:])
            shi = look > 2 and highs[-1] > max(highs[-look:-1]) and closes[-1] < max(highs[-look:-1])
            slo = look > 2 and lows[-1] < min(lows[-look:-1]) and closes[-1] > min(lows[-look:-1])
            labels = {
                '4A': 'LIQUIDITY_ZONES_IDENTIFIED',
                '4B': 'SWEEP_HIGH' if shi else 'SWEEP_LOW' if slo else 'NO_SWEEP',
                '4C': 'REJECTION' if shi or slo else 'NO_REJECTION',
                '4D': 'ACCEPTANCE' if not (shi or slo) else 'REJECTION_CONTEXT',
                '4E': 'RECLAIM_CONTEXT' if shi or slo else 'NO_RECLAIM',
                '4F': 'QUALITY_MEASURABLE',
            }
            label = labels[sid]
            ev.update({'state': label, 'zone_high': rh, 'zone_low': rl, 'sweep_high': shi, 'sweep_low': slo})
            reasons = [f'liquidity evidence: {label}']
            score = 85 if label in {'SWEEP_HIGH', 'SWEEP_LOW', 'REJECTION', 'RECLAIM_CONTEXT'} else 72
        elif sid in {'5A', '5B', '5C', '5D', '5E', '5F'}:
            rh, rl = max(highs), min(lows)
            pos = (closes[-1] - rl) / (rh - rl) if rh != rl else .5
            labels = {
                '5A': 'EQUILIBRIUM_CALCULATED',
                '5B': 'UPPER_HALF' if pos > .5 else 'LOWER_HALF',
                '5C': 'LIQUIDITY_LOCATION_CALCULATED',
                '5D': 'EXTENDED' if pos > .85 or pos < .15 else 'NOT_EXTENDED',
                '5E': 'SPACE_AVAILABLE' if .15 < pos < .85 else 'LIMITED_SPACE',
                '5F': 'LOCATION_QUALITY_MEASURABLE',
            }
            label = labels[sid]
            ev.update({'state': label, 'position_in_range': round(pos, 4), 'mean_close': mean(closes), 'range_high': rh, 'range_low': rl})
            reasons = [f'location evidence: {label}']
            score = 90 if .20 <= pos <= .80 and label not in {'EXTENDED', 'LIMITED_SPACE'} else 75
        elif sid in {'6A', '6B', '6C', '6D', '6E', '6F'}:
            regime = data.get('E2_result', {}).get('2B', {}).get('regime') or data.get('E2_result', {}).get('2C', {}).get('regime')
            if direction != 'NEUTRAL':
                archetype = 'DIRECTIONAL_SETUP'
            elif regime == 'RANGE':
                archetype = 'RANGE_REJECTION_SETUP'
            elif regime == 'MEAN_REVERSION':
                archetype = 'MEAN_REVERSION_SETUP'
            else:
                archetype = 'BREAKOUT_SETUP' if ratio > .65 else 'LIQUIDITY_REVERSAL_SETUP'
            labels = {
                '6A': 'CONTEXT_ALIGNED' if direction != 'NEUTRAL' or regime in {'RANGE', 'MEAN_REVERSION'} else 'CONTEXT_NEUTRAL',
                '6B': archetype,
                '6C': 'FORMATION_OBSERVED',
                '6D': 'NOT_INVALIDATED',
                '6E': 'QUALITY_MEASURABLE',
                '6F': 'MATURE' if body_ratio >= .5 else 'DEVELOPING',
            }
            label = labels[sid]
            ev.update({'state': label, 'direction': direction, 'body_ratio': round(body_ratio, 4), 'archetype': archetype})
            reasons = [f'setup evidence: {label}']
            score = 86 if label == 'MATURE' else 68
        elif sid in {'7A', '7B', '7C', '7D', '7E', '7F'}:
            labels = {
                '7A': 'TRIGGER_OBSERVED' if body_ratio >= .5 else 'NO_STRONG_TRIGGER',
                '7B': 'QUALITY_PASS' if body_ratio >= .5 else 'QUALITY_WEAK',
                '7C': 'FOLLOW_THROUGH_OBSERVED' if direction != 'NEUTRAL' else 'NO_FOLLOW_THROUGH',
                '7D': 'NO_FAILURE' if direction != 'NEUTRAL' else 'UNRESOLVED',
                '7E': 'EXECUTION_CONDITIONS_MEASURABLE',
                '7F': 'CONFIRMATION_PASS' if body_ratio >= .5 and (direction != 'NEUTRAL' or data.get('E2_result', {}).get('2B', {}).get('regime') == 'RANGE') else 'CONFIRMATION_WEAK',
            }
            label = labels[sid]
            ev.update({'state': label, 'direction': direction, 'body_ratio': round(body_ratio, 4)})
            reasons = [f'confirmation evidence: {label}']
            score = 88 if label in {'TRIGGER_OBSERVED', 'QUALITY_PASS', 'CONFIRMATION_PASS'} else 65
        elif sid in {'8A', '8B', '8C', '8D', '8E', '8F', '8G'}:
            labels = {'8A': 'INVALIDATION_CALCULABLE', '8B': 'STOP_DISTANCE_CALCULABLE', '8C': 'TARGET_OBJECTIVE_CALCULABLE', '8D': 'RR_CONFIGURABLE', '8E': 'POSITION_SIZE_REQUIRES_ACCOUNT_RISK', '8F': 'EXPOSURE_LIMITS_REQUIRE_RUNTIME_CONFIG', '8G': 'RISK_GATE_READY'}
            label = labels[sid]
            ev.update({'state': label, 'direction': direction, 'risk_distance': round(atr * 1.5, 8)})
            reasons = [f'risk evidence: {label}']
            score = 85
        elif sid in {'9A', '9B', '9C', '9D', '9E', '9F', '9G', '9H'}:
            label = {'9A': 'DATA_GATE', '9B': 'CONTEXT_GATE', '9C': 'SETUP_GATE', '9D': 'CONFIRMATION_GATE', '9E': 'RISK_GATE', '9F': 'EXECUTION_GATE', '9G': 'FINAL_DECISION_SYNTHESIS', '9H': 'DECISION_LOGGING'}[sid]
            ev.update({'state': label, 'direction': direction, 'authority': 'E9'})
            reasons = [f'E9 evidence: {label}']
            score = 90
        else:
            gate, score, reasons = False, 0, ['UNKNOWN_SUB_ENGINE_ID']

        return ev, gate, round(score, 1), reasons

    def run(self, data):
        output, gate, score, reasons = self._analyse(data)
        trace = {
            'sub_engine_id': self.sub_engine_id,
            'symbol': data.get('symbol'),
            'timeframe': data.get('timeframe'),
            'candle_close_timestamp': data.get('candle_close_timestamp'),
            'spec_version': 'production-v2.1.0-professional-m5',
            'input_references': {'bar_count': len(self._bars(data))},
            'output': output,
            'gate': 'PASS' if gate else 'FAIL',
            'score': score,
            'reason_codes': reasons,
        }
        return SubEngineResult(self.sub_engine_id, output, gate, score, trace)

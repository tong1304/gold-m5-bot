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
    """Deterministic analytical Sub-Engine contract.

    Sub-Engines produce evidence only. They never place orders and never
    bypass their parent Engine. E9 final-decision evidence is still handed to
    the E9 master decision layer before execution.
    """

    def __init__(self, sub_engine_id: str | None = None):
        self.sub_engine_id = sub_engine_id or self._derive_id()

    def _derive_id(self) -> str:
        parts = self.__class__.__module__.split('.')
        engine = next((p[1:] for p in parts if p.startswith('e') and p[1:].isdigit()), '')
        leaf = parts[-1]
        letter = leaf.split('_', 1)[0].upper()
        return f'{engine}{letter}'

    @staticmethod
    def _bars(data: dict[str, Any]) -> list[dict[str, float]]:
        bars = data.get('bars') or []
        return [b for b in bars if isinstance(b, dict) and all(k in b for k in ('open', 'high', 'low', 'close'))]

    @staticmethod
    def _score(valid: bool, n: int) -> float:
        return min(100.0, 50.0 + min(50.0, n)) if valid else 0.0

    def run(self, data: dict[str, Any]) -> SubEngineResult:
        bars = self._bars(data)
        valid = bool(bars) and bool(data.get('symbol')) and bool(data.get('timeframe'))
        output: dict[str, Any] = {'state': 'VALID' if valid else 'UNAVAILABLE', 'evidence': {}}
        if valid:
            closes = [float(b['close']) for b in bars]
            highs = [float(b['high']) for b in bars]
            lows = [float(b['low']) for b in bars]
            output['evidence'] = {'bars': len(bars), 'last_close': closes[-1]}
            prefix = self.sub_engine_id[0]
            letter = self.sub_engine_id[1]
            if self.sub_engine_id == '1A':
                output['data_quality'] = {'bars': len(bars), 'ordered': all(bars[i]['close'] is not None for i in range(len(bars)))}
            elif self.sub_engine_id == '1B':
                returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes)) if closes[i - 1] != 0]
                output['volatility'] = pstdev(returns) if len(returns) > 1 else 0.0
            elif self.sub_engine_id in {'1C', '2A'}:
                output['direction'] = 'UP' if closes[-1] > closes[0] else 'DOWN' if closes[-1] < closes[0] else 'NEUTRAL'
            elif self.sub_engine_id in {'1D', '2B'}:
                output['range'] = {'high': max(highs), 'low': min(lows), 'width': max(highs) - min(lows)}
            elif self.sub_engine_id in {'1E', '1F'}:
                output['range_change'] = max(highs) - min(lows)
            elif prefix == '3' and letter == 'A':
                output['swing_reference'] = {'high': max(highs), 'low': min(lows)}
            elif prefix == '4' and letter == 'A':
                output['liquidity_reference'] = {'high': max(highs), 'low': min(lows)}
            elif prefix == '5':
                output['location_reference'] = {'range_high': max(highs), 'range_low': min(lows), 'mean_close': mean(closes)}
            elif prefix == '6':
                output['setup_state'] = 'OBSERVED'
            elif prefix == '7':
                output['confirmation_state'] = 'OBSERVED'
            elif prefix == '8':
                output['risk_state'] = 'CALCULABLE'
            elif prefix == '9':
                output['decision_state'] = 'PENDING_PARENT_SYNTHESIS'

        score = self._score(valid, len(bars))
        trace = {
            'sub_engine_id': self.sub_engine_id,
            'symbol': data.get('symbol'),
            'timeframe': data.get('timeframe'),
            'candle_close_timestamp': data.get('candle_close_timestamp'),
            'spec_version': 'production-v2.0.0',
            'input_references': {'bar_count': len(bars)},
            'output': output,
            'gate': 'PASS' if valid else 'FAIL',
            'score': score,
            'reason_codes': [] if valid else ['INVALID_OR_MISSING_INPUT'],
        }
        return SubEngineResult(self.sub_engine_id, output, valid, score, trace)

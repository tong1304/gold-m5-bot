from production_v2.e3_brain import (
    UP, DOWN, MIXED, NEUTRAL,
    _resolve_structure, _protected_structure, _current_break,
    _lifecycle, analyze_e3,
)


def swing(i, price, label):
    return {'index': i, 'price': float(price), 'label': label, 'confirmation_index': i + 1}


def make_bars(closes):
    bars = []
    for i, c in enumerate(closes):
        bars.append({'open': c - 0.2, 'high': c + 0.5, 'low': c - 0.5, 'close': c})
    return bars


def wave(*levels):
    out = []
    for level in levels:
        start = out[-1] if out else level
        step = (level - start) / 10.0
        for j in range(10):
            out.append(start + step * (j + 1))
    return out


def test_external_authority_uses_paired_structure_not_counts():
    highs = [swing(20, 110, 'HH'), swing(50, 115, 'HH')]
    lows = [swing(35, 100, 'HL'), swing(65, 105, 'HL')]
    assert _resolve_structure(highs, lows) == UP
    highs.insert(0, swing(5, 120, 'LH'))
    lows.insert(0, swing(10, 90, 'LL'))
    assert _resolve_structure(highs, lows) == UP


def test_external_authority_resolves_bearish_pair():
    highs = [swing(20, 110, 'LH'), swing(50, 105, 'LH')]
    lows = [swing(35, 100, 'LL'), swing(65, 95, 'LL')]
    assert _resolve_structure(highs, lows) == DOWN


def test_conflict_is_explicit_and_not_count_authority():
    external = [swing(20, 110, 'HH'), swing(50, 115, 'HH')]
    lows = [swing(35, 100, 'HL'), swing(65, 105, 'HL')]
    assert _resolve_structure(external, lows) == UP
    internal = [swing(70, 114, 'LH'), swing(80, 108, 'LL')]
    assert _resolve_structure(internal, lows[-2:]) == DOWN


def test_protected_structure_and_invalidation_anchor():
    highs = [swing(20, 110, 'HH'), swing(50, 115, 'HH')]
    lows = [swing(35, 100, 'HL'), swing(65, 105, 'HL')]
    p = _protected_structure(UP, highs, lows)
    assert p['primary_direction'] == UP
    assert p['primary_label'] == 'HL'
    assert p['invalidation_level'] == 100.0
    assert p['invalidation_type'] == 'CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW'


def test_closed_candle_bos_only():
    highs = [swing(20, 110, 'HH')]
    lows = [swing(35, 100, 'HL')]
    bars = make_bars([105] * 40 + [111])
    e = _current_break(bars, highs, lows, atr=2.0, structure=UP, idx=len(bars)-1)
    assert e['confirmed'] is True
    assert e['closed_candle_confirmed'] is True
    assert e['direction'] == UP


def test_lifecycle_failure_is_terminal():
    current = {'confirmed': False, 'event': 'NO_BOS', 'direction': NEUTRAL}
    failure = {'confirmed': True, 'direction': DOWN, 'level': 110.0, 'break_candle_index': 40, 'failure_candle_index': 43}
    life = _lifecycle(current, failure, [], None, 50)
    assert life['stage'] == 'FAILED'
    assert life['terminal'] is True
    assert life['failure'] is True
    assert life['current'] is False


def test_real_scenario_analysis_returns_complete_e3_without_upstream_dependency():
    closes = []
    for a, b in [(100, 110), (110, 102), (102, 108), (108, 98), (98, 105), (105, 94), (94, 99)]:
        closes.extend(wave(a, b))
    result = analyze_e3(make_bars(closes))
    assert result['analysis_status'] == 'COMPLETE'
    assert result['reasoning_trace']['upstream_inputs_used'] is False
    assert result['reasoning_trace']['external_is_authority'] is True, result
    assert result['reasoning_trace']['closed_candle_only'] is True
    assert 'count_state_role=DESCRIPTIVE_NOT_AUTHORITY' in result['evidence']
    assert result['decision_authority'] == 'E9_ONLY'


def test_insufficient_data_is_safe():
    result = analyze_e3(make_bars([100] * 10))
    assert result['analysis_status'] == 'INCOMPLETE'
    assert result['direction'] == NEUTRAL


def test_professional_schema_separates_current_and_historical_breaks():
    result = analyze_e3(make_bars([100] * 60))
    assert 'current_break' in result
    assert 'historical_break' in result
    assert result['current_break']['stage'] in {'NONE', 'CONFIRMED', 'ACCEPTED', 'FAILED'}
    assert result['historical_break']['stage'] in {'NONE', 'ACCEPTED', 'FAILED'}


def test_professional_schema_separates_current_and_historical_liquidity():
    result = analyze_e3(make_bars([100] * 60))
    assert 'current_liquidity' in result
    assert 'historical_liquidity' in result
    assert result['current_liquidity']['stage'] in {'NONE', 'SWEEP', 'RECLAIM'}
    assert result['historical_liquidity']['stage'] in {'NONE', 'SWEEP_RECLAIM'}

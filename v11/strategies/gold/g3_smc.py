from __future__ import annotations

from typing import Any

import pandas as pd

from ...common import atr14, candle_metrics, num
from ...contracts import StrategyResult


STRATEGY = "G3_LIQUIDITY_SWEEP_CHOCH"
SWEEP_LOOKBACK = 10
CHOCH_LOOKAHEAD = 4
EQUAL_LEVEL_ATR = 0.20
MIN_BODY_RATIO = 0.45
MIN_MOMENTUM_ATR = 0.50
SL_BUFFER_ATR = 0.15


def _x(m5):
    return m5.tail(100).reset_index(drop=True).copy()


def _atr(x):
    values = atr14(x).dropna()
    if len(values):
        return max(num(values.iloc[-1]), 1e-9)
    return max(num((x.high - x.low).tail(14).mean()), 1e-9)


def _pivots(x):
    highs, lows = [], []
    for i in range(2, len(x) - 2):
        h = num(x.high.iloc[i])
        l = num(x.low.iloc[i])
        if h >= max(num(v) for v in x.high.iloc[i - 2 : i + 3]):
            highs.append((i, h))
        if l <= min(num(v) for v in x.low.iloc[i - 2 : i + 3]):
            lows.append((i, l))
    return highs, lows


def _context_level(context: dict[str, Any], names: tuple[str, ...]):
    for name in names:
        value = context.get(name)
        if value is not None:
            try:
                return float(value), name
            except (TypeError, ValueError):
                pass
    return None, None


def _equal_level(pivots, atr, direction):
    values = pivots if direction == "BUY" else pivots
    if len(values) < 2:
        return None, None
    # Most recent repeated liquidity pool wins; require two pivots close enough
    # to be meaningfully equal on M5 rather than treating every swing as liquidity.
    for j in range(len(values) - 1, 0, -1):
        level_j = values[j][1]
        for k in range(j - 1, -1, -1):
            level_k = values[k][1]
            if abs(level_j - level_k) <= EQUAL_LEVEL_ATR * atr:
                return (level_j + level_k) / 2.0, "EQL" if direction == "BUY" else "EQH"
    return None, None


def _htf_aligned(direction, context):
    context = context or {}
    m15 = context.get("m15") or {}
    h1 = str(context.get("h1_bias") or "NEUTRAL").upper()
    m15_direction = str(m15.get("direction") or "NEUTRAL").upper()
    poi = context.get("poi") or m15.get("poi") or context.get("h1_poi")

    if poi:
        if isinstance(poi, dict):
            poi_direction = str(poi.get("direction") or "").upper()
            if poi_direction in (direction, "NEUTRAL"):
                return True
        elif poi is True:
            return True
        elif str(poi).upper() == direction:
            return True

    directional = [v for v in (h1, m15_direction) if v in ("BUY", "SELL")]
    if not directional:
        return False
    return all(v == direction for v in directional)


def _find_sweep(x, direction, level, atr):
    start = max(0, len(x) - SWEEP_LOOKBACK)
    for i in range(start, len(x) - 1):
        c = candle_metrics(x.iloc[i])
        if direction == "BUY":
            ok = (
                c["low"] < level - 0.05 * atr
                and c["close"] > level
                and c["lower_wick"] >= max(c["body"], 0.15 * atr)
            )
        else:
            ok = (
                c["high"] > level + 0.05 * atr
                and c["close"] < level
                and c["upper_wick"] >= max(c["body"], 0.15 * atr)
            )
        if ok:
            return i, c
    return None, None


def _find_choch(x, direction, sweep_index, protected_level, atr):
    end = min(len(x), sweep_index + 1 + CHOCH_LOOKAHEAD)
    for i in range(sweep_index + 1, end):
        c = candle_metrics(x.iloc[i])
        momentum = c["body"] / max(atr, 1e-9)
        if direction == "BUY":
            ok = c["bull"] and c["body_ratio"] >= MIN_BODY_RATIO and momentum >= MIN_MOMENTUM_ATR and c["close"] > protected_level
        else:
            ok = c["bear"] and c["body_ratio"] >= MIN_BODY_RATIO and momentum >= MIN_MOMENTUM_ATR and c["close"] < protected_level
        if ok:
            return i, c
    return None, None


def _find_fvg(x, direction, choch_index):
    end = min(len(x), choch_index + 2)
    for i in range(choch_index, end):
        if i < 2:
            continue
        left = candle_metrics(x.iloc[i - 2])
        right = candle_metrics(x.iloc[i])
        if direction == "BUY" and right["low"] > left["high"]:
            return i, left["high"], right["low"], (left["high"] + right["low"]) / 2.0
        if direction == "SELL" and right["high"] < left["low"]:
            return i, right["high"], left["low"], (right["high"] + left["low"]) / 2.0
    return None, None, None, None


def _find_order_block(x, direction, sweep_index, choch_index):
    # Last opposite candle before the displacement is the M5 OB.
    for i in range(choch_index - 1, sweep_index - 1, -1):
        c = candle_metrics(x.iloc[i])
        if direction == "BUY" and c["bear"]:
            return i, c["low"], c["high"], c["open"]
        if direction == "SELL" and c["bull"]:
            return i, c["low"], c["high"], c["open"]
    return None, None, None, None


def evaluate(m5, direction, context=None):
    direction = str(direction).upper()
    context = context or {}
    x = _x(m5)
    reasons = []
    if direction not in ("BUY", "SELL"):
        return StrategyResult.fail(STRATEGY, direction, ["INVALID_DIRECTION"])
    if len(x) < 40:
        return StrategyResult.fail(STRATEGY, direction, ["INSUFFICIENT_M5_BARS"])

    atr = _atr(x)
    highs, lows = _pivots(x)
    if direction == "BUY":
        pool_pivots = lows
        opposite_pivots = highs
        context_level, context_name = _context_level(context, ("session_low", "previous_day_low", "pd_low"))
    else:
        pool_pivots = highs
        opposite_pivots = lows
        context_level, context_name = _context_level(context, ("session_high", "previous_day_high", "pd_high"))

    if context_level is not None:
        liquidity_level, liquidity_type = context_level, context_name.upper()
    else:
        liquidity_level, liquidity_type = _equal_level(pool_pivots, atr, direction)

    if liquidity_level is None:
        return StrategyResult.fail(STRATEGY, direction, ["NO_EQUAL_OR_SESSION_LIQUIDITY"])

    if not _htf_aligned(direction, context):
        return StrategyResult.fail(STRATEGY, direction, ["HTF_ALIGNMENT_FAILED"], {"liquidity_level": liquidity_level})

    sweep_index, sweep = _find_sweep(x, direction, liquidity_level, atr)
    if sweep_index is None:
        return StrategyResult.fail(STRATEGY, direction, ["LIQUIDITY_SWEEP_NOT_CONFIRMED"], {"liquidity_level": liquidity_level, "liquidity_type": liquidity_type})

    protected = [(i, v) for i, v in opposite_pivots if i < sweep_index]
    if not protected:
        return StrategyResult.fail(STRATEGY, direction, ["NO_PROTECTED_SWING_FOR_CHOCH"], {"sweep_index": sweep_index})
    protected_index, protected_level = protected[-1]

    choch_index, choch = _find_choch(x, direction, sweep_index, protected_level, atr)
    if choch_index is None:
        return StrategyResult.fail(STRATEGY, direction, ["CHOCH_NOT_CONFIRMED"], {"sweep_index": sweep_index, "protected_swing": protected_level})

    fvg_index, fvg_low, fvg_high, fvg_mid = _find_fvg(x, direction, choch_index)
    if fvg_index is None:
        return StrategyResult.fail(STRATEGY, direction, ["NO_FVG_AFTER_CHOCH"], {"sweep_index": sweep_index, "choch_index": choch_index, "choch_level": protected_level})

    ob_index, ob_low, ob_high, ob_edge = _find_order_block(x, direction, sweep_index, choch_index)
    if ob_index is None:
        return StrategyResult.fail(STRATEGY, direction, ["NO_M5_ORDER_BLOCK"], {"sweep_index": sweep_index, "choch_index": choch_index})

    entry = fvg_mid
    if direction == "BUY":
        sl = sweep["low"] - SL_BUFFER_ATR * atr
        tp1 = protected_level
        future_highs = [v for i, v in opposite_pivots if i > choch_index and v > entry]
        tp2 = max(future_highs) if future_highs else None
        if tp1 <= entry:
            return StrategyResult.fail(STRATEGY, direction, ["TP1_NOT_ABOVE_ENTRY"])
    else:
        sl = sweep["high"] + SL_BUFFER_ATR * atr
        tp1 = protected_level
        future_lows = [v for i, v in opposite_pivots if i > choch_index and v < entry]
        tp2 = min(future_lows) if future_lows else None
        if tp1 >= entry:
            return StrategyResult.fail(STRATEGY, direction, ["TP1_NOT_BELOW_ENTRY"])

    risk = abs(entry - sl)
    if risk <= 0:
        return StrategyResult.fail(STRATEGY, direction, ["INVALID_RISK_DISTANCE"])

    reward = abs(tp1 - entry)
    rr = reward / risk
    if rr < 1.20:
        return StrategyResult.fail(STRATEGY, direction, ["RR_BELOW_MINIMUM"], {"entry": entry, "sl": sl, "tp1": tp1, "rr": rr})

    evidence = {
        "liquidity_type": liquidity_type,
        "liquidity_level": liquidity_level,
        "sweep_confirmed": True,
        "sweep_index": sweep_index,
        "sweep_low": sweep["low"],
        "sweep_high": sweep["high"],
        "choch_confirmed": True,
        "choch_index": choch_index,
        "choch_level": protected_level,
        "fvg_confirmed": True,
        "fvg_index": fvg_index,
        "fvg_low": fvg_low,
        "fvg_high": fvg_high,
        "fvg_mid": fvg_mid,
        "ob_index": ob_index,
        "ob_low": ob_low,
        "ob_high": ob_high,
        "ob_entry_edge": ob_edge,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk_reward_tp1": rr,
        "atr": atr,
        "htf_h1_bias": context.get("h1_bias", "NEUTRAL"),
        "htf_m15_direction": (context.get("m15") or {}).get("direction", "NEUTRAL"),
    }
    return StrategyResult.pass_(STRATEGY, direction, evidence, quality=95.0, freshness_bars=max(0, len(x) - 1 - fvg_index))

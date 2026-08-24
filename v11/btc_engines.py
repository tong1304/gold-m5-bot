from __future__ import annotations

import math
import pandas as pd

from .common import atr14, candle_metrics

BTC_ENGINE_NAMES = {
    "B1": "RANGE_SWEEP_DISPLACEMENT",
    "B2": "HTF_ZONE_M5_FVG_RETEST",
    "B3": "VOLATILITY_EXPANSION_BREAKOUT_RETEST",
}

BTC_ENGINE_PRIORITY = {"B1": 0, "B2": 1, "B3": 2}
BTC_POINT_BUFFER = 125.0
BTC_FVG_MIN_POINTS = 100.0
BTC_MIN_BODY_RATIO = 0.55


def _num(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _body(c):
    return abs(_num(c.close) - _num(c.open))


def _range(c):
    return max(_num(c.high) - _num(c.low), 1e-12)


def _bull(c):
    return _num(c.close) > _num(c.open)


def _bear(c):
    return _num(c.close) < _num(c.open)


def _reversal_bull(x):
    if len(x) < 2:
        return False
    a, b = x.iloc[-1], x.iloc[-2]
    body = _body(a)
    lower = min(_num(a.open), _num(a.close)) - _num(a.low)
    engulf = _bull(a) and _bear(b) and _num(a.open) <= _num(b.close) and _num(a.close) >= _num(b.open)
    pin = _bull(a) and lower >= max(body * 1.5, _range(a) * 0.45) and (_num(a.close) - _num(a.low)) / _range(a) >= 0.65
    return engulf or pin


def _reversal_bear(x):
    if len(x) < 2:
        return False
    a, b = x.iloc[-1], x.iloc[-2]
    body = _body(a)
    upper = _num(a.high) - max(_num(a.open), _num(a.close))
    engulf = _bear(a) and _bull(b) and _num(a.open) >= _num(b.close) and _num(a.close) <= _num(b.open)
    pin = _bear(a) and upper >= max(body * 1.5, _range(a) * 0.45) and (_num(a.close) - _num(a.low)) / _range(a) <= 0.35
    return engulf or pin


def _avg_body(x, period=20):
    return sum(_body(r) for _, r in x.tail(period).iterrows()) / max(min(period, len(x)), 1)


def _volume_ratio(x, period=20):
    v = pd.to_numeric(x.get("volume", pd.Series(1.0, index=x.index)), errors="coerce").fillna(1.0)
    avg = _num(v.tail(period).mean(), 1.0)
    return _num(v.iloc[-1]) / max(avg, 1e-12)


def _atr(x):
    a = atr14(x).dropna()
    return _num(a.iloc[-1]) if len(a) else _num((x.high - x.low).tail(14).mean(), 1.0)


def _fvg(x, direction, min_points=BTC_FVG_MIN_POINTS):
    if len(x) < 3:
        return None
    a = x.iloc[-1]
    c = x.iloc[-3]
    if direction == "BUY":
        bottom = _num(c.high)
        top = _num(a.low)
        if top - bottom >= min_points:
            return {"bottom": bottom, "top": top, "width": top - bottom, "type": "BULLISH_FVG"}
    else:
        bottom = _num(a.high)
        top = _num(c.low)
        if top - bottom >= min_points:
            return {"bottom": bottom, "top": top, "width": top - bottom, "type": "BEARISH_FVG"}
    return None


def _recent_fvg(x, direction, lookback=8, min_points=BTC_FVG_MIN_POINTS):
    z = x.tail(lookback).reset_index(drop=True)
    for i in range(len(z) - 1, 1, -1):
        f = _fvg(z.iloc[: i + 1], direction, min_points)
        if f:
            return f
    return None


def _range(x, lookback=20):
    z = x.iloc[-lookback-1:-1] if len(x) > lookback else x.iloc[:-1]
    return (_num(z.high.max()), _num(z.low.min()))


def _swing(x, direction, lookback=8):
    z = x.iloc[-lookback-1:-1] if len(x) > lookback else x.iloc[:-1]
    if z.empty:
        return None
    return _num(z.high.max()) if direction == "BUY" else _num(z.low.min())


def _result(eid, direction, anchor, evidence, quality, trigger, entry_type="MARKET"):
    return {
        "status": "PASS",
        "engine": eid,
        "strategy": BTC_ENGINE_NAMES[eid],
        "direction": direction,
        "setup_anchor": anchor,
        "evidence": evidence,
        "quality": float(max(0, min(100, quality))),
        "trigger_signature": trigger,
        "entry_type_hint": entry_type,
        "rejection_reasons": [],
    }


def _fail(eid, direction, reason):
    return {
        "status": "FAIL",
        "engine": eid,
        "strategy": BTC_ENGINE_NAMES[eid],
        "direction": direction,
        "quality": 0.0,
        "rejection_reasons": [reason],
    }


def _htf_zone(frame, direction, lookback=40):
    if frame is None or len(frame) < 8:
        return None
    x = frame.tail(lookback).reset_index(drop=True)
    avg = _avg_body(x, min(20, len(x)))
    for i in range(len(x) - 2, 1, -1):
        c = x.iloc[i]
        nxt = x.iloc[i + 1]
        if direction == "BUY" and _bear(c) and _body(nxt) >= avg * 1.5 and _bull(nxt):
            return {"low": _num(c.low), "high": _num(c.open), "source": "BULLISH_OB"}
        if direction == "SELL" and _bull(c) and _body(nxt) >= avg * 1.5 and _bear(nxt):
            return {"low": _num(c.open), "high": _num(c.high), "source": "BEARISH_OB"}
    return None


def _zone_touched(frame, zone):
    if frame is None or not zone or frame.empty:
        return False
    c = frame.iloc[-1]
    return _num(c.low) <= zone["high"] and _num(c.high) >= zone["low"]


def _evaluate_b1(x, direction):
    if len(x) < 25:
        return _fail("B1", direction, "INSUFFICIENT_M5_CONTEXT")
    rh, rl = _range(x, 20)
    a = _atr(x)
    avg = _avg_body(x.iloc[:-1], min(20, len(x) - 1))
    current = x.iloc[-1]
    sweep_low = _num(current.low) if direction == "BUY" else None
    sweep_high = _num(current.high) if direction == "SELL" else None
    if direction == "BUY":
        swept = sweep_low < rl and _num(current.close) > rl
        swing = _swing(x, "BUY", 8)
        displacement = _num(current.close) > swing and _body(current) >= avg * 1.5 and _bull(current)
        fvg = _recent_fvg(x, "BUY")
        if swept and displacement and fvg:
            entry = fvg["top"]
            sl = sweep_low - BTC_POINT_BUFFER
            risk = entry - sl
            if risk > 0:
                tp = max(rh, entry + risk * 1.5)
                return _result("B1", direction, rl, {"range_high": rh, "range_low": rl, "sweep_low": sweep_low, "swing_high": swing, "fvg": fvg, "entry_price": entry, "sl_price": sl, "tp_price": tp, "risk_reward": (tp-entry)/risk, "point_buffer": BTC_POINT_BUFFER}, 94, f"B1|range-sweep-displacement|BUY|{entry}", "BUY_LIMIT")
    else:
        swept = sweep_high > rh and _num(current.close) < rh
        swing = _swing(x, "SELL", 8)
        displacement = _num(current.close) < swing and _body(current) >= avg * 1.5 and _bear(current)
        fvg = _recent_fvg(x, "SELL")
        if swept and displacement and fvg:
            entry = fvg["bottom"]
            sl = sweep_high + BTC_POINT_BUFFER
            risk = sl - entry
            if risk > 0:
                tp = min(rl, entry - risk * 1.5)
                return _result("B1", direction, rh, {"range_high": rh, "range_low": rl, "sweep_high": sweep_high, "swing_low": swing, "fvg": fvg, "entry_price": entry, "sl_price": sl, "tp_price": tp, "risk_reward": (entry-tp)/risk, "point_buffer": BTC_POINT_BUFFER}, 94, f"B1|range-sweep-displacement|SELL|{entry}", "SELL_LIMIT")
    return _fail("B1", direction, "RANGE_SWEEP_DISPLACEMENT_FAILED")


def _evaluate_b2(x, m15, h1, direction):
    if len(x) < 30:
        return _fail("B2", direction, "INSUFFICIENT_M5_CONTEXT")
    zone15 = _htf_zone(m15, direction)
    zone1 = _htf_zone(h1, direction)
    touched15 = _zone_touched(m15, zone15)
    touched1 = _zone_touched(h1, zone1)
    if not (touched15 or touched1):
        return _fail("B2", direction, "HTF_OB_DEMAND_SUPPLY_NOT_TOUCHED")
    swing = _swing(x, direction, 8)
    current = x.iloc[-1]
    if direction == "BUY":
        choch = _num(current.close) > _num(swing)
        fvg = _recent_fvg(x, "BUY")
        retest = _num(current.low) <= fvg["top"] if fvg else False
        confirm = _reversal_bull(x)
        if choch and fvg and fvg["width"] >= BTC_FVG_MIN_POINTS and retest and confirm:
            entry = _num(current.close)
            sl = _num(swing) - BTC_POINT_BUFFER
            tp = entry + abs(entry-sl) * 2.0
            return _result("B2", direction, swing, {"htf_zone_m15": zone15, "htf_zone_h1": zone1, "m5_swing_low": _num(x.low.iloc[-9:-1].min()), "m15_swing_high": _num(m15.high.tail(20).max()) if m15 is not None else None, "fvg": fvg, "entry_price": entry, "sl_price": sl, "tp_price": tp, "risk_reward": 2.0}, 92, f"B2|htf-zone-fvg-retest|BUY|{entry}")
    else:
        choch = _num(current.close) < _num(swing)
        fvg = _recent_fvg(x, "SELL")
        retest = _num(current.high) >= fvg["bottom"] if fvg else False
        confirm = _reversal_bear(x)
        if choch and fvg and fvg["width"] >= BTC_FVG_MIN_POINTS and retest and confirm:
            entry = _num(current.close)
            sl = _num(swing) + BTC_POINT_BUFFER
            tp = entry - abs(entry-sl) * 2.0
            return _result("B2", direction, swing, {"htf_zone_m15": zone15, "htf_zone_h1": zone1, "m5_swing_high": _num(x.high.tail(20).max()), "m15_swing_low": _num(m15.low.tail(20).min()) if m15 is not None else None, "fvg": fvg, "entry_price": entry, "sl_price": sl, "tp_price": tp, "risk_reward": 2.0}, 92, f"B2|htf-zone-fvg-retest|SELL|{entry}")
    return _fail("B2", direction, "HTF_ZONE_M5_FVG_RETEST_FAILED")


def _evaluate_b3(x, direction):
    if len(x) < 30:
        return _fail("B3", direction, "INSUFFICIENT_M5_CONTEXT")
    resistance, support = _range(x, 20)
    current = x.iloc[-1]
    avg = _avg_body(x.iloc[:-1], min(20, len(x)-1))
    vr = _volume_ratio(x.iloc[:-1])
    breakout = None
    for i in range(len(x)-6, len(x)-1):
        c = x.iloc[i]
        if direction == "BUY" and _num(c.close) > resistance and _body(c) > avg * 2.0 and _num(c.get("volume", 0)) > _num(x.iloc[max(0, i-20):i].get("volume", pd.Series([1])).mean()) * 1.5:
            breakout = c
        if direction == "SELL" and _num(c.close) < support and _body(c) > avg * 2.0 and _num(c.get("volume", 0)) > _num(x.iloc[max(0, i-20):i].get("volume", pd.Series([1])).mean()) * 1.5:
            breakout = c
    if breakout is None:
        return _fail("B3", direction, "VOLATILITY_EXPANSION_BREAKOUT_FAILED")
    fvg = _recent_fvg(x.iloc[:-1], direction)
    if direction == "BUY":
        retest = _num(current.low) <= resistance
        confirm = _bull(current)
        if retest and confirm:
            entry = _num(current.close); sl = min(_num(breakout.low), _num(fvg["bottom"]) if fvg else _num(breakout.low)) - BTC_POINT_BUFFER; risk = entry-sl
            if risk > 0:
                tp = entry + risk * 1.5
                return _result("B3", direction, resistance, {"resistance": resistance, "support": support, "breakout_high": _num(breakout.high), "breakout_low": _num(breakout.low), "fvg": fvg, "volume_ratio": vr, "entry_price": entry, "sl_price": sl, "tp_price": tp, "risk_reward": 1.5}, 90, f"B3|volatility-breakout-retest|BUY|{entry}")
    else:
        retest = _num(current.high) >= support
        confirm = _bear(current)
        if retest and confirm:
            entry = _num(current.close); sl = max(_num(breakout.high), _num(fvg["top"]) if fvg else _num(breakout.high)) + BTC_POINT_BUFFER; risk = sl-entry
            if risk > 0:
                tp = entry - risk * 1.5
                return _result("B3", direction, support, {"resistance": resistance, "support": support, "breakout_high": _num(breakout.high), "breakout_low": _num(breakout.low), "fvg": fvg, "volume_ratio": vr, "entry_price": entry, "sl_price": sl, "tp_price": tp, "risk_reward": 1.5}, 90, f"B3|volatility-breakout-retest|SELL|{entry}")
    return _fail("B3", direction, "VOLATILITY_EXPANSION_BREAKOUT_RETEST_FAILED")


def evaluate_btc_engines(m5, m15=None, h1=None):
    x = m5.tail(100).reset_index(drop=True).copy()
    out, trace = [], []
    for eid, fn in (("B1", _evaluate_b1),):
        for direction in ("BUY", "SELL"):
            r = fn(x, direction)
            trace.append(f"BTC {eid}:{direction}:{r['status']}" + (f" reason={r['rejection_reasons'][0]}" if r.get('rejection_reasons') else ""))
            if r["status"] == "PASS": out.append(r)
    for direction in ("BUY", "SELL"):
        r = _evaluate_b2(x, m15, h1, direction)
        trace.append(f"BTC B2:{direction}:{r['status']}" + (f" reason={r['rejection_reasons'][0]}" if r.get('rejection_reasons') else ""))
        if r["status"] == "PASS": out.append(r)
    for direction in ("BUY", "SELL"):
        r = _evaluate_b3(x, direction)
        trace.append(f"BTC B3:{direction}:{r['status']}" + (f" reason={r['rejection_reasons'][0]}" if r.get('rejection_reasons') else ""))
        if r["status"] == "PASS": out.append(r)
    return out, trace

"""Multi-Strategy Engine v10.2 for BTC and XAU/USD.

M15 context (100) -> M5 structure (50) -> strategy evaluation -> M5 trigger (1-3).
No H1 dependency and no weighted confluence. All configured strategies for the
asset are evaluated on every eligible scan; regime applicability is reported as
NOT_APPLICABLE rather than silently hiding strategies. Only one passing strategy
may become active, using the configured asset priority order.
"""
from __future__ import annotations
import logging, math
import pandas as pd

logger = logging.getLogger("strategy_engine")

BTC_STRATEGIES = (
    "TREND_PULLBACK", "BREAKOUT_RETEST", "RANGE_BREAKOUT",
    "MOMENTUM", "VOLATILITY_BREAKOUT",
)
GOLD_STRATEGIES = (
    "TREND_PULLBACK", "BREAKOUT_RETEST", "EMA_PULLBACK",
    "LIQUIDITY_SWEEP", "SR_REVERSAL", "VOLATILITY_BREAKOUT",
)

# A strategy is evaluated for every scan, but only these regimes allow it to PASS.
# This preserves the requested 5/6-strategy evaluation log without letting a
# strategy trade in a market condition it was not designed for.
STRATEGY_REGIMES = {
    "BTC": {
        "TREND_PULLBACK": {"TREND_UP", "TREND_DOWN"},
        "BREAKOUT_RETEST": {"TREND_UP", "TREND_DOWN", "BREAKOUT", "VOLATILITY_EXPANSION"},
        "RANGE_BREAKOUT": {"RANGE", "BREAKOUT"},
        "MOMENTUM": {"TREND_UP", "TREND_DOWN", "VOLATILITY_EXPANSION"},
        "VOLATILITY_BREAKOUT": {"BREAKOUT", "VOLATILITY_EXPANSION"},
    },
    "GOLD": {
        "TREND_PULLBACK": {"TREND_UP", "TREND_DOWN"},
        "BREAKOUT_RETEST": {"TREND_UP", "TREND_DOWN", "BREAKOUT", "VOLATILITY_EXPANSION"},
        "EMA_PULLBACK": {"TREND_UP", "TREND_DOWN"},
        "LIQUIDITY_SWEEP": {"RANGE", "BREAKOUT", "VOLATILITY_EXPANSION"},
        "SR_REVERSAL": {"RANGE", "BREAKOUT"},
        "VOLATILITY_BREAKOUT": {"BREAKOUT", "VOLATILITY_EXPANSION"},
    },
}


def _num(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _atr(df, period=14):
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _ema(df, span):
    return pd.to_numeric(df["close"], errors="coerce").ewm(span=span, adjust=False).mean()


def _structure(df, lookback=50):
    x = df.tail(lookback).reset_index(drop=True)
    if len(x) < 20:
        return {"bias": "NEUTRAL", "support": None, "resistance": None, "hh": False, "hl": False, "lh": False, "ll": False}
    highs, lows = [], []
    for i in range(2, len(x) - 2):
        if _num(x.high.iloc[i]) >= max(_num(v) for v in x.high.iloc[i-2:i+3]): highs.append(_num(x.high.iloc[i]))
        if _num(x.low.iloc[i]) <= min(_num(v) for v in x.low.iloc[i-2:i+3]): lows.append(_num(x.low.iloc[i]))
    hh = len(highs) >= 2 and highs[-1] > highs[-2]
    hl = len(lows) >= 2 and lows[-1] > lows[-2]
    lh = len(highs) >= 2 and highs[-1] < highs[-2]
    ll = len(lows) >= 2 and lows[-1] < lows[-2]
    return {
        "bias": "BUY" if hh and hl else "SELL" if lh and ll else "NEUTRAL",
        "support": lows[-1] if lows else _num(x.low.min()),
        "resistance": highs[-1] if highs else _num(x.high.max()),
        "hh": hh, "hl": hl, "lh": lh, "ll": ll,
    }


def _regime(m15, m5):
    x = m15.tail(100).reset_index(drop=True)
    y = m5.tail(50).reset_index(drop=True)
    if len(x) < 100 or len(y) < 50:
        return {"name": "NEUTRAL", "direction": "NEUTRAL", "reason": "INSUFFICIENT_CONTEXT"}
    c15 = _num(x.close.iloc[-1]); e20 = _num(_ema(x, 20).iloc[-1]); e50 = _num(_ema(x, 50).iloc[-1])
    a15 = _atr(x, 14); atr15 = _num(a15.iloc[-1]); med15 = _num(a15.dropna().tail(30).median())
    ratio = atr15 / med15 if med15 > 0 else 0
    s15 = _structure(x, 100)
    direction = "BUY" if c15 > e20 > e50 and s15["bias"] == "BUY" else "SELL" if c15 < e20 < e50 and s15["bias"] == "SELL" else "NEUTRAL"
    a5 = _atr(y, 14); atr5 = _num(a5.iloc[-1]); med5 = _num(a5.dropna().tail(30).median())
    vr = atr5 / med5 if med5 > 0 else 0
    prior = y.iloc[:-1].tail(20); hi = _num(prior.high.max()); lo = _num(prior.low.min()); close = _num(y.close.iloc[-1])
    range_atr = (hi - lo) / max(atr5, 1e-9)
    if vr >= 1.35 and (close > hi or close < lo): name = "VOLATILITY_EXPANSION"
    elif close > hi or close < lo: name = "BREAKOUT"
    elif direction in ("BUY", "SELL") and 0.5 <= ratio <= 2.0: name = "TREND_UP" if direction == "BUY" else "TREND_DOWN"
    elif range_atr <= 8.0: name = "RANGE"
    else: name = "NEUTRAL"
    return {
        "name": name, "direction": direction, "m15_close": c15,
        "m15_ema20": e20, "m15_ema50": e50,
        "m15_atr_ratio": round(ratio, 3), "m5_atr_ratio": round(vr, 3),
        "m5_range_high": hi, "m5_range_low": lo, "m5_range_atr": round(range_atr, 3),
        "structure": s15,
    }


def _candle(df, i=-1):
    r = df.iloc[i]; o, h, l, c = map(_num, (r.open, r.high, r.low, r.close))
    rng = max(h - l, 1e-12); body = abs(c - o)
    return {"open": o, "high": h, "low": l, "close": c, "body": body, "range": rng,
            "body_ratio": body / rng, "bull": c > o, "bear": c < o,
            "upper": h - max(o, c), "lower": min(o, c) - l}


def _trend_pullback(m5, d):
    x = m5.tail(50).reset_index(drop=True); e20 = _ema(x, 20); e50 = _ema(x, 50); a = _num(_atr(x, 14).iloc[-1]); last = _candle(x)
    touch = any((_num(x.low.iloc[i]) <= _num(e20.iloc[i]) + a*.35) if d == "BUY" else (_num(x.high.iloc[i]) >= _num(e20.iloc[i]) - a*.35) for i in range(max(0, len(x)-10), len(x)))
    aligned = (last["close"] > _num(e20.iloc[-1]) > _num(e50.iloc[-1])) if d == "BUY" else (last["close"] < _num(e20.iloc[-1]) < _num(e50.iloc[-1]))
    confirm = (last["bull"] and last["body_ratio"] >= .25) if d == "BUY" else (last["bear"] and last["body_ratio"] >= .25)
    return touch and aligned and confirm


def _ema_pullback(m5, d):
    x = m5.tail(25).reset_index(drop=True); e20 = _ema(x, 20); a = _num(_atr(x, 14).iloc[-1]); last = _candle(x); prev = x.iloc[-2]
    touch = (_num(prev.low) <= _num(e20.iloc[-2]) + a*.35) if d == "BUY" else (_num(prev.high) >= _num(e20.iloc[-2]) - a*.35)
    confirm = (last["bull"] and last["close"] > _num(e20.iloc[-1])) if d == "BUY" else (last["bear"] and last["close"] < _num(e20.iloc[-1]))
    return touch and confirm


def _breakout_retest(m5, d):
    x = m5.tail(50).reset_index(drop=True); a = _num(_atr(x, 14).iloc[-1]); last = _candle(x)
    for j in range(max(5, len(x)-8), len(x)-1):
        base = x.iloc[max(0, j-20):j]; level = _num(base.high.max()) if d == "BUY" else _num(base.low.min()); b = _candle(x, j)
        broke = (b["close"] > level and b["bull"] and b["body_ratio"] >= .30) if d == "BUY" else (b["close"] < level and b["bear"] and b["body_ratio"] >= .30)
        if broke:
            retest = (last["low"] <= level+a*.55 and last["close"] >= level and last["bull"]) if d == "BUY" else (last["high"] >= level-a*.55 and last["close"] <= level and last["bear"])
            if retest: return True
    return False


def _range_breakout(m5, d):
    x = m5.tail(30).reset_index(drop=True); prior = x.iloc[:-1].tail(20); last = _candle(x); hi = _num(prior.high.max()); lo = _num(prior.low.min())
    return (last["close"] > hi and last["bull"] and last["body_ratio"] >= .30) if d == "BUY" else (last["close"] < lo and last["bear"] and last["body_ratio"] >= .30)


def _momentum(m5, d):
    x = m5.tail(20).reset_index(drop=True); a = _num(_atr(x, 14).iloc[-1]); last = _candle(x); move = _num(x.close.iloc[-1]) - _num(x.close.iloc[-6])
    return (move > a and last["bull"] and last["body_ratio"] >= .45) if d == "BUY" else (move < -a and last["bear"] and last["body_ratio"] >= .45)


def _volatility_breakout(m5, d):
    x = m5.tail(45).reset_index(drop=True); aa = _atr(x, 14); a = _num(aa.iloc[-1]); med = _num(aa.dropna().tail(30).median()); last = _candle(x); prior = x.iloc[:-1].tail(20); hi = _num(prior.high.max()); lo = _num(prior.low.min())
    return a/max(med, 1e-9) >= 1.25 and ((last["close"] > hi and last["bull"]) if d == "BUY" else (last["close"] < lo and last["bear"]))


def _liquidity_sweep(m5, d):
    x = m5.tail(30).reset_index(drop=True); a = _num(_atr(x, 14).iloc[-1]); last = _candle(x); prev = x.iloc[:-1].tail(12); hi = _num(prev.high.max()); lo = _num(prev.low.min())
    return (last["low"] < lo-a*.05 and last["close"] > lo and last["bull"]) if d == "BUY" else (last["high"] > hi+a*.05 and last["close"] < hi and last["bear"])


def _sr_reversal(m5, d):
    x = m5.tail(40).reset_index(drop=True); a = _num(_atr(x, 14).iloc[-1]); last = _candle(x); prior = x.iloc[:-1].tail(20); hi = _num(prior.high.max()); lo = _num(prior.low.min())
    return (last["low"] <= lo+a*.20 and last["close"] > lo and last["lower"] >= last["body"]*1.2) if d == "BUY" else (last["high"] >= hi-a*.20 and last["close"] < hi and last["upper"] >= last["body"]*1.2)


_FUNCS = {
    "TREND_PULLBACK": _trend_pullback, "BREAKOUT_RETEST": _breakout_retest,
    "RANGE_BREAKOUT": _range_breakout, "MOMENTUM": _momentum,
    "VOLATILITY_BREAKOUT": _volatility_breakout, "EMA_PULLBACK": _ema_pullback,
    "LIQUIDITY_SWEEP": _liquidity_sweep, "SR_REVERSAL": _sr_reversal,
}


def _candidate_order(symbol, regime):
    return list(BTC_STRATEGIES if symbol == "BTC" else GOLD_STRATEGIES)


def _candidate_directions(strategy, regime, m5, regime_direction):
    if regime_direction in ("BUY", "SELL"):
        return [regime_direction]
    x = m5.tail(21).reset_index(drop=True); last = _candle(x); prior = x.iloc[:-1].tail(20); hi = _num(prior.high.max()); lo = _num(prior.low.min())
    if strategy in ("RANGE_BREAKOUT", "BREAKOUT_RETEST", "VOLATILITY_BREAKOUT"):
        dirs = []
        if last["close"] > hi: dirs.append("BUY")
        if last["close"] < lo: dirs.append("SELL")
        return dirs or ["BUY", "SELL"]
    if strategy in ("SR_REVERSAL", "LIQUIDITY_SWEEP"):
        return ["BUY", "SELL"] if last["bull"] else ["SELL", "BUY"]
    return ["BUY", "SELL"]


def _diagnose(strategy, m5, d):
    x = m5.tail(50).reset_index(drop=True); last = _candle(x); a = _num(_atr(x, 14).iloc[-1]); reasons = []
    if a <= 0: return False, ["ATR_UNAVAILABLE"]
    if strategy == "TREND_PULLBACK":
        e20 = _ema(x, 20); e50 = _ema(x, 50)
        aligned = (last["close"] > _num(e20.iloc[-1]) > _num(e50.iloc[-1])) if d == "BUY" else (last["close"] < _num(e20.iloc[-1]) < _num(e50.iloc[-1]))
        touch = any((_num(x.low.iloc[i]) <= _num(e20.iloc[i]) + a*.35) if d == "BUY" else (_num(x.high.iloc[i]) >= _num(e20.iloc[i]) - a*.35) for i in range(max(0, len(x)-10), len(x)))
        confirm = (last["bull"] and last["body_ratio"] >= .25) if d == "BUY" else (last["bear"] and last["body_ratio"] >= .25)
        if not touch: reasons.append("NO_EMA20_PULLBACK_TOUCH")
        if not aligned: reasons.append("EMA20_EMA50_ALIGNMENT_FAILED")
        if not confirm: reasons.append("ENTRY_CANDLE_CONFIRMATION_FAILED")
    elif strategy == "EMA_PULLBACK":
        e20 = _ema(x, 20); prev = x.iloc[-2]
        touch = (_num(prev.low) <= _num(e20.iloc[-2]) + a*.35) if d == "BUY" else (_num(prev.high) >= _num(e20.iloc[-2]) - a*.35)
        confirm = (last["bull"] and last["close"] > _num(e20.iloc[-1])) if d == "BUY" else (last["bear"] and last["close"] < _num(e20.iloc[-1]))
        if not touch: reasons.append("PREVIOUS_CANDLE_DID_NOT_TOUCH_EMA20")
        if not confirm: reasons.append("EMA20_CLOSING_CONFIRMATION_FAILED")
    elif strategy in ("RANGE_BREAKOUT", "VOLATILITY_BREAKOUT"):
        p = x.iloc[:-1].tail(20); hi = _num(p.high.max()); lo = _num(p.low.min())
        if strategy == "VOLATILITY_BREAKOUT":
            aa = _atr(x, 14); med = _num(aa.dropna().tail(30).median())
            if a/max(med, 1e-9) < 1.25: reasons.append("VOLATILITY_EXPANSION_BELOW_1.25X")
        if not ((last["close"] > hi) if d == "BUY" else (last["close"] < lo)): reasons.append("RANGE_BOUNDARY_NOT_BROKEN")
        if not ((last["bull"] if d == "BUY" else last["bear"])): reasons.append("BREAKOUT_CANDLE_DIRECTION_FAILED")
        if last["body_ratio"] < .30: reasons.append("BREAKOUT_BODY_TOO_SMALL")
    elif strategy == "MOMENTUM":
        move = last["close"] - _num(x.close.iloc[-6])
        if not (move > a if d == "BUY" else move < -a): reasons.append("MOMENTUM_MOVE_BELOW_ATR")
        if not ((last["bull"] and last["body_ratio"] >= .45) if d == "BUY" else (last["bear"] and last["body_ratio"] >= .45)): reasons.append("MOMENTUM_CANDLE_STRENGTH_FAILED")
    elif strategy == "BREAKOUT_RETEST":
        found = False
        for j in range(max(5, len(x)-8), len(x)-1):
            base = x.iloc[max(0, j-20):j]; level = _num(base.high.max()) if d == "BUY" else _num(base.low.min()); b = _candle(x, j)
            broke = (b["close"] > level and b["bull"] and b["body_ratio"] >= .30) if d == "BUY" else (b["close"] < level and b["bear"] and b["body_ratio"] >= .30)
            if broke:
                retest = (last["low"] <= level+a*.55 and last["close"] >= level and last["bull"]) if d == "BUY" else (last["high"] >= level-a*.55 and last["close"] <= level and last["bear"])
                if retest: found = True; break
        if not found: reasons.append("BREAKOUT_RETEST_SEQUENCE_NOT_CONFIRMED")
    elif strategy == "LIQUIDITY_SWEEP":
        p = x.iloc[:-1].tail(12); hi = _num(p.high.max()); lo = _num(p.low.min())
        ok = (last["low"] < lo-a*.05 and last["close"] > lo and last["bull"]) if d == "BUY" else (last["high"] > hi+a*.05 and last["close"] < hi and last["bear"])
        if not ok: reasons.append("LIQUIDITY_SWEEP_REJECTION_NOT_CONFIRMED")
    elif strategy == "SR_REVERSAL":
        p = x.iloc[:-1].tail(20); hi = _num(p.high.max()); lo = _num(p.low.min())
        ok = (last["low"] <= lo+a*.20 and last["close"] > lo and last["lower"] >= last["body"]*1.2) if d == "BUY" else (last["high"] >= hi-a*.20 and last["close"] < hi and last["upper"] >= last["body"]*1.2)
        if not ok: reasons.append("SUPPORT_RESISTANCE_REJECTION_NOT_CONFIRMED")
    else:
        reasons.append("UNKNOWN_STRATEGY")
    return not reasons, reasons or ["SETUP_VALID"]


def _log_evaluations(symbol, regime, tested):
    logger.warning("[%s] STRATEGY EVALUATION START | regime=%s | count=%d", symbol, regime, len(tested))
    for item in tested:
        logger.warning("[%s] STRATEGY EVAL | strategy=%s | direction=%s | status=%s | reason=%s",
                       symbol, item["strategy"], item["direction"], item["status"], item["reason"])
    passed = [f'{x["strategy"]}:{x["direction"]}' for x in tested if x["status"] == "PASS"]
    logger.warning("[%s] STRATEGY EVALUATION SUMMARY | PASS=%s | FAIL=%d | NOT_APPLICABLE=%d",
                   symbol, passed or "NONE", sum(x["status"] == "FAIL" for x in tested), sum(x["status"] == "NOT_APPLICABLE" for x in tested))


def analyze(m5, m15, h1=None, symbol="BTC"):
    symbol = "GOLD" if str(symbol).upper() in ("GOLD", "XAU", "XAU/USDT", "XAU/USD") else "BTC"
    if len(m5) < 80 or len(m15) < 100:
        return {"signal": "NO_TRADE", "valid": False, "strategy": "NONE", "regime": "NEUTRAL", "rejection_reasons": ["INSUFFICIENT_CONTEXT"]}
    regime = _regime(m15, m5); rn = regime.get("name", "NEUTRAL"); direction = regime.get("direction", "NEUTRAL")
    order = _candidate_order(symbol, rn); tested = []
    for strategy in order:
        applicable = rn in STRATEGY_REGIMES[symbol][strategy]
        directions = _candidate_directions(strategy, rn, m5, direction) if applicable else [direction if direction in ("BUY", "SELL") else "NEUTRAL"]
        for d in directions:
            if not applicable:
                tested.append({"strategy": strategy, "direction": d, "passed": False, "status": "NOT_APPLICABLE", "reason": [f"REGIME_{rn}_NOT_SUPPORTED"]})
                continue
            diag_ok, reasons = _diagnose(strategy, m5, d)
            passed = bool(diag_ok and _FUNCS[strategy](m5, d))
            tested.append({"strategy": strategy, "direction": d, "passed": passed, "status": "PASS" if passed else "FAIL", "reason": ["SETUP_VALID"] if passed else reasons})
            if passed:
                _log_evaluations(symbol, rn, tested)
                return {"signal": d, "valid": True, "strategy": strategy, "regime": rn, "regime_detail": regime,
                        "strategy_candidates": tested, "analysis_window": {"m15_context_bars": 100, "m5_structure_bars": 50, "m5_setup_bars": 20, "m5_trigger_bars": 3},
                        "trigger_candle_count": 3, "rejection_reasons": []}
    _log_evaluations(symbol, rn, tested)
    return {"signal": "NO_TRADE", "valid": False, "strategy": "NONE", "regime": rn, "regime_detail": regime,
            "strategy_candidates": tested, "analysis_window": {"m15_context_bars": 100, "m5_structure_bars": 50, "m5_setup_bars": 20, "m5_trigger_bars": 3},
            "rejection_reasons": ["NO_STRATEGY_SETUP"]}

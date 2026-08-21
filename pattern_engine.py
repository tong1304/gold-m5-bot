"""Deterministic multi-category pattern recognition for manual-entry signals.

The engine intentionally detects evidence rather than treating every pattern as an
automatic trade. It returns structured observations that a confluence layer can score.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h-l).abs(), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _body(row):
    return abs(float(row.close) - float(row.open))


def _range(row):
    return max(float(row.high) - float(row.low), 1e-12)


def detect_price_action(df: pd.DataFrame, i: int) -> list[dict[str, Any]]:
    if i < 3:
        return []
    a, b = df.iloc[i-1], df.iloc[i]
    out = []
    body_b = _body(b)
    body_a = _body(a)
    if b.close > b.open and a.close < a.open and b.open <= a.close and b.close >= a.open:
        out.append({"name":"Bullish Engulfing","category":"PRICE_ACTION","direction":"BUY"})
    if b.close < b.open and a.close > a.open and b.open >= a.close and b.close <= a.open:
        out.append({"name":"Bearish Engulfing","category":"PRICE_ACTION","direction":"SELL"})
    upper = float(b.high) - max(float(b.open), float(b.close))
    lower = min(float(b.open), float(b.close)) - float(b.low)
    if lower >= max(body_b * 2, _range(b) * 0.45) and b.close > b.open:
        out.append({"name":"Hammer / Rejection","category":"PRICE_ACTION","direction":"BUY"})
    if upper >= max(body_b * 2, _range(b) * 0.45) and b.close < b.open:
        out.append({"name":"Shooting Star / Rejection","category":"PRICE_ACTION","direction":"SELL"})
    if float(b.high) <= float(a.high) and float(b.low) >= float(a.low):
        out.append({"name":"Inside Bar","category":"PRICE_ACTION","direction":"NEUTRAL"})
    if body_a < _range(a)*0.15 and body_b > body_a*1.8:
        direction = "BUY" if b.close > b.open else "SELL"
        out.append({"name":"Three-Candle Reversal Candidate","category":"PRICE_ACTION","direction":direction})
    return out


def detect_chart_patterns(df: pd.DataFrame, i: int, lookback: int = 60) -> list[dict[str, Any]]:
    if i < 10:
        return []
    s = df.iloc[max(0, i-lookback):i+1]
    highs, lows = s.high.to_numpy(), s.low.to_numpy()
    out = []
    if len(highs) >= 20:
        h = np.sort(highs)[-5:]
        l = np.sort(lows)[:5]
        if h[-1]-h[0] <= max(np.mean(_atr(s).dropna()) if _atr(s).notna().any() else 0, 1e-9)*1.5:
            out.append({"name":"Double Top Candidate","category":"CHART_PATTERN","direction":"SELL"})
        if l[-1]-l[0] <= max(np.mean(_atr(s).dropna()) if _atr(s).notna().any() else 0, 1e-9)*1.5:
            out.append({"name":"Double Bottom Candidate","category":"CHART_PATTERN","direction":"BUY"})
        recent = s.tail(12)
        width = recent.high.max() - recent.low.min()
        if width > 0 and recent.high.diff().dropna().mean() < 0 and recent.low.diff().dropna().mean() > 0:
            out.append({"name":"Symmetrical Triangle Candidate","category":"CHART_PATTERN","direction":"NEUTRAL"})
    return out


def detect_smc(df: pd.DataFrame, i: int, swing: int = 3) -> list[dict[str, Any]]:
    if i < swing * 2 + 2:
        return []
    out = []
    recent = df.iloc[i-swing:i]
    prev = df.iloc[i-2*swing:i-swing]
    atr = float(_atr(df).iloc[i]) if pd.notna(_atr(df).iloc[i]) else 0
    if not atr:
        return out
    high_prev, low_prev = float(prev.high.max()), float(prev.low.min())
    high_recent, low_recent = float(recent.high.max()), float(recent.low.min())
    row = df.iloc[i]
    if float(row.high) > high_prev and float(row.close) < high_prev:
        out.append({"name":"Liquidity Sweep High","category":"SMC_ICT","direction":"SELL"})
    if float(row.low) < low_prev and float(row.close) > low_prev:
        out.append({"name":"Liquidity Sweep Low","category":"SMC_ICT","direction":"BUY"})
    if float(row.close) > high_recent:
        out.append({"name":"Bullish BOS / MSS Candidate","category":"SMC_ICT","direction":"BUY"})
    if float(row.close) < low_recent:
        out.append({"name":"Bearish BOS / MSS Candidate","category":"SMC_ICT","direction":"SELL"})
    if i >= 2:
        c0, c1, c2 = df.iloc[i-2], df.iloc[i-1], df.iloc[i]
        if float(c0.high) < float(c2.low):
            out.append({"name":"Bullish FVG","category":"SMC_ICT","direction":"BUY"})
        if float(c0.low) > float(c2.high):
            out.append({"name":"Bearish FVG","category":"SMC_ICT","direction":"SELL"})
    return out


def detect_supply_demand(df: pd.DataFrame, i: int) -> list[dict[str, Any]]:
    if i < 5:
        return []
    out = []
    a, b = df.iloc[i-1], df.iloc[i]
    atr = _atr(df).iloc[i]
    if pd.isna(atr) or atr <= 0:
        return out
    impulse = abs(float(b.close)-float(a.close))
    if impulse >= float(atr)*1.5:
        if b.close > b.open:
            out.append({"name":"Demand Impulse / Base Candidate","category":"SUPPLY_DEMAND","direction":"BUY"})
        else:
            out.append({"name":"Supply Impulse / Base Candidate","category":"SUPPLY_DEMAND","direction":"SELL"})
    return out


def detect_trend_breakout(df: pd.DataFrame, i: int) -> list[dict[str, Any]]:
    if i < 55:
        return []
    close = df.close
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    out = []
    row = df.iloc[i]
    if ema20.iloc[i] > ema50.iloc[i] and close.iloc[i] > ema20.iloc[i]:
        out.append({"name":"Uptrend / EMA20-50 Alignment","category":"TREND_BREAKOUT","direction":"BUY"})
    if ema20.iloc[i] < ema50.iloc[i] and close.iloc[i] < ema20.iloc[i]:
        out.append({"name":"Downtrend / EMA20-50 Alignment","category":"TREND_BREAKOUT","direction":"SELL"})
    prior_high = float(df.high.iloc[i-20:i].max())
    prior_low = float(df.low.iloc[i-20:i].min())
    if float(row.close) > prior_high:
        out.append({"name":"20-Bar Breakout","category":"TREND_BREAKOUT","direction":"BUY"})
    if float(row.close) < prior_low:
        out.append({"name":"20-Bar Breakdown","category":"TREND_BREAKOUT","direction":"SELL"})
    return out


def detect_fibonacci(df: pd.DataFrame, i: int) -> list[dict[str, Any]]:
    if i < 30:
        return []
    s = df.iloc[i-30:i+1]
    hi, lo, px = float(s.high.max()), float(s.low.min()), float(df.close.iloc[i])
    span = hi-lo
    if span <= 0:
        return []
    levels = {"38.2":hi-span*.382,"50.0":hi-span*.5,"61.8":hi-span*.618}
    tolerance = span*.012
    for name, level in levels.items():
        if abs(px-level) <= tolerance:
            direction = "BUY" if px < (hi+lo)/2 else "SELL"
            return [{"name":f"Fibonacci {name}% Zone","category":"FIBONACCI_HARMONIC","direction":direction}]
    return []


def detect_indicators_session(df: pd.DataFrame, i: int) -> list[dict[str, Any]]:
    if i < 30:
        return []
    close = df.close
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100/(1+rs))
    value = float(rsi.iloc[i]) if pd.notna(rsi.iloc[i]) else 50
    out = []
    if value < 30:
        out.append({"name":"RSI Oversold","category":"INDICATOR_SESSION","direction":"BUY"})
    elif value > 70:
        out.append({"name":"RSI Overbought","category":"INDICATOR_SESSION","direction":"SELL"})
    return out


def detect_all(df: pd.DataFrame, i: int) -> dict[str, Any]:
    groups = {
        "PRICE_ACTION": detect_price_action(df, i),
        "CHART_PATTERN": detect_chart_patterns(df, i),
        "SMC_ICT": detect_smc(df, i),
        "SUPPLY_DEMAND": detect_supply_demand(df, i),
        "TREND_BREAKOUT": detect_trend_breakout(df, i),
        "FIBONACCI_HARMONIC": detect_fibonacci(df, i),
        "INDICATOR_SESSION": detect_indicators_session(df, i),
    }
    patterns = [p for values in groups.values() for p in values]
    return {"groups":groups,"patterns":patterns,"pattern_count":len(patterns)}


def confluence(patterns: list[dict[str, Any]], minimum: int = 3) -> dict[str, Any]:
    buy = [p for p in patterns if p.get("direction") == "BUY"]
    sell = [p for p in patterns if p.get("direction") == "SELL"]
    buy_categories = {p.get("category") for p in buy}
    sell_categories = {p.get("category") for p in sell}
    buy_score = min(100, len(buy)*12 + len(buy_categories)*10)
    sell_score = min(100, len(sell)*12 + len(sell_categories)*10)
    if buy_score >= sell_score and buy_score >= minimum*20:
        direction, score = "BUY", buy_score
    elif sell_score > buy_score and sell_score >= minimum*20:
        direction, score = "SELL", sell_score
    else:
        direction, score = "NO_TRADE", max(buy_score, sell_score)
    return {"signal":direction,"score":round(float(score),2),"buy_evidence":buy,"sell_evidence":sell,"buy_categories":sorted(x for x in buy_categories if x),"sell_categories":sorted(x for x in sell_categories if x),"minimum_confluence":minimum}

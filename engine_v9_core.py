"""Structure V9 - pattern-driven live/replay signal engine for BTC + GOLD.

V9 keeps the V8 MTF structure and risk controls but changes the trigger rule:
ONE clear M5 price-action pattern is sufficient when H1/M15 direction agrees and
there is no direct M15 conflict. Liquidity sweep and MSS/BOS are confirmations,
not mandatory weighted-confluence requirements. No weighted score is used.
Minimum RR remains 2R.
"""
from __future__ import annotations

import engine_v8_core as base

ENGINE_VERSION = "9.0"
app = base.app
SYMBOL = base.SYMBOL
SPREAD = base.SPREAD
SLIPPAGE = base.SLIPPAGE
MINIMUM_ATR = base.MINIMUM_ATR
MIN_STOP_ATR = base.MIN_STOP_ATR
MAX_STOP_ATR = base.MAX_STOP_ATR
MIN_RISK_REWARD = max(float(base.MIN_RISK_REWARD), 2.0)
RISK_REWARD = MIN_RISK_REWARD
FORWARD_BARS = base.FORWARD_BARS
SIGNAL_HISTORY_POINTS = base.SIGNAL_HISTORY_POINTS

_f = base._f
_atr = base._atr
_structure = base._structure
_location = base._location
_find_sweep = base._find_sweep
_find_mss = base._find_mss
_retest = base._retest
_target_liquidity = base._target_liquidity
resolve_trade = base.resolve_trade
remove_incomplete_last_candle = base.remove_incomplete_last_candle
evaluate_live_risk_guard = base.evaluate_live_risk_guard


def execution_price(raw, side):
    adverse = max(float(SPREAD) / 2.0 + float(SLIPPAGE), 0.0)
    p = _f(raw)
    return p + adverse if side == "BUY" else p - adverse


def send_telegram(message):
    text = str(message).replace("Structure V8", "Structure V9").replace("V8 Setup", "V9 Setup")
    return base.send_telegram(text)


def _candle_pattern(df, direction):
    """Return one clear, non-lookahead M5 pattern on the latest closed candle."""
    if df is None or len(df) < 25:
        return None
    x = df.reset_index(drop=True)
    i = len(x) - 1
    r = x.iloc[i]
    p = x.iloc[i - 1]
    atr = _atr(x, i)
    o, h, l, c = map(float, (r.open, r.high, r.low, r.close))
    po, ph, pl, pc = map(float, (p.open, p.high, p.low, p.close))
    body = abs(c - o)
    rng = max(h - l, 1e-12)
    upper = h - max(o, c)
    lower = min(o, c) - l
    prev_body = abs(pc - po)

    if direction == "BUY":
        engulf = c > o and pc < po and o <= pc and c >= po and body >= max(prev_body * 0.90, atr * 0.20)
        pin = c > o and lower >= max(body * 2.0, atr * 0.35) and upper <= body * 0.8 and (c-l)/rng >= 0.65
        breakout = c > ph and body >= max(atr * 0.25, rng * 0.35)
        if engulf:
            return {"name":"BULLISH_ENGULFING","direction":"BUY","index":i,"strength":"CLEAR"}
        if pin:
            return {"name":"BULLISH_PIN_BAR","direction":"BUY","index":i,"strength":"CLEAR"}
        if breakout:
            return {"name":"BULLISH_BREAKOUT","direction":"BUY","index":i,"strength":"CLEAR"}
    else:
        engulf = c < o and pc > po and o >= pc and c <= po and body >= max(prev_body * 0.90, atr * 0.20)
        pin = c < o and upper >= max(body * 2.0, atr * 0.35) and lower <= body * 0.8 and (h-c)/rng >= 0.65
        breakout = c < pl and body >= max(atr * 0.25, rng * 0.35)
        if engulf:
            return {"name":"BEARISH_ENGULFING","direction":"SELL","index":i,"strength":"CLEAR"}
        if pin:
            return {"name":"BEARISH_PIN_BAR","direction":"SELL","index":i,"strength":"CLEAR"}
        if breakout:
            return {"name":"BEARISH_BREAKOUT","direction":"SELL","index":i,"strength":"CLEAR"}
    return None


def _pattern_context(df, direction):
    p = _candle_pattern(df, direction)
    if p:
        return {"valid":True,"pattern":p}
    return {"valid":False,"pattern":None,"reason":"NO_CLEAR_M5_PATTERN"}


def build_trade_levels(df, index, direction, invalidation, target, pattern=None):
    if target is None:
        return {"valid":False,"reason":"LEVELS_UNAVAILABLE"}
    entry = execution_price(df.iloc[index].close, direction)
    atr = _atr(df, index)
    if invalidation is None:
        r = df.iloc[index]
        invalidation = float(r.low) if direction == "BUY" else float(r.high)
    buffer = max(atr * 0.12, 1e-9)
    sl = float(invalidation) - buffer if direction == "BUY" else float(invalidation) + buffer
    tp = float(target)
    if direction == "BUY" and not sl < entry < tp:
        return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    if direction == "SELL" and not sl > entry > tp:
        return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    risk = abs(entry-sl)
    reward = abs(tp-entry)
    rr = reward/risk if risk else 0.0
    if rr < MIN_RISK_REWARD:
        return {"valid":False,"reason":"RR_BELOW_2R","entry":entry,"sl":sl,"tp":tp,"risk":risk,"reward":reward,"risk_reward":rr}
    return {"valid":True,"entry":round(entry,8),"sl":round(sl,8),"tp":round(tp,8),"risk":round(risk,8),"reward":round(reward,8),"risk_reward":round(rr,3),"effective_rr":round(rr,3),"source":"structure_v9"}


def analyze_structure_setup(m5, m15, h1, index=None):
    if index is None:
        index = len(m5)-1
    m5 = m5.iloc[:index+1].reset_index(drop=True)
    if len(m5) < 80 or len(m15) < 60 or len(h1) < 60:
        return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["INSUFFICIENT_CONTEXT"]}

    h1s = _structure(h1)
    m15s = _structure(m15)
    direction = h1s["bias"] if h1s["bias"] in ("BUY","SELL") else m15s["bias"]
    if direction not in ("BUY","SELL"):
        return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["NO_DIRECTIONAL_STRUCTURE"],"structure_bias":h1s,"m15_structure":m15s}

    reasons = []
    if m15s["bias"] in ("BUY","SELL") and m15s["bias"] != direction:
        reasons.append("M15_OPPOSES_H1")

    loc = _location(m15, direction)
    if not loc["valid"]:
        reasons.append("M15_LOCATION_INVALID")

    pattern_ctx = _pattern_context(m5, direction)
    if not pattern_ctx["valid"]:
        reasons.append(pattern_ctx["reason"])

    sweep = _find_sweep(m5, direction)
    mss = _find_mss(m5, sweep, direction)
    if sweep and not mss:
        mss = _find_mss(m5, sweep, direction, window=16)

    confirmations = []
    if sweep:
        confirmations.append("LIQUIDITY_SWEEP")
    if mss:
        confirmations.append("MSS_BOS")
    if pattern_ctx["valid"]:
        confirmations.append("CLEAR_M5_PATTERN")

    retest = _retest(m5, mss, direction) if mss else {"valid":False,"reason":"NO_MSS_BOS_CONFIRMATION_OPTIONAL"}
    entry = _f(m5.iloc[-1].close)
    target = _target_liquidity(m5, direction, entry)
    if target is None:
        reasons.append("NO_LIQUIDITY_TARGET")

    invalidation = sweep["extreme"] if sweep else None
    levels = build_trade_levels(m5, len(m5)-1, direction, invalidation, target, pattern_ctx.get("pattern"))
    if not levels.get("valid"):
        reasons.append(levels.get("reason","LEVELS_INVALID"))

    signal = direction if not reasons else "NO_TRADE"
    pattern_name = ((pattern_ctx.get("pattern") or {}).get("name") or "NONE")
    sweep_index = sweep.get("index") if isinstance(sweep, dict) else "NO_SWEEP"
    mss_index = mss.get("index") if isinstance(mss, dict) else "NO_MSS"
    setup_key = f"{direction}:{pattern_name}:{sweep_index}:{mss_index}"
    return {"signal":signal,"engine_version":ENGINE_VERSION,"valid":signal in ("BUY","SELL") and levels.get("valid",False),"structure_bias":h1s,"m15_structure":m15s,"location":loc,"pattern":pattern_ctx.get("pattern"),"pattern_valid":pattern_ctx["valid"],"confirmations":confirmations,"liquidity_event":sweep,"m5_trigger":mss,"pullback":retest,"target_liquidity":target,"invalidation":invalidation,"trade_levels":levels,"setup_key":setup_key,"rejection_reasons":reasons}


def calculate_trade_levels(df, i, direction, entry_price=None):
    setup = analyze_structure_setup(df, df, df, i)
    if setup.get("valid") and setup.get("signal") == direction:
        return setup["trade_levels"]
    return {"valid":False,"reason":"NO_VALID_STRUCTURE_SETUP"}


def calculate_indicators(df):
    return base.calculate_indicators(df)

base = base

from __future__ import annotations

"""E3 — Professional Market Structure Brain.

Single-brain implementation. The former 3A-3F sub-engines are intentionally
not split into separate runtime modules; their reasoning is performed inside
this brain so E3 can later be decomposed without changing its contract.
E3 analyses structure only. It never authorizes or blocks a trade.
"""

import math
import pandas as pd


def _f(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _atr(df, period=14):
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=3).mean()


def e3_structure(m5, e1, e2):
    """Read external/internal price structure from closed M5 candles.

    Rules deliberately favor confirmed structural facts over raw wick breaks:
    - pivots require left/right confirmation;
    - ATR-normalized prominence filters insignificant noise;
    - external structure uses a wider pivot scale than internal structure;
    - BOS requires a close beyond a confirmed swing, not merely a wick;
    - a break that closes back through the level is classified as failed;
    - conflicting internal/external evidence is preserved, never hidden.
    """
    if len(m5) < 80:
        return {
            "engine": "E3",
            "question": "What does price structure say about the current opportunity?",
            "analysis_status": "INCOMPLETE",
            "conclusion": "INSUFFICIENT_DATA",
            "confidence": 0.0,
            "observations": ["Need >=80 M5 candles for confirmed structure"],
            "structure": "UNKNOWN",
            "structure_state": "UNKNOWN",
            "bos": "NONE",
            "structural_bias": "NEUTRAL",
        }

    # The scanner supplies closed candles plus the current row in some paths.
    # Never let the still-forming candle create a structural event.
    closed = m5.iloc[:-1].copy() if len(m5) > 1 else m5.copy()
    if len(closed) < 70:
        return {
            "engine": "E3", "question": "What does price structure say about the current opportunity?",
            "analysis_status": "INCOMPLETE", "conclusion": "INSUFFICIENT_DATA", "confidence": 0.0,
            "observations": ["Not enough closed candles for structure confirmation"],
            "structure": "UNKNOWN", "structure_state": "UNKNOWN", "bos": "NONE", "structural_bias": "NEUTRAL",
        }

    for col in ("open", "high", "low", "close"):
        closed[col] = pd.to_numeric(closed[col], errors="coerce")
    closed = closed.dropna(subset=["high", "low", "close"]).reset_index(drop=True)
    atr_series = _atr(closed)
    atr_now = max(_f(atr_series.iloc[-1]), 1e-9)

    def pivots(window):
        highs, lows = [], []
        if len(closed) < window * 2 + 5:
            return highs, lows
        h = closed["high"].to_numpy()
        l = closed["low"].to_numpy()
        for i in range(window, len(closed) - window):
            local_h = h[i-window:i+window+1]
            local_l = l[i-window:i+window+1]
            rng = max(_f(atr_series.iloc[i]), 1e-9)
            prominence_h = h[i] - max(h[i-window:i])
            prominence_l = min(l[i-window:i]) - l[i]
            right_h = h[i] - max(h[i+1:i+window+1])
            right_l = min(l[i+1:i+window+1]) - l[i]
            if h[i] == local_h.max() and prominence_h >= 0.12 * rng and right_h >= 0.08 * rng:
                highs.append((i, _f(h[i]), rng))
            if l[i] == local_l.min() and prominence_l >= 0.12 * rng and right_l >= 0.08 * rng:
                lows.append((i, _f(l[i]), rng))
        return highs, lows

    internal_h, internal_l = pivots(2)
    external_h, external_l = pivots(4)

    def classify(highs, lows):
        hh = hl = lh = ll = 0
        labels = []
        if len(highs) >= 2:
            for a, b in zip(highs[-6:-1], highs[-5:]):
                labels.append("HH" if b[1] > a[1] else "LH")
                if b[1] > a[1]: hh += 1
                elif b[1] < a[1]: lh += 1
        if len(lows) >= 2:
            for a, b in zip(lows[-6:-1], lows[-5:]):
                labels.append("HL" if b[1] > a[1] else "LL")
                if b[1] > a[1]: hl += 1
                elif b[1] < a[1]: ll += 1
        bull = hh + hl
        bear = lh + ll
        if bull >= 2 and bull > bear + 1:
            state = "BULLISH"
        elif bear >= 2 and bear > bull + 1:
            state = "BEARISH"
        elif bull or bear:
            state = "MIXED"
        else:
            state = "NEUTRAL"
        return state, labels, {"HH": hh, "HL": hl, "LH": lh, "LL": ll}

    ext_state, ext_labels, ext_counts = classify(external_h, external_l)
    int_state, int_labels, int_counts = classify(internal_h, internal_l)

    last_close = _f(closed["close"].iloc[-1])
    prior_close = _f(closed["close"].iloc[-2])

    # Only the latest confirmed external swing is eligible for a major BOS.
    last_ext_high = external_h[-1] if external_h else None
    last_ext_low = external_l[-1] if external_l else None
    last_int_high = internal_h[-1] if internal_h else None
    last_int_low = internal_l[-1] if internal_l else None

    bullish_bos = bool(last_ext_high and last_close > last_ext_high[1] and prior_close <= last_ext_high[1])
    bearish_bos = bool(last_ext_low and last_close < last_ext_low[1] and prior_close >= last_ext_low[1])
    bos = "BULLISH" if bullish_bos else "BEARISH" if bearish_bos else "NONE"
    bos_type = "EXTERNAL_CLOSE_BREAK" if bos != "NONE" else "NONE"
    bos_level = last_ext_high[1] if bullish_bos else last_ext_low[1] if bearish_bos else None
    bos_index = last_ext_high[0] if bullish_bos else last_ext_low[0] if bearish_bos else None

    # Structural failure: a recent confirmed break is rejected back through
    # the broken level. This is evidence of failed acceptance, not a reversal
    # authorization.
    failure = "NONE"
    failure_type = "NONE"
    failure_level = None
    if last_ext_high and len(closed) >= 2:
        level = last_ext_high[1]
        recent_window = closed.tail(4)
        broke = bool((recent_window["high"] > level).any())
        rejected = _f(recent_window["close"].iloc[-1]) < level
        if broke and rejected:
            failure = "BULLISH_BREAK_FAILURE"
            failure_type = "FAILED_UPSIDE_ACCEPTANCE"
            failure_level = level
    if last_ext_low and len(closed) >= 2 and failure == "NONE":
        level = last_ext_low[1]
        recent_window = closed.tail(4)
        broke = bool((recent_window["low"] < level).any())
        rejected = _f(recent_window["close"].iloc[-1]) > level
        if broke and rejected:
            failure = "BEARISH_BREAK_FAILURE"
            failure_type = "FAILED_DOWNSIDE_ACCEPTANCE"
            failure_level = level

    # Strength is evidence quality, not trade permission.
    ext_events = min(4, len(external_h) + len(external_l))
    internal_events = min(4, len(internal_h) + len(internal_l))
    continuity = max(ext_counts.values()) if ext_counts else 0
    strength = 35.0 + ext_events * 7.0 + internal_events * 3.0 + min(continuity * 4.0, 16.0)
    if bos != "NONE":
        strength += 12.0
    if failure != "NONE":
        strength -= 10.0
    if ext_state == int_state and ext_state in ("BULLISH", "BEARISH"):
        strength += 8.0
    strength = max(0.0, min(100.0, strength))

    if failure == "BULLISH_BREAK_FAILURE":
        structure_state = "BEARISH_FAILURE_RISK"
    elif failure == "BEARISH_BREAK_FAILURE":
        structure_state = "BULLISH_FAILURE_RISK"
    elif bos == "BULLISH":
        structure_state = "BULLISH_BOS"
    elif bos == "BEARISH":
        structure_state = "BEARISH_BOS"
    elif ext_state == "BULLISH" and int_state == "BEARISH":
        structure_state = "BULLISH_EXTERNAL_BEARISH_INTERNAL"
    elif ext_state == "BEARISH" and int_state == "BULLISH":
        structure_state = "BEARISH_EXTERNAL_BULLISH_INTERNAL"
    elif ext_state in ("BULLISH", "BEARISH"):
        structure_state = ext_state
    else:
        structure_state = "MIXED" if int_state == "MIXED" else "NEUTRAL"

    if structure_state.startswith("BULLISH"):
        bias = "BUY"
    elif structure_state.startswith("BEARISH"):
        bias = "SELL"
    elif ext_state == "BULLISH":
        bias = "BUY"
    elif ext_state == "BEARISH":
        bias = "SELL"
    else:
        bias = "NEUTRAL"

    conflicts = []
    if ext_state != int_state and ext_state in ("BULLISH", "BEARISH") and int_state in ("BULLISH", "BEARISH"):
        conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if e2.get("directional_bias") in ("BUY", "SELL") and bias in ("BUY", "SELL") and e2.get("directional_bias") != bias:
        conflicts.append("E2_STRUCTURE_DIRECTION_CONFLICT")
    if failure != "NONE":
        conflicts.append("STRUCTURAL_FAILURE_PRESENT")

    clarity = strength
    if conflicts:
        clarity -= min(20.0, 8.0 * len(conflicts))
    confidence = max(20.0, min(96.0, clarity))

    swing_map = {
        "external_highs": [{"index": i, "price": round(p, 6)} for i, p, _ in external_h[-6:]],
        "external_lows": [{"index": i, "price": round(p, 6)} for i, p, _ in external_l[-6:]],
        "internal_highs": [{"index": i, "price": round(p, 6)} for i, p, _ in internal_h[-8:]],
        "internal_lows": [{"index": i, "price": round(p, 6)} for i, p, _ in internal_l[-8:]],
    }

    observations = [
        f"External={ext_state}; Internal={int_state}",
        f"External counts HH={ext_counts['HH']} HL={ext_counts['HL']} LH={ext_counts['LH']} LL={ext_counts['LL']}",
        f"Internal counts HH={int_counts['HH']} HL={int_counts['HL']} LH={int_counts['LH']} LL={int_counts['LL']}",
        f"BOS={bos}; failure={failure}; strength={strength:.1f}",
        f"E1 state={e1.get('market_state', 'UNKNOWN')}; E2 playbook={e2.get('playbook', 'UNKNOWN')}",
    ]

    return {
        "engine": "E3",
        "question": "What does price structure say about the current opportunity?",
        "analysis_status": "COMPLETE",
        "conclusion": structure_state,
        "confidence": round(confidence, 1),
        "observations": observations,
        "structure": "BULLISH" if bias == "BUY" else "BEARISH" if bias == "SELL" else "MIXED" if "MIXED" in structure_state else "NEUTRAL",
        "structure_state": structure_state,
        "internal_structure": int_state,
        "external_structure": ext_state,
        "internal_labels": int_labels[-10:],
        "external_labels": ext_labels[-10:],
        "swing_map": swing_map,
        "HH": ext_counts["HH"], "HL": ext_counts["HL"], "LH": ext_counts["LH"], "LL": ext_counts["LL"],
        "BOS": bos,
        "bos": bos,
        "BOS_type": bos_type,
        "bos_type": bos_type,
        "BOS_level": round(bos_level, 6) if bos_level is not None else None,
        "bos_level": round(bos_level, 6) if bos_level is not None else None,
        "BOS_candle_index": bos_index,
        "structural_failure": failure,
        "failure_type": failure_type,
        "failure_level": round(failure_level, 6) if failure_level is not None else None,
        "strength": round(strength, 1),
        "structure_strength": round(strength, 1),
        "directional_bias": bias,
        "structural_bias": bias,
        "recent_high": round(_f(closed["high"].tail(30).max()), 6),
        "recent_low": round(_f(closed["low"].tail(30).min()), 6),
        "prior_high": round(_f(closed["high"].iloc[-60:-30].max()), 6),
        "prior_low": round(_f(closed["low"].iloc[-60:-30].min()), 6),
        "atr": round(atr_now, 6),
        "conflicts": conflicts,
        "evidence": observations,
        "reasoning_trace": {
            "closed_candles": len(closed),
            "internal_pivot_window": 2,
            "external_pivot_window": 4,
            "atr_prominence_threshold": 0.12,
            "bos_requires_close": True,
            "external_structure_state": ext_state,
            "internal_structure_state": int_state,
        },
    }

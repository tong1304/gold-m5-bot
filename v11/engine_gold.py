from __future__ import annotations

import os
import hashlib
import pandas as pd

from .data_quality import validate_frame
from .regime import classify_regime, _direction
from .setup_state import SetupState, can_emit_entry
from .new_gold_engines import evaluate_new_gold_engines
from .decision_priority import signal_reason

ENGINE_VERSION = "12.6-GOLD-G1-G3-H1-M15-M5-DYNAMIC-TP"
GOLD_ENGINES = ("G1", "G2", "G3")
MIN_RR = {"G1": 2.0, "G2": 2.0, "G3": 1.5}


def _stable_id(prefix, *parts):
    raw = "|".join("" if p is None else str(p).strip() for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _asof_context(frame, target_time, timeframe_minutes, max_bars=100):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out = frame.copy(); out["datetime"] = pd.to_datetime(out["datetime"], utc=True, errors="coerce")
    target = pd.Timestamp(target_time)
    target = target.tz_localize("UTC") if target.tzinfo is None else target.tz_convert("UTC")
    cutoff = target - pd.Timedelta(minutes=timeframe_minutes)
    return out.loc[out["datetime"] <= cutoff].sort_values("datetime").tail(max_bars).reset_index(drop=True)


def _finalize(payload):
    payload = dict(payload); payload["reason"] = signal_reason(payload); payload["signal_reason"] = payload["reason"]; return payload


def _setup_ids(selected, symbol, candle_time):
    engine = selected["engine"]; direction = selected["direction"]; anchor = selected.get("setup_anchor")
    sid = _stable_id("SETUP", symbol, engine, direction, round(float(anchor), 8) if anchor is not None else "NA")
    tid = _stable_id("TRIGGER", engine, direction, candle_time, selected.get("trigger_signature", ""))
    return sid, tid


def _dynamic_targets(direction, entry, primary_tp, m15, h1):
    """Build up to three structure/liquidity targets: engine target, M15, H1."""
    if direction == "BUY":
        def levels(frame):
            if frame is None or frame.empty: return []
            return sorted({float(v) for v in frame.high.tail(100) if float(v) > entry})
        candidates = [float(primary_tp)] + levels(m15) + levels(h1)
        ordered = []
        for p in sorted(candidates):
            if p > entry and not ordered or (p > entry and abs(p-ordered[-1]) > 1e-9): ordered.append(p)
    else:
        def levels(frame):
            if frame is None or frame.empty: return []
            return sorted({float(v) for v in frame.low.tail(100) if float(v) < entry}, reverse=True)
        candidates = [float(primary_tp)] + levels(m15) + levels(h1)
        ordered = []
        for p in candidates:
            if p < entry and not ordered or (p < entry and abs(p-ordered[-1]) > 1e-9): ordered.append(p)
        ordered = sorted(ordered, reverse=True)
    # Keep the engine's own target as TP1; choose the furthest useful HTF targets after it.
    if direction == "BUY": ordered = sorted(set(ordered));
    else: ordered = sorted(set(ordered), reverse=True)
    if not ordered: return [float(primary_tp)]
    tp1 = float(primary_tp)
    if direction == "BUY":
        higher = [p for p in ordered if p > tp1 * (1 + 1e-10)]
        return [tp1] + higher[:2]
    lower = [p for p in ordered if p < tp1 * (1 - 1e-10)]
    return [tp1] + lower[:2]


def _trade_levels(selected, m15, h1):
    ev = selected.get("evidence") or {}; entry = float(ev.get("entry_price", 0) or 0); sl = float(ev.get("sl_price", 0) or 0); primary = float(ev.get("tp_price", ev.get("tp2", ev.get("tp1", 0))) or 0)
    minimum = MIN_RR.get(selected.get("engine"), 2.0)
    if entry <= 0 or sl <= 0 or primary <= 0: return {"valid": False, "reason": "ENGINE_LEVELS_UNAVAILABLE"}
    risk = abs(entry - sl)
    if risk <= 0: return {"valid": False, "reason": "ZERO_RISK"}
    if selected["direction"] == "BUY" and not sl < entry: return {"valid": False, "reason": "INVALID_BUY_LEVELS"}
    if selected["direction"] == "SELL" and not sl > entry: return {"valid": False, "reason": "INVALID_SELL_LEVELS"}
    tps = _dynamic_targets(selected["direction"], entry, primary, m15, h1)
    valid_tps = [p for p in tps if abs(p-entry)/risk >= minimum]
    if not valid_tps: return {"valid": False, "reason": "RR_BELOW_MINIMUM", "target_rr": minimum}
    allocations = [40, 35, 25][:len(valid_tps)]
    if len(allocations) == 1: allocations = [100]
    elif len(allocations) == 2: allocations = [50, 50]
    tp_levels = [{"price": p, "risk_reward": abs(p-entry)/risk, "type": f"TP{i+1}", "allocation_pct": allocations[i]} for i,p in enumerate(valid_tps)]
    return {"valid": True, "entry": entry, "sl": sl, "tp": valid_tps[-1], "tp1": valid_tps[0], "tp2": valid_tps[1] if len(valid_tps)>1 else None, "tp3": valid_tps[2] if len(valid_tps)>2 else None, "risk": risk, "risk_reward": tp_levels[-1]["risk_reward"], "effective_rr": tp_levels[-1]["risk_reward"], "minimum_rr": minimum, "target_rr": minimum, "tp_levels": tp_levels, "tp_count": len(tp_levels), "tp_allocations": allocations, "tp_structure_levels": valid_tps, "tp_selection": "DYNAMIC_M5_M15_H1_LIQUIDITY"}


def analyze(m5, m15=None, symbol=None, index=None, setup_state=None, h1=None):
    if index is not None: m5 = m5.iloc[:index + 1].reset_index(drop=True)
    m5 = m5.reset_index(drop=True)
    q5 = validate_frame(m5, minimum=60, timeframe_minutes=5, market=symbol)
    if len(m5):
        trigger_time = pd.to_datetime(m5.iloc[-1]["datetime"], utc=True); m15 = _asof_context(m15, trigger_time, 15); h1 = _asof_context(h1, trigger_time, 60)
    q15 = validate_frame(m15, minimum=60, timeframe_minutes=15, market=symbol) if m15 is not None else ["M15_CONTEXT_REQUIRED"]
    q1 = validate_frame(h1, minimum=60, timeframe_minutes=60, market=symbol) if h1 is not None else ["H1_CONTEXT_REQUIRED"]
    base = {"engine_version": ENGINE_VERSION, "symbol": symbol, "live_orders_allowed": False, "analysis_window": {"m5_context_bars": 100, "m15_context_bars": 100, "h1_context_bars": 100, "timeframe_mode": "MTF:H1→M15→M5", "alignment": "H1/M15 closed before M5 trigger"}}
    if q5 or q15 or q1: return _finalize({**base, "valid": False, "signal": "NO_TRADE", "strategy": "NONE", "allowed_engines": list(GOLD_ENGINES), "rejection_reasons": q5+q15+q1, "trade_levels": {"valid": False}, "data_quality": {"m5": q5, "m15": q15, "h1": q1}})
    regime = classify_regime(m5, m15, h1)
    # M15 regime is diagnostic metadata only. It is NOT an entry filter.
    regime["m15_regime_filter_enabled"] = False
    regime["m15_bias_only"] = True
    base.update({"regime": regime, "m5_trend": {"direction": _direction(m5), "bars": min(100, len(m5))}, "h1_bias": regime.get("h1_bias"), "h1_gate": regime.get("h1_gate"), "m15_regime": regime.get("m15_regime"), "m15_role": "TREND_BIAS_ONLY", "allowed_engines": list(GOLD_ENGINES)})
    candidates, trace = evaluate_new_gold_engines(m5, m15, h1, regime)
    base["decision_trace"] = trace
    if not candidates: return _finalize({**base, "valid": False, "signal": "NO_TRADE", "strategy": "NONE", "setup_candidates": [], "selected_setup": None, "rejection_reasons": ["NO_ALLOWED_G1_G2_G3_SETUP"], "trade_levels": {"valid": False}})
    selected = candidates[0]
    sid, tid = _setup_ids(selected, symbol, str(m5.iloc[-1].get("datetime", "")))
    selected = {**selected, "setup_id": sid, "trigger_id": tid, "symbol": symbol}
    score = selected.get("score_detail") or {"score": selected.get("quality", 0), "qualified": True}
    base.update({"setup_candidates": candidates, "selected_setup": selected, "strategy": selected["strategy"], "engine": selected["engine"], "setup_id": sid, "trigger_id": tid, "setup_score": score})
    if not score.get("qualified"): return _finalize({**base, "valid": False, "signal": "NO_TRADE", "entry_type": None, "rejection_reasons": ["SETUP_SCORE_BELOW_THRESHOLD"], "trade_levels": {"valid": False}})
    state = setup_state if isinstance(setup_state, SetupState) else SetupState(); max_reentries = int(os.getenv("MAX_REENTRIES_PER_SETUP", "2")); emit, entry_type = can_emit_entry(state, sid, tid, max_reentries=max_reentries)
    if not emit: return _finalize({**base, "valid": False, "signal": "NO_TRADE", "entry_type": entry_type, "rejection_reasons": [entry_type], "trade_levels": {"valid": False}})
    levels = _trade_levels(selected, m15, h1)
    if not levels.get("valid"): return _finalize({**base, "valid": False, "signal": "NO_TRADE", "entry_type": entry_type, "rejection_reasons": [levels.get("reason", "INVALID_RISK_OR_RR")], "trade_levels": levels, "rr_target": levels.get("target_rr", MIN_RR.get(selected["engine"], 2.0))})
    return _finalize({**base, "valid": True, "signal": selected["direction"], "direction": selected["direction"], "strategy": selected["strategy"], "engine": selected["engine"], "entry_type": entry_type, "setup_id": sid, "trigger_id": tid, "trade_levels": levels, "risk_engine": {"method": "DYNAMIC_M5_M15_H1_LIQUIDITY", "risk_reward": levels["risk_reward"], "minimum_rr": levels["minimum_rr"]}, "rr_target": levels["minimum_rr"], "rejection_reasons": [], "data_quality": {"m5": [], "m15": [], "h1": []}, "setup_state": {"reentries_used": state.reentry_count(sid), "max_reentries": max_reentries}, "live_orders_allowed": False})

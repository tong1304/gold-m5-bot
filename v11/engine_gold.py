from __future__ import annotations

import os
import hashlib
import pandas as pd

from .data_quality import validate_frame
from .regime import classify_regime, _direction
from .risk import calculate as calculate_risk, min_rr_for_strategy
from .setup_state import SetupState, can_emit_entry
from .gold_engines import evaluate_gold_engines
from .strategy_engine import signal_reason

ENGINE_VERSION = "12.4-MTF-H1-HARD-GATE-M15-M5-BTC-B1-B3-GOLD-G1-G5"
GOLD_ENGINES = ("G1", "G2", "G3", "G4", "G5")


def _stable_id(prefix, *parts):
    raw = "|".join("" if p is None else str(p).strip() for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _asof_context(frame, target_time, timeframe_minutes, max_bars=100):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out = frame.copy()
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True, errors="coerce")
    target = pd.Timestamp(target_time)
    if target.tzinfo is None:
        target = target.tz_localize("UTC")
    else:
        target = target.tz_convert("UTC")
    cutoff = target - pd.Timedelta(minutes=timeframe_minutes)
    return out.loc[out["datetime"] <= cutoff].sort_values("datetime").tail(max_bars).reset_index(drop=True)


def _finalize(payload):
    payload = dict(payload)
    payload["reason"] = signal_reason(payload)
    payload["signal_reason"] = payload["reason"]
    return payload


def _setup_ids(selected, symbol, regime, candle_time):
    engine = selected["engine"]
    direction = selected["direction"]
    anchor = selected.get("setup_anchor")
    setup_id = _stable_id("SETUP", symbol, regime, engine, direction, round(float(anchor), 8) if anchor is not None else "NA")
    trigger_id = _stable_id("TRIGGER", engine, direction, candle_time, selected.get("trigger_signature", ""))
    return setup_id, trigger_id


def _levels_ready(levels, direction, strategy):
    try:
        entry = float(levels["entry"])
        sl = float(levels["sl"])
        tp = float(levels["tp"])
        rr = float(levels["risk_reward"])
        minimum = float(min_rr_for_strategy(strategy))
        return bool(levels.get("valid")) and rr >= minimum and ((direction == "BUY" and sl < entry < tp) or (direction == "SELL" and tp < entry < sl))
    except (KeyError, TypeError, ValueError):
        return False


def analyze(m5, m15=None, symbol=None, index=None, setup_state=None, h1=None):
    if index is not None:
        m5 = m5.iloc[: index + 1].reset_index(drop=True)
    m5 = m5.reset_index(drop=True)
    q5 = validate_frame(m5, minimum=60, timeframe_minutes=5, market=symbol)
    if len(m5):
        trigger_time = pd.to_datetime(m5.iloc[-1]["datetime"], utc=True)
        m15 = _asof_context(m15, trigger_time, 15, 100)
        h1 = _asof_context(h1, trigger_time, 60, 100)
    q15 = validate_frame(m15, minimum=60, timeframe_minutes=15, market=symbol) if m15 is not None else ["M15_CONTEXT_REQUIRED"]
    q1 = validate_frame(h1, minimum=60, timeframe_minutes=60, market=symbol) if h1 is not None else ["H1_CONTEXT_REQUIRED"]
    base = {
        "engine_version": ENGINE_VERSION,
        "symbol": symbol,
        "live_orders_allowed": False,
        "analysis_window": {
            "m5_context_bars": 100,
            "m15_context_bars": 100,
            "h1_context_bars": 100,
            "timeframe_mode": "MTF:H1→M15→M5",
            "alignment": "H1/M15 closed before M5 trigger",
        },
    }
    if q5 or q15 or q1:
        return _finalize({**base, "valid": False, "signal": "NO_TRADE", "strategy": "NONE", "regime": None,
                          "allowed_engines": list(GOLD_ENGINES), "rejection_reasons": q5 + q15 + q1,
                          "trade_levels": {"valid": False}, "data_quality": {"m5": q5, "m15": q15, "h1": q1}})

    regime = classify_regime(m5, m15, h1)
    base.update({
        "regime": regime,
        "m5_trend": {"direction": _direction(m5), "bars": min(100, len(m5))},
        "h1_bias": regime.get("h1_bias"),
        "h1_gate": regime.get("h1_gate"),
        "m15_regime": regime.get("m15_regime"),
        "allowed_engines": list(GOLD_ENGINES),
    })

    candidates, trace = evaluate_gold_engines(m5, m15, h1, regime)
    base["decision_trace"] = trace
    if not candidates:
        return _finalize({**base, "valid": False, "signal": "NO_TRADE", "strategy": "NONE",
                          "setup_candidates": [], "selected_setup": None,
                          "rejection_reasons": ["NO_ALLOWED_GOLD_G_ENGINE_SETUP"],
                          "trade_levels": {"valid": False}})

    selected = candidates[0]
    setup_id, trigger_id = _setup_ids(selected, symbol, regime.get("regime", "UNKNOWN"), str(m5.iloc[-1].get("datetime", "")))
    selected = {**selected, "setup_id": setup_id, "trigger_id": trigger_id,
                "regime": regime.get("regime"), "symbol": symbol}
    score = selected.get("score_detail") or {}
    base.update({
        "setup_candidates": candidates,
        "selected_setup": selected,
        "strategy": selected["strategy"],
        "engine": selected["engine"],
        "setup_id": setup_id,
        "trigger_id": trigger_id,
        "setup_score": score,
    })
    if not score.get("qualified"):
        return _finalize({**base, "valid": False, "signal": "NO_TRADE", "entry_type": None,
                          "rejection_reasons": ["SETUP_SCORE_BELOW_THRESHOLD"], "trade_levels": {"valid": False}})

    state = setup_state if isinstance(setup_state, SetupState) else SetupState()
    max_reentries = int(os.getenv("MAX_REENTRIES_PER_SETUP", "2"))
    emit, entry_type = can_emit_entry(state, setup_id, trigger_id, max_reentries=max_reentries)
    if not emit:
        return _finalize({**base, "valid": False, "signal": "NO_TRADE", "entry_type": entry_type,
                          "rejection_reasons": [entry_type], "trade_levels": {"valid": False}})

    strategy = selected["strategy"].split("_", 1)[1] if selected["strategy"].startswith("G") else selected["strategy"]
    levels = calculate_risk(m5, selected["direction"], strategy, selected.get("evidence"), rr=min_rr_for_strategy(strategy))
    actual_rr = float(levels.get("risk_reward", levels.get("effective_rr", 0)) or 0)
    target_rr = float(min_rr_for_strategy(strategy))
    if not levels.get("valid") or actual_rr < target_rr:
        return _finalize({**base, "valid": False, "signal": "NO_TRADE", "entry_type": entry_type,
                          "rejection_reasons": [levels.get("reason", "INVALID_RISK_OR_RR")],
                          "trade_levels": levels, "rr_target": target_rr})

    return _finalize({**base, "valid": True, "signal": selected["direction"],
                      "direction": selected["direction"], "strategy": selected["strategy"],
                      "engine": selected["engine"], "entry_type": entry_type,
                      "setup_id": setup_id, "trigger_id": trigger_id,
                      "trade_levels": levels,
                      "risk_engine": {"method": "GOLD_G_SERIES+STRUCTURE+ATR",
                                      "risk_reward": levels.get("risk_reward"), "minimum_rr": target_rr},
                      "rr_target": target_rr, "rejection_reasons": [],
                      "data_quality": {"m5": [], "m15": [], "h1": []},
                      "setup_state": {"reentries_used": state.reentry_count(setup_id), "max_reentries": max_reentries},
                      "live_orders_allowed": False})

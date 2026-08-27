"""Production-V2 E4 — Professional Liquidity Brain.

E4 is standalone and analysis-only. Legacy 4A-4F specialists remain present
but are PAUSED and are not executed by this entrypoint. E4 may reinterpret
qualitative E1-E3 evidence, never their score, gate, or trade decision.
E9 remains the sole trade-decision authority.
"""
from __future__ import annotations
from math import isfinite
from typing import Any, Iterable

_EPS = 1e-9
_FORBIDDEN = {"decision", "trade_decision", "decision_score", "score", "gate", "gate_passed", "specialist_gate"}


def _num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _get(bar: Any, *names: str) -> float | None:
    if isinstance(bar, dict):
        for name in names:
            if name in bar:
                value = _num(bar[name])
                if value is not None:
                    return value
            lower = name.lower()
            for key, raw in bar.items():
                if str(key).lower() == lower:
                    value = _num(raw)
                    if value is not None:
                        return value
    else:
        for name in names:
            value = _num(getattr(bar, name, None))
            if value is not None:
                return value
    return None


def _clean_bars(bars: Iterable[Any]) -> list[dict[str, float]]:
    result = []
    for bar in bars:
        o, h, l, c = (_get(bar, n) for n in ("open", "high", "low", "close"))
        if None not in (o, h, l, c) and h >= l:
            result.append({"open": o, "high": h, "low": l, "close": c})
    return result


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        trs.append(max(b["high"] - b["low"], abs(b["high"] - p["close"]), abs(b["low"] - p["close"])))
    sample = trs[-period:]
    return sum(sample) / len(sample) if sample else 0.0


def _pivot_levels(bars: list[dict[str, float]], lookback: int = 2):
    highs, lows = [], []
    if len(bars) < lookback * 2 + 1:
        return highs, lows
    for i in range(lookback, len(bars) - lookback):
        window = bars[i - lookback:i + lookback + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append(bars[i]["low"])
    return highs, lows


def _cluster(levels: list[float], tolerance: float):
    if not levels:
        return []
    groups: list[list[float]] = []
    for level in sorted(levels):
        if not groups or abs(level - sum(groups[-1]) / len(groups[-1])) > max(tolerance, _EPS):
            groups.append([level])
        else:
            groups[-1].append(level)
    return [{"zone_id": f"L{i}", "price": sum(g) / len(g), "lower": min(g), "upper": max(g), "touches": len(g), "type": "CLUSTERED_LIQUIDITY" if len(g) > 1 else "SWING_LIQUIDITY"} for i, g in enumerate(groups, 1)]


def _evidence_values(evidence_bus):
    result = {}
    for engine_id in ("E1", "E2", "E3"):
        package = (evidence_bus or {}).get(engine_id)
        if not isinstance(package, dict):
            continue
        evidence = package.get("evidence") or package.get("output") or {}
        if not isinstance(evidence, dict):
            continue
        output = evidence.get("output") if isinstance(evidence.get("output"), dict) else evidence
        result[engine_id] = {k: v for k, v in output.items() if str(k).lower() not in _FORBIDDEN}
    return result


def _iter_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_values(item)
    elif isinstance(value, str):
        yield value.upper().strip()


def _direction_hint(values):
    found = {v for v in _iter_values(values) if v in {"BULLISH", "BEARISH", "UP", "DOWN", "BUY", "SELL", "LONG", "SHORT"}}
    down, up = found & {"BEARISH", "DOWN", "SELL", "SHORT"}, found & {"BULLISH", "UP", "BUY", "LONG"}
    if down and up:
        return "CONFLICTING"
    if down:
        return "DOWN"
    if up:
        return "UP"
    return "UNRESOLVED"


def _base(status="COMPLETE"):
    return {"architecture": "E4_PROFESSIONAL_LIQUIDITY_BRAIN_V1", "analysis_status": status, "sub_engines_active": False, "sub_engines_status": "PAUSED", "specialists": {}, "decision_authority": "E9_ONLY", "trade_decision_authority": False, "decision": None, "gate": None, "score": None, "reasoning_role": "LIQUIDITY_ANALYST", "question": "Where is liquidity and what did price do with it?"}


def analyze_e4(bars: Iterable[Any], evidence_bus=None):
    data = _clean_bars(bars)
    if not data:
        out = _base("INSUFFICIENT_DATA")
        out.update({"finding": "NO_VALID_MARKET_DATA", "liquidity_state": "UNRESOLVED", "event": "NONE", "observations": [], "reasons": ["E4_NO_VALID_BARS"], "reason_codes": ("E4_NO_VALID_BARS",), "confidence": 0.0})
        return out

    atr = _atr(data)
    last = data[-1]
    tol = max(atr * 0.12, (last["high"] - last["low"]) * 0.15, _EPS)
    pivot_highs, pivot_lows = _pivot_levels(data[-250:], 2)
    external_high = max(b["high"] for b in data[:-1]) if len(data) > 1 else last["high"]
    external_low = min(b["low"] for b in data[:-1]) if len(data) > 1 else last["low"]
    high_zones = _cluster(pivot_highs + [external_high], tol)
    low_zones = _cluster(pivot_lows + [external_low], tol)

    prior_high = max(b["high"] for b in data[-21:-1]) if len(data) > 21 else max(b["high"] for b in data[:-1])
    prior_low = min(b["low"] for b in data[-21:-1]) if len(data) > 21 else min(b["low"] for b in data[:-1])
    swept_high = last["high"] > prior_high + _EPS
    swept_low = last["low"] < prior_low - _EPS
    body = abs(last["close"] - last["open"])
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    bearish_rejection = swept_high and last["close"] < prior_high and upper_wick >= max(body * 0.8, tol * 0.25)
    bullish_rejection = swept_low and last["close"] > prior_low and lower_wick >= max(body * 0.8, tol * 0.25)
    acceptance_high = swept_high and last["close"] > prior_high
    acceptance_low = swept_low and last["close"] < prior_low

    if bearish_rejection and bullish_rejection:
        event, implication = "CONFLICTING_SWEEP", "UNRESOLVED"
    elif bearish_rejection:
        event, implication = "HIGH_SWEEP_REJECTION", "DOWN"
    elif bullish_rejection:
        event, implication = "LOW_SWEEP_REJECTION", "UP"
    elif acceptance_high:
        event, implication = "HIGH_ACCEPTANCE", "UP"
    elif acceptance_low:
        event, implication = "LOW_ACCEPTANCE", "DOWN"
    elif swept_high:
        event, implication = "HIGH_LIQUIDITY_PENETRATION", "UNRESOLVED"
    elif swept_low:
        event, implication = "LOW_LIQUIDITY_PENETRATION", "UNRESOLVED"
    else:
        event, implication = "NO_CONFIRMED_LIQUIDITY_EVENT", "UNRESOLVED"

    evidence = _evidence_values(evidence_bus)
    contextual_hint = _direction_hint(evidence)
    conflicts = []
    if contextual_hint not in {"UNRESOLVED", "CONFLICTING", implication} and implication != "UNRESOLVED":
        conflicts.append("UPSTREAM_CONTEXT_DISAGREES_WITH_LIQUIDITY_EVENT")

    freshness = min(1.0, len(data[-60:]) / 60.0)
    cluster_bonus = min(1.0, (len(high_zones) + len(low_zones)) / 8.0)
    event_strength = 1.0 if event in {"HIGH_SWEEP_REJECTION", "LOW_SWEEP_REJECTION", "HIGH_ACCEPTANCE", "LOW_ACCEPTANCE"} else 0.55 if "PENETRATION" in event else 0.25
    confidence = round(100.0 * (0.40 * event_strength + 0.30 * cluster_bonus + 0.20 * freshness + 0.10 * (1.0 if atr > 0 else 0.0)), 2)
    observations = [f"liquidity_high_zones={len(high_zones)}", f"liquidity_low_zones={len(low_zones)}", f"swept_high={swept_high}", f"swept_low={swept_low}", f"rejection_high={bearish_rejection}", f"rejection_low={bullish_rejection}", f"acceptance_high={acceptance_high}", f"acceptance_low={acceptance_low}", f"event={event}", f"directional_implication={implication}", f"atr14={round(atr, 8)}"]
    reasons = ["E4_LIQUIDITY_ANALYSIS_COMPLETE"] + conflicts

    out = _base()
    out.update({"finding": event, "liquidity_state": "EVENT_DETECTED" if event != "NO_CONFIRMED_LIQUIDITY_EVENT" else "LIQUIDITY_MAPPED", "event": event, "directional_implication": implication, "contextual_direction_hint": contextual_hint, "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones, "external_high": external_high, "external_low": external_low, "atr": atr, "tolerance": tol}, "interaction": {"swept_high": swept_high, "swept_low": swept_low, "rejection_high": bearish_rejection, "rejection_low": bullish_rejection, "acceptance_high": acceptance_high, "acceptance_low": acceptance_low}, "liquidity_strength": confidence, "confidence": round(confidence / 100.0, 4), "observations": observations, "reasons": reasons, "reason_codes": tuple(reasons), "evidence": {"source_engines": sorted(evidence), "decisions_used": False, "gates_used": False, "scores_used": False, "raw_market_data_used": True}, "conflicts": conflicts})
    return out


__all__ = ["analyze_e4"]

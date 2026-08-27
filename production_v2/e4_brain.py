"""Production-V2 E4 — Professional Liquidity Brain.

E4 is a standalone, analysis-only brain. The legacy 4A-4F specialists remain
present in the repository but are intentionally PAUSED and are not executed by
this entrypoint. E4 may reinterpret qualitative evidence from E1-E3, but it
never consumes their score, gate, or trade decision.

Decision boundary: liquidity interpretation only. E9 remains the sole trade
decision authority.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Iterable

_EPS = 1e-9


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
        o = _get(bar, "open", "o")
        h = _get(bar, "high", "h")
        l = _get(bar, "low", "l")
        c = _get(bar, "close", "c")
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


def _pivot_levels(bars: list[dict[str, float]], lookback: int = 3) -> tuple[list[float], list[float]]:
    highs, lows = [], []
    if len(bars) < lookback * 2 + 1:
        return highs, lows
    for i in range(lookback, len(bars) - lookback):
        h = bars[i]["high"]
        l = bars[i]["low"]
        if h >= max(x["high"] for x in bars[i - lookback:i + lookback + 1]):
            highs.append(h)
        if l <= min(x["low"] for x in bars[i - lookback:i + lookback + 1]):
            lows.append(l)
    return highs, lows


def _cluster(levels: list[float], tolerance: float) -> list[dict[str, Any]]:
    if not levels:
        return []
    groups: list[list[float]] = []
    for level in sorted(levels):
        if not groups or abs(level - sum(groups[-1]) / len(groups[-1])) > max(tolerance, _EPS):
            groups.append([level])
        else:
            groups[-1].append(level)
    zones = []
    for idx, group in enumerate(groups, 1):
        zones.append({
            "zone_id": f"L{idx}",
            "price": sum(group) / len(group),
            "lower": min(group),
            "upper": max(group),
            "touches": len(group),
            "type": "CLUSTERED_LIQUIDITY" if len(group) > 1 else "SWING_LIQUIDITY",
        })
    return zones


def _evidence_values(evidence_bus: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    forbidden = {"decision", "trade_decision", "decision_score", "score", "gate", "gate_passed", "specialist_gate"}
    for engine_id in ("E1", "E2", "E3"):
        package = (evidence_bus or {}).get(engine_id)
        if not isinstance(package, dict):
            continue
        evidence = package.get("evidence") or package.get("output") or {}
        if isinstance(evidence, dict):
            output = evidence.get("output") if isinstance(evidence.get("output"), dict) else evidence
            result[engine_id] = {k: v for k, v in output.items() if str(k).lower() not in forbidden}
    return result


def _iter_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_values(item)
    elif isinstance(value, str):
        yield value.upper().strip()


def _direction_hint(values: dict[str, Any]) -> str:
    directional = {"BULLISH", "BEARISH", "UP", "DOWN", "BUY", "SELL", "LONG", "SHORT"}
    found = {v for v in _iter_values(values) if v in directional}
    if found & {"BEARISH", "DOWN", "SELL", "SHORT"} and found & {"BULLISH", "UP", "BUY", "LONG"}:
        return "CONFLICTING"
    if found & {"BEARISH", "DOWN", "SELL", "SHORT"}:
        return "DOWN"
    if found & {"BULLISH", "UP", "BUY", "LONG"}:
        return "UP"
    return "UNRESOLVED"


def analyze_e4(bars: Iterable[Any], evidence_bus: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reconstruct the liquidity map and current interaction from closed candles."""
    data = _clean_bars(bars)
    if not data:
        return {
            "architecture": "E4_PROFESSIONAL_LIQUIDITY_BRAIN_V1",
            "analysis_status": "INSUFFICIENT_DATA",
            "liquidity_state": "UNRESOLVED",
            "event": "NONE",
            "liquidity_map": {},
            "confidence": 0.0,
            "reason_codes": ("E4_NO_VALID_BARS",),
            "reasoning_role": "LIQUIDITY_ANALYST",
        }

    atr = _atr(data)
    last = data[-1]
    tol = max(atr * 0.12, (last["high"] - last["low"]) * 0.15, _EPS)
    pivot_highs, pivot_lows = _pivot_levels(data[-250:], 2)
    recent = data[-60:]
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

    freshness = min(1.0, len(recent) / 60.0)
    cluster_bonus = min(1.0, (len(high_zones) + len(low_zones)) / 8.0)
    event_strength = 1.0 if event in {"HIGH_SWEEP_REJECTION", "LOW_SWEEP_REJECTION", "HIGH_ACCEPTANCE", "LOW_ACCEPTANCE"} else 0.55 if event.endswith("PENETRATION") else 0.25
    confidence = round(100.0 * (0.40 * event_strength + 0.30 * cluster_bonus + 0.20 * freshness + 0.10 * (1.0 if atr > 0 else 0.0)), 2)

    evidence = _evidence_values(evidence_bus)
    contextual_hint = _direction_hint(evidence)
    conflicts = []
    if contextual_hint not in {"UNRESOLVED", "CONFLICTING", implication} and implication != "UNRESOLVED":
        conflicts.append("UPSTREAM_CONTEXT_DISAGREES_WITH_LIQUIDITY_EVENT")

    return {
        "architecture": "E4_PROFESSIONAL_LIQUIDITY_BRAIN_V1",
        "analysis_status": "COMPLETE",
        "sub_engines_active": False,
        "sub_engines_status": "PAUSED",
        "decision_authority": "E9_ONLY",
        "trade_decision_authority": False,
        "reasoning_role": "LIQUIDITY_ANALYST",
        "question": "Where is liquidity and what did price do with it?",
        "liquidity_state": "EVENT_DETECTED" if event != "NO_CONFIRMED_LIQUIDITY_EVENT" else "LIQUIDITY_MAPPED",
        "event": event,
        "directional_implication": implication,
        "contextual_direction_hint": contextual_hint,
        "liquidity_map": {
            "high_zones": high_zones,
            "low_zones": low_zones,
            "external_high": external_high,
            "external_low": external_low,
            "atr": atr,
            "tolerance": tol,
        },
        "interaction": {
            "swept_high": swept_high,
            "swept_low": swept_low,
            "rejection_high": bearish_rejection,
            "rejection_low": bullish_rejection,
            "acceptance_high": acceptance_high,
            "acceptance_low": acceptance_low,
        },
        "liquidity_strength": round(confidence, 2),
        "confidence": round(confidence / 100.0, 4),
        "evidence": {
            "source_engines": sorted(evidence),
            "decisions_used": False,
            "gates_used": False,
            "scores_used": False,
            "raw_market_data_used": True,
        },
        "conflicts": conflicts,
        "reason_codes": tuple(["E4_LIQUIDITY_ANALYSIS_COMPLETE"] + conflicts),
    }


__all__ = ["analyze_e4"]

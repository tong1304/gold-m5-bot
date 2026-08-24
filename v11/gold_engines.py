from __future__ import annotations

from .strategies.gold import REGISTRY

# GOLD uses only the dedicated G-series. Legacy E1-E8 engines are intentionally
# not called from this module.
GOLD_ENGINE_MAP = {
    "G1": ("TREND_PULLBACK", REGISTRY["TREND_PULLBACK"]),
    "G2": ("BREAKOUT_RETEST", REGISTRY["BREAKOUT_RETEST"]),
    "G3": ("LIQUIDITY_SWEEP", REGISTRY["LIQUIDITY_SWEEP"]),
    "G4": ("VWAP_MOMENTUM_PULLBACK", REGISTRY["VWAP_MOMENTUM_PULLBACK"]),
    "G5": ("OPENING_RANGE_BREAKOUT", REGISTRY["OPENING_RANGE_BREAKOUT"]),
}

GOLD_ENGINE_NAMES = {k: v[0] for k, v in GOLD_ENGINE_MAP.items()}
GOLD_ENGINE_PRIORITY = {"G1": 0, "G2": 1, "G3": 2, "G4": 3, "G5": 4}


def _candidate_directions(regime):
    bias = str(regime.get("h1_bias") or "NEUTRAL").upper()
    m15 = regime.get("m15_context") or {}
    m15_direction = str(m15.get("direction") or "NEUTRAL").upper()
    direction = str(regime.get("direction") or "NEUTRAL").upper()
    if bias in ("BUY", "SELL"):
        return [bias]
    if m15_direction in ("BUY", "SELL"):
        return [m15_direction]
    if direction in ("BUY", "SELL"):
        return [direction]
    return ["BUY", "SELL"]


def _context(regime):
    # G3 needs the full HTF gate: H1 bias + M15 context/POI.
    return {
        "h1_bias": regime.get("h1_bias") or "NEUTRAL",
        "h1_poi": regime.get("h1_poi"),
        "poi": regime.get("poi"),
        "m15": regime.get("m15_context") or {},
        "opening_range_minutes": 30,
    }


def _convert(gid, strategy, result, direction):
    evidence = dict(result.evidence or {})
    anchor = evidence.get("setup_anchor")
    if anchor is None:
        anchor = evidence.get("support") if direction == "BUY" else evidence.get("resistance")
    return {
        "status": result.status,
        "engine": gid,
        "strategy": f"{gid}_{strategy}",
        "direction": direction,
        "setup_anchor": anchor,
        "evidence": evidence,
        "quality": float(result.quality or 0.0),
        "trigger_signature": f"{gid}|{strategy}|{direction}|{evidence.get('setup_anchor', anchor)}",
        "entry_type_hint": "MARKET",
        "rejection_reasons": list(result.reasons or ()),
    }


def evaluate_gold_engines(m5, m15, h1, regime):
    candidates = []
    trace = []
    ctx = _context(regime)
    for gid, (strategy, fn) in GOLD_ENGINE_MAP.items():
        for direction in _candidate_directions(regime):
            try:
                result = fn(m5, direction, ctx)
                converted = _convert(gid, strategy, result, direction)
            except Exception as exc:
                converted = {
                    "status": "FAIL",
                    "engine": gid,
                    "strategy": f"{gid}_{strategy}",
                    "direction": direction,
                    "quality": 0.0,
                    "rejection_reasons": [f"GOLD_ENGINE_ERROR:{type(exc).__name__}:{exc}"],
                }
            trace.append(converted)
            if converted.get("status") == "PASS":
                # Dedicated G-series is scored independently of the legacy E-series.
                score = min(100.0, max(0.0, float(converted.get("quality", 0.0))))
                if strategy in ("TREND_PULLBACK", "VWAP_MOMENTUM_PULLBACK") and regime.get("m15_regime") == "TREND":
                    score = min(100.0, score + 5.0)
                if strategy in ("BREAKOUT_RETEST", "OPENING_RANGE_BREAKOUT") and regime.get("m15_regime") in ("TRANSITION", "TREND"):
                    score = min(100.0, score + 3.0)
                converted["score_detail"] = {
                    "score": round(score, 2),
                    "qualified": score >= 70.0,
                    "components": {"gold_engine_quality": float(converted.get("quality", 0.0))},
                }
                candidates.append(converted)
    candidates.sort(key=lambda r: (
        GOLD_ENGINE_PRIORITY.get(str(r.get("engine")).upper(), 99),
        -float((r.get("score_detail") or {}).get("score", 0) or 0),
        -float(r.get("quality", 0) or 0),
    ))
    return candidates, trace

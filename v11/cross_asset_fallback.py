from __future__ import annotations

from .asset_strategies import evaluate_asset_strategies, MIN_RR, STRATEGY_NAMES
from .regime import ASSET_STRATEGY_REGIMES

ASSET_ORDER = ("GOLD", "BTC")


def _normal_asset(asset: str) -> str:
    asset = str(asset or "").upper()
    if asset in ("XAU", "XAUUSD", "XAU/USD", "XAU/USDT"):
        return "GOLD"
    if asset in ("BTCUSD", "BTC/USD", "BTC/USDT"):
        return "BTC"
    return asset


def cross_asset_strategy_ids(target_asset: str, regime: str) -> list[str]:
    """Return compatible strategies from the other asset for the same M5 regime."""
    target = _normal_asset(target_asset)
    regime = str(regime or "").upper()
    source = next((asset for asset in ASSET_ORDER if asset != target), None)
    if source is None:
        return []
    return [
        engine
        for engine, profile in ASSET_STRATEGY_REGIMES.items()
        if profile.get("asset") == source and regime in profile.get("regimes", set())
    ]


def cross_asset_compatible(target_asset: str, source_asset: str, engine: str, regime: str) -> tuple[bool, str]:
    target = _normal_asset(target_asset)
    source = _normal_asset(source_asset)
    engine = str(engine or "").upper()
    regime = str(regime or "").upper()
    if target == source:
        return False, "SOURCE_ASSET_EQUALS_TARGET_ASSET"
    profile = ASSET_STRATEGY_REGIMES.get(engine)
    if not profile:
        return False, "UNKNOWN_STRATEGY"
    if profile.get("asset") != source:
        return False, "STRATEGY_SOURCE_ASSET_MISMATCH"
    if regime not in profile.get("regimes", set()):
        return False, "REGIME_NOT_COMPATIBLE"
    return True, "CROSS_ASSET_REGIME_COMPATIBLE"


def evaluate_cross_asset_fallback(target_asset, m5, regime):
    """Evaluate the other asset's regime-compatible strategies on target-asset M5 data."""
    target = _normal_asset(target_asset)
    source = next((asset for asset in ASSET_ORDER if asset != target), None)
    current_regime = str((regime or {}).get("m5_regime") or (regime or {}).get("regime") or "TRANSITION").upper()
    if source is None:
        return [], [{"status": "NO_FALLBACK", "reason": "NO_SOURCE_ASSET"}]

    allowed = set(cross_asset_strategy_ids(target, current_regime))
    if not allowed:
        return [], [{"status": "NO_FALLBACK", "target_asset": target, "source_asset": source, "regime": current_regime, "reason": "NO_CROSS_ASSET_STRATEGY_FOR_REGIME"}]

    candidates, native_trace = evaluate_asset_strategies(source, m5, regime)
    out = []
    trace = [{
        "status": "CROSS_ASSET_FALLBACK",
        "target_asset": target,
        "source_asset": source,
        "regime": current_regime,
        "compatible_engines": sorted(allowed),
    }]
    for item in native_trace:
        if item.get("engine") in allowed:
            trace.append({**item, "strategy_mode": "CROSS_ASSET", "target_asset": target, "source_asset": source})

    for item in candidates:
        engine = str(item.get("engine", "")).upper()
        if engine not in allowed:
            continue
        compatible, reason = cross_asset_compatible(target, source, engine, current_regime)
        if not compatible:
            trace.append({
                "status": "NOT_APPLICABLE",
                "engine": engine,
                "strategy": STRATEGY_NAMES.get(engine, engine),
                "reason": reason,
                "target_asset": target,
                "source_asset": source,
            })
            continue
        adapted = dict(item)
        adapted.update({
            "asset": target,
            "target_asset": target,
            "source_asset": source,
            "strategy_mode": "CROSS_ASSET",
            "strategy_origin": source,
            "compatibility_gate": "PASS",
            "compatibility_reason": reason,
            "source_min_rr": MIN_RR.get(engine),
            "effective_min_rr": MIN_RR.get(engine),
        })
        out.append(adapted)

    out.sort(key=lambda z: (-float((z.get("score_detail") or {}).get("score", 0)), z.get("engine", "")))
    return out, trace

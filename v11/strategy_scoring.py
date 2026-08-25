from __future__ import annotations

from copy import deepcopy


STRATEGY_PROFILES = {
    "G1": {
        "asset": "GOLD",
        "name": "TREND_PULLBACK",
        "min_score": 65,
        "core_gate": ["trend_direction", "pullback", "structure_intact", "entry_trigger"],
        "regimes": {"TREND"},
        "weights": {
            "trend_strength": 15,
            "ema_alignment": 15,
            "pullback_quality": 25,
            "structure_quality": 15,
            "momentum": 10,
            "location": 10,
            "rsi": 5,
            "atr": 5,
        },
    },
    "G2": {
        "asset": "GOLD",
        "name": "EMA_MOMENTUM_CONTINUATION",
        "min_score": 70,
        "core_gate": ["ema_direction", "momentum_candle", "confirmation_close"],
        "regimes": {"TREND", "EXPANSION"},
        "weights": {
            "momentum_strength": 25,
            "candle_body_quality": 20,
            "ema_alignment": 15,
            "price_location": 10,
            "atr_expansion": 10,
            "structure": 10,
            "rsi": 5,
            "volume_activity": 5,
        },
    },
    "G3": {
        "asset": "GOLD",
        "name": "STRUCTURE_BREAK_CONTINUATION",
        "min_score": 65,
        "core_gate": ["swing_structure", "bos", "pullback_after_bos", "structure_intact", "continuation_trigger"],
        "regimes": {"TREND", "BREAKOUT_RETEST", "EXPANSION"},
        "weights": {
            "bos_strength": 20,
            "structure_quality": 20,
            "pullback_quality": 20,
            "continuation_momentum": 15,
            "location": 10,
            "atr": 10,
            "ema_alignment": 5,
        },
    },
    "B1": {
        "asset": "BTC",
        "name": "VOLATILITY_EXPANSION_BREAKOUT",
        "min_score": 65,
        "core_gate": ["compression", "breakout", "breakout_close"],
        "regimes": {"EXPANSION"},
        "weights": {
            "breakout_strength": 20,
            "volatility_expansion": 20,
            "momentum": 15,
            "candle_quality": 10,
            "location": 10,
            "distance_from_breakout": 10,
            "trend_alignment": 10,
            "volume_activity": 5,
        },
    },
    "B2": {
        "asset": "BTC",
        "name": "BREAKOUT_RETEST",
        "min_score": 65,
        "core_gate": ["key_level", "breakout", "retest", "retest_holds", "confirmation_candle"],
        "regimes": {"BREAKOUT_RETEST", "EXPANSION"},
        "weights": {
            "retest_quality": 20,
            "momentum": 15,
            "structure": 15,
            "breakout_strength": 15,
            "location": 10,
            "atr": 10,
            "volume_activity": 10,
            "rsi": 5,
        },
    },
    "B3": {
        "asset": "BTC",
        "name": "LIQUIDITY_SWEEP_BREAKOUT",
        "min_score": 70,
        "core_gate": ["liquidity_level", "sweep", "reclaim", "confirmation"],
        "regimes": {"RANGE", "TRANSITION"},
        "weights": {
            "rejection_quality": 20,
            "displacement": 20,
            "structure_shift": 20,
            "sweep_depth": 15,
            "momentum": 10,
            "location": 10,
            "rsi": 5,
        },
    },
}


def _clamp(value, low, high):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    return max(low, min(high, value))


def score_setup(strategy: str, components: dict | None = None, core_gate: dict | None = None, filters: dict | None = None):
    profile = STRATEGY_PROFILES[strategy]
    components = components or {}
    core_gate = core_gate or {}
    filters = filters or components.get("filters") or {}

    failed_gate = [name for name in profile["core_gate"] if not bool(core_gate.get(name, False))]
    scored = {}
    total = 0.0
    for name, weight in profile["weights"].items():
        points = _clamp(components.get(name, 0.0), 0.0, float(weight))
        scored[name] = points
        total += points

    filter_rejections = []
    filter_aliases = {
        "spread_high": "SPREAD_HIGH",
        "atr_too_low": "ATR_TOO_LOW",
        "atr_too_high": "ATR_TOO_HIGH",
        "sl_too_tight": "SL_TOO_TIGHT",
        "sl_too_wide": "SL_TOO_WIDE",
        "invalid_rr": "RR_INVALID",
        "overextended": "OVEREXTENDED",
        "duplicate_signal": "DUPLICATE_SIGNAL",
        "conflict": "SIGNAL_CONFLICT",
        "market_closed": "MARKET_CLOSED",
    }
    for key, reason in filter_aliases.items():
        if bool(filters.get(key)):
            filter_rejections.append(reason)

    total = round(total, 2)
    qualified = not failed_gate and total >= profile["min_score"] and not filter_rejections
    return {
        "strategy": strategy,
        "asset": profile["asset"],
        "name": profile["name"],
        "score": total,
        "minimum_score": profile["min_score"],
        "qualified": qualified,
        "failed_gate": failed_gate,
        "filter_rejections": filter_rejections,
        "components": scored,
        "core_gate": deepcopy(core_gate),
        "filters": deepcopy(filters),
    }


def profile(strategy: str) -> dict:
    return deepcopy(STRATEGY_PROFILES[strategy])

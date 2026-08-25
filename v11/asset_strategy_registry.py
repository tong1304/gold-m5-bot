from __future__ import annotations

from .regime import ASSET_STRATEGY_REGIMES


def _normal_asset(asset: str) -> str:
    asset = str(asset or "").upper()
    if asset in ("XAU", "XAUUSD", "XAU/USD", "XAU/USDT"):
        return "GOLD"
    if asset in ("BTCUSD", "BTC/USD", "BTC/USDT"):
        return "BTC"
    return asset


def native_strategy_ids(asset: str, regime: str) -> list[str]:
    """Return only strategies belonging to the analyzed asset and regime."""
    target = _normal_asset(asset)
    current_regime = str(regime or "").upper()
    return [
        engine
        for engine, profile in ASSET_STRATEGY_REGIMES.items()
        if profile.get("asset") == target and current_regime in profile.get("regimes", set())
    ]

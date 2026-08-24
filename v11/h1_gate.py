from __future__ import annotations


def allows_trend_direction(h1_bias: str | None, direction: str | None) -> bool:
    """Hard H1 gate for Trend-family strategies.

    H1 BUY forbids Trend SELL, H1 SELL forbids Trend BUY.
    H1 NEUTRAL does not force a direction; M15/M5 may decide.
    """
    bias = str(h1_bias or "NEUTRAL").upper()
    side = str(direction or "").upper()
    if side not in ("BUY", "SELL"):
        return False
    return bias == "NEUTRAL" or bias == side


def gate_reason(h1_bias: str | None, direction: str | None) -> str:
    bias = str(h1_bias or "NEUTRAL").upper()
    side = str(direction or "").upper()
    if bias == "NEUTRAL":
        return "H1_NEUTRAL_M15_M5_DECIDE"
    if bias == side:
        return "H1_DIRECTION_ALIGNED"
    return f"H1_{bias}_BLOCKS_TREND_{side}"

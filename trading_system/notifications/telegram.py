from __future__ import annotations

from typing import Any


SYSTEM_NAME = "9-ENGINE-TRADING-DECISION-SYSTEM"


def render_decision(event: dict[str, Any]) -> str:
    """Presentation-only Telegram renderer for the 9-engine decision contract."""
    decision = str(event.get("decision", "NO_TRADE")).upper()
    symbol = str(event.get("symbol", "UNKNOWN")).upper()
    timeframe = event.get("timeframe", "M5")
    price = event.get("price")
    engine = event.get("engine", "E9")
    reason = event.get("reason") or event.get("signal_reason")

    direction_icon = "🟢" if decision == "BUY" else "🔴" if decision == "SELL" else "⚪"
    lines = [
        f"{direction_icon} <b>9-ENGINE DECISION</b>",
        "",
        f"📊 สินทรัพย์: <b>{symbol}</b>",
        f"⏱ Timeframe: <b>{timeframe}</b>",
        f"💵 ราคา: <b>{price}</b>" if price is not None else "",
        f"🧠 Decision Authority: <b>{engine}</b>",
        f"🎯 Decision: <b>{decision}</b>",
    ]
    if reason:
        lines.append(f"📝 Reason: <b>{reason}</b>")
    lines.extend([
        "",
        "🔗 Pipeline: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
    ])
    return "\n".join(line for line in lines if line != "")

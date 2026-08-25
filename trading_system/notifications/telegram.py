from __future__ import annotations

from typing import Any


def render_decision(event: dict[str, Any]) -> str:
    """Presentation only: renders an existing decision without changing it."""
    decision = event.get('decision', 'NO_TRADE')
    symbol = event.get('symbol', 'UNKNOWN')
    price = event.get('price')
    price_text = f'\n💵 Price: {price}' if price is not None else ''
    return f'🚨 Trading System v2.0\n\n📊 {symbol}{price_text}\n🧠 Decision: {decision}'

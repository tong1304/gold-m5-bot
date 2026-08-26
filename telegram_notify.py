"""Production-V2 Telegram notification boundary.

All Telegram sends are routed through the Production-V2 sender.
The legacy V11 Telegram sender is intentionally not imported or used.
"""

from production_v2_telegram import send_telegram
from trading_system.notifications.telegram import render_decision


def send_telegram_message(message):
    """Send an already-rendered message through the Production-V2 sender."""
    return send_telegram(message)


def send_decision_notification(event):
    """Render and send a 9-engine decision notification."""
    return send_telegram(render_decision(event))

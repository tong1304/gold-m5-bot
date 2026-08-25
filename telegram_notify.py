"""Compatibility wrapper for Telegram notifications.

All messages are routed through the 9-engine Telegram presentation boundary.
"""

from trading_system.notifications.telegram import render_decision
from v11.telegram import send_telegram


def send_telegram_message(message):
    """Send an already-rendered message through the 9-engine Telegram boundary."""
    return send_telegram(message)


def send_decision_notification(event):
    """Render and send a 9-engine decision notification."""
    return send_telegram(render_decision(event))

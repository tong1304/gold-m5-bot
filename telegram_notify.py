"""Compatibility wrapper for startup/scheduler Telegram notifications."""

import engine_v5 as engine


def send_telegram_message(message):
    return engine.send_telegram(message)

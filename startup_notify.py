import os
import threading

import requests

_LOCK = threading.Lock()
_SENT = False


def send_startup_notification(symbol="BTC/USDT", engine_version="5.0"):
    global _SENT
    with _LOCK:
        if _SENT:
            return False
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return False
        message = (
            "🚀 <b>BOT SYSTEM ONLINE</b>\n\n"
            f"<b>Exchange:</b> Binance\n"
            f"<b>Symbol:</b> {symbol}\n"
            "<b>Timeframe:</b> M5\n"
            f"<b>Engine:</b> v{engine_version}\n"
            "<b>Market Data:</b> Connected\n"
            "<b>Mode:</b> MANUAL ENTRY\n"
            "<b>Auto Order:</b> DISABLED\n\n"
            "System is ready to scan for signals."
        )
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            if response.ok:
                _SENT = True
                return True
        except requests.RequestException:
            pass
        return False

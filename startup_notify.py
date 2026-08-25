import os
import threading

import requests

_LOCK = threading.Lock()
_SENT = False

SYSTEM_NAME = "9-ENGINE-TRADING-DECISION-SYSTEM"
ARCHITECTURE = (
    "Market Data → E1 Market State → E2 Market Regime → E3 Market Structure "
    "→ E4 Liquidity → E5 Location/Value → E6 Trade Setup "
    "→ E7 Entry Confirmation → E8 Risk/Reward → E9 Master Decision/Execution"
)
SPEC_STATUS = "PHASE 4 SPECIFICATION v1.1 — LOCKED"
PRODUCTION_STATUS = "PHASE 5 IMPLEMENTATION — NOT ACTIVATED"


def send_startup_notification(symbol="BTC + GOLD / LSE", engine_version=None):
    global _SENT
    with _LOCK:
        if _SENT:
            return False
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return False

        asset = str(symbol or "BTC + GOLD / LSE").strip()
        if "/ LSE" in asset:
            asset = asset.replace(" / LSE", "").strip()
        if not asset:
            asset = "BTC + GOLD"

        message = (
            "🟢 <b>สถานะระบบ 9-ENGINE</b>\n\n"
            f"🕐 ระบบ: <b>{SYSTEM_NAME}</b>\n"
            f"📊 สินทรัพย์: <b>{asset}</b>\n"
            "⏱ Timeframe: <b>M5</b>\n\n"
            "🧠 <b>Architecture</b>\n"
            f"{ARCHITECTURE}\n\n"
            f"📐 <b>Specification:</b> {SPEC_STATUS}\n"
            f"⚙️ <b>Production:</b> {PRODUCTION_STATUS}\n"
            "📡 <b>Market Data:</b> ใช้ข้อมูลตาม Input Contract ของแต่ละ Engine\n"
            "🔐 <b>Decision Authority:</b> E9 เท่านั้น\n\n"
            "ℹ️ การแจ้งเตือนนี้เป็นสถานะระบบ ไม่ใช่สัญญาณ BUY/SELL\n"
            "⚠️ ระบบ 9 Engines จะไม่อ้างอิง H1/M15, B1-B3, G1-G3, Cross-Asset Fallback, "
            "หรือกลยุทธ์ V12 เดิมเป็นส่วนหนึ่งของ Decision Architecture"
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

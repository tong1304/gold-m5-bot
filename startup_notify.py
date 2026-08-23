import os
import threading

import requests

_LOCK = threading.Lock()
_SENT = False


def send_startup_notification(symbol="BTC + GOLD / LSE", engine_version="8"):
    global _SENT
    with _LOCK:
        if _SENT:
            return False
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return False

        # Keep the startup notification consistent with the actual LSE-native runtime.
        market = "LSE"
        asset = str(symbol or "BTC + GOLD / LSE").strip()
        if "/ LSE" in asset:
            asset = asset.replace(" / LSE", "").strip()
        if not asset:
            asset = "BTC + GOLD"

        message = (
            "🚀 <b>ระบบเทรดออนไลน์</b>\n\n"
            f"<b>ตลาด:</b> {market}\n"
            f"<b>สินทรัพย์:</b> {asset}\n"
            "<b>กรอบเวลา:</b> M5\n"
            f"<b>ระบบวิเคราะห์:</b> V{engine_version}\n\n"
            "📡 <b>ข้อมูลตลาด:</b> LSE Historical + LSE WebSocket เชื่อมต่อแล้ว\n"
            "📲 <b>Telegram:</b> เชื่อมต่อแล้ว\n\n"
            "<b>โหมด:</b> แจ้งสัญญาณเท่านั้น\n"
            "🖐️ <b>การเปิดออเดอร์:</b> คุณเป็นผู้กดเอง\n"
            "🤖 <b>เปิดออเดอร์อัตโนมัติ:</b> ปิด\n\n"
            "✅ ระบบพร้อมค้นหาจุดเข้าออเดอร์"
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

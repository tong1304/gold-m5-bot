from __future__ import annotations
import json, os
from urllib.request import Request, urlopen

def send_telegram(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if not token or not chat_id:
        return {"success": False, "error": "TELEGRAM_NOT_CONFIGURED"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    try:
        req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"success": bool(payload.get("ok")), "response": payload}
    except Exception as exc:
        return {"success": False, "error_type": type(exc).__name__, "error": str(exc)}

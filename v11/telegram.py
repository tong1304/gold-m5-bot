from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def send_telegram(text: str):
    """Send an HTML Telegram message without assuming response JSON is a dict.

    Telegram normally returns a JSON object, but proxies/errors/test endpoints can
    return a JSON scalar/string. Never let that turn into AttributeError('.get').
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if not token or not chat_id:
        return {"success": False, "error": "TELEGRAM_NOT_CONFIGURED"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({
        "chat_id": chat_id,
        "text": str(text),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    try:
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error_type": "TelegramResponseDecodeError",
                "error": "Telegram returned a non-JSON response",
                "response_text": raw[:500],
            }

        if not isinstance(payload, dict):
            return {
                "success": False,
                "error_type": "TelegramResponseTypeError",
                "error": f"Telegram response must be an object, got {type(payload).__name__}",
                "response": payload,
            }

        return {
            "success": bool(payload.get("ok", False)),
            "response": payload,
        }

    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        return {
            "success": False,
            "error_type": "HTTPError",
            "error": str(exc),
            "response_text": raw[:500],
        }
    except URLError as exc:
        return {
            "success": False,
            "error_type": "URLError",
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

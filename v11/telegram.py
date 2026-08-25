from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SYSTEM_NAME = "9-ENGINE-TRADING-DECISION-SYSTEM"
ARCHITECTURE = (
    "Market Data → E1 Market State → E2 Market Regime → E3 Market Structure "
    "→ E4 Liquidity → E5 Location/Value → E6 Trade Setup "
    "→ E7 Entry Confirmation → E8 Risk/Reward → E9 Master Decision/Execution"
)


def _normalize_message(text: str) -> str:
    """Prevent legacy V12/Cross-Asset labels from leaking into Telegram."""
    message = str(text)
    message = message.replace("12.11-CROSS-ASSET-FALLBACK", SYSTEM_NAME)
    message = message.replace("V12.11", SYSTEM_NAME)
    message = message.replace("V12", SYSTEM_NAME)
    message = message.replace(
        "H1 → M15 → M5 + REGIME + BTC B1-B3 + GOLD G1-G3 + RE-ENTRY + MULTI-TP",
        ARCHITECTURE,
    )
    message = message.replace("MTF:H1→M15→M5", "M5 / 9-ENGINE")
    message = message.replace("H1→M15→M5", "M5 / 9-ENGINE")
    message = message.replace("H1>M15>M5", "M5 / 9-ENGINE")
    message = message.replace("MODE=MTF", "MODE=9-ENGINE")
    message = message.replace("CROSS-ASSET-FALLBACK", "9-ENGINE")
    return message


def send_telegram(text: str):
    """Send an HTML Telegram message after legacy-label normalization."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if not token or not chat_id:
        return {"success": False, "error": "TELEGRAM_NOT_CONFIGURED"}

    normalized_text = _normalize_message(text)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({
        "chat_id": chat_id,
        "text": normalized_text,
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

        return {"success": bool(payload.get("ok", False)), "response": payload}

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
        return {"success": False, "error_type": "URLError", "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error_type": type(exc).__name__, "error": str(exc)}

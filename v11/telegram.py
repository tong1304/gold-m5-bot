from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SYSTEM_NAME = "9-ENGINE-TRADING-DECISION-SYSTEM"
ARCHITECTURE = (
    "Market Data → E1 Market State → E2 Market Regime → E3 Market Structure "
    "→ E4 Liquidity → E5 Location/Value → E6 Trade Setup "
    "→ E7 Entry Confirmation → E8 Risk/Reward → E9 Master Decision/Execution"
)

LEGACY_TOKENS = (
    "12.11-CROSS-ASSET-FALLBACK",
    "CROSS-ASSET-FALLBACK",
    "V12.11",
    "V12",
    "MTF:H1→M15→M5",
    "H1→M15→M5",
    "H1>M15>M5",
    "H1 → M15 → M5",
)


def _normalize_message(text: str) -> str:
    """Render every outgoing Telegram message in the locked 9-engine vocabulary.

    This is presentation-only. It must never change a trading decision.
    """
    message = str(text)

    # Legacy engine/version labels.
    message = message.replace("12.11-CROSS-ASSET-FALLBACK", SYSTEM_NAME)
    message = message.replace("CROSS-ASSET-FALLBACK", "9-ENGINE")
    message = message.replace("V12.11", SYSTEM_NAME)
    message = message.replace("V12", SYSTEM_NAME)

    # Legacy timeframe/strategy architecture labels.
    legacy_arch = (
        "H1 → M15 → M5 + REGIME + BTC B1-B3 + GOLD G1-G3 + RE-ENTRY + MULTI-TP"
    )
    message = message.replace(legacy_arch, ARCHITECTURE)
    message = message.replace("MTF:H1→M15→M5", "M5 / 9-ENGINE")
    message = message.replace("H1→M15→M5", "M5 / 9-ENGINE")
    message = message.replace("H1>M15>M5", "M5 / 9-ENGINE")
    message = message.replace("H1 → M15 → M5", "M5 / 9-ENGINE")
    message = message.replace("MODE=MTF", "MODE=9-ENGINE")

    # Do not expose the old asset-specific strategy catalog in notifications.
    for token in (
        "B1_RANGE_SWEEP_DISPLACEMENT",
        "B2_HTF_ZONE_M5_FVG_RETEST",
        "B3_VOLATILITY_EXPANSION_BREAKOUT_RETEST",
        "G1_LIQUIDITY_SWEEP_CHOCH",
        "G2_HTF_ZONE_M5_FVG_RETEST",
        "G3_VOLATILITY_EXPANSION_BREAKOUT_RETEST",
    ):
        message = message.replace(token, "SETUP_CANDIDATE")

    # Normalize old logging-style engine names if they reach Telegram.
    message = re.sub(r"(?i)(?:engine|ระบบวิเคราะห์)\s*[:=]\s*(?:12\.11[^\n]*)", "Engine: 9-ENGINE-TRADING-DECISION-SYSTEM", message)
    return message


def send_telegram(text: str):
    """Send an HTML Telegram message using the 9-engine presentation contract."""
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
            return {"success": False, "error_type": "TelegramResponseDecodeError", "error": "Telegram returned a non-JSON response", "response_text": raw[:500]}

        if not isinstance(payload, dict):
            return {"success": False, "error_type": "TelegramResponseTypeError", "error": f"Telegram response must be an object, got {type(payload).__name__}", "response": payload}

        return {"success": bool(payload.get("ok", False)), "response": payload}

    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        return {"success": False, "error_type": "HTTPError", "error": str(exc), "response_text": raw[:500]}
    except URLError as exc:
        return {"success": False, "error_type": "URLError", "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error_type": type(exc).__name__, "error": str(exc)}

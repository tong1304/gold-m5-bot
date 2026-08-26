from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BANGKOK = ZoneInfo("Asia/Bangkok")
_MONITOR_MARKER = "📊 <b>ราคาสินทรัพย์ปัจจุบัน</b>"
_MONITOR_NOTE = "ℹ️ แจ้งเตือนสถานะระบบ ไม่ใช่สัญญาณ BUY/SELL"


def _fmt_price(value):
    try:
        value = float(value)
        return f"{value:,.2f}" if value > 0 else "N/A"
    except (TypeError, ValueError):
        return "N/A"


def _current_m5_open(symbol: str):
    """Return the Open of the currently forming 5-minute candle.

    This is intentionally separate from the closed-candle scanner path. The
    status message reports the current M5 candle's fixed Open, while signal
    analysis continues to consume only closed M5 candles.
    """
    try:
        from lse import LSE

        market = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}.get(symbol)
        api_key = os.getenv("LSE_API_KEY", "").strip()
        if not market or not api_key:
            return None

        now = datetime.now(timezone.utc)
        slot = now.replace(second=0, microsecond=0, minute=(now.minute // 5) * 5)
        start = (slot - timedelta(minutes=5)).date().isoformat()
        end = (now + timedelta(days=1)).date().isoformat()
        client = LSE(api_key=api_key)
        try:
            rows = client.candles(
                market,
                "5m",
                start=start,
                end=end,
                limit=6,
                order="desc",
            )
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

        rows = rows.get("data") if isinstance(rows, dict) else rows
        if not isinstance(rows, (list, tuple)):
            return None

        candidates = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not all(key in row for key in ("datetime", "open")):
                continue
            try:
                ts = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts = ts.astimezone(timezone.utc).replace(second=0, microsecond=0)
                if ts == slot:
                    candidates.append(float(row["open"]))
            except (TypeError, ValueError):
                continue

        return candidates[0] if candidates else None
    except Exception:
        return None


def _format_system_monitor_message(now_bkk=None):
    now_bkk = now_bkk or datetime.now(timezone.utc).astimezone(BANGKOK)
    gold_open = _current_m5_open("GOLD")
    btc_open = _current_m5_open("BTC")
    return (
        "✅ <b>สถานะระบบ PRODUCTION-V2</b>\n\n"
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8\n"
        "⏱ Timeframe: M5\n\n"
        f"🚨เวลาแจ้งเตือน: {now_bkk.strftime('%d/%m/%Y %H:%M:%S')} (ประเทศไทย)\n\n"
        "📡 ราคาแท่งปัจจุบัน:\n"
        f"🌕 GOLD: {_fmt_price(gold_open)}\n"
        f"🪙 BTC: {_fmt_price(btc_open)}\n\n"
        "✅ ระบบทำงานปกติ"
    )


def _rewrite_system_monitor(text: str):
    text = str(text)
    if _MONITOR_MARKER not in text or _MONITOR_NOTE not in text:
        return text
    return _format_system_monitor_message()


def send_telegram(text: str):
    """Send an HTML Telegram message without assuming response JSON is a dict.

    The scheduled 15-minute system monitor is normalized here so every
    production status notification uses the approved PRODUCTION-V2 format.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if not token or not chat_id:
        return {"success": False, "error": "TELEGRAM_NOT_CONFIGURED"}

    text = _rewrite_system_monitor(text)
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

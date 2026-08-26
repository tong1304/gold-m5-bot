from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc


def _fmt_price(value):
    try:
        value = float(value)
        return f"{value:,.2f}" if value > 0 else "N/A"
    except (TypeError, ValueError):
        return "N/A"


def _current_m5_open(symbol: str, now_utc: datetime | None = None):
    """Return Open of the currently forming M5 candle, not the live tick."""
    try:
        from lse import LSE

        market = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}.get(symbol.upper())
        api_key = os.getenv("LSE_API_KEY", "").strip()
        if not market or not api_key:
            return None

        now_utc = now_utc or datetime.now(UTC)
        slot = now_utc.astimezone(UTC).replace(
            minute=(now_utc.minute // 5) * 5,
            second=0,
            microsecond=0,
        )
        start = (slot - timedelta(minutes=5)).date().isoformat()
        end = (slot + timedelta(minutes=5)).date().isoformat()

        client = LSE(api_key=api_key)
        try:
            rows = client.candles(
                market,
                "5m",
                start=start,
                end=end,
                limit=12,
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

        for row in rows:
            if not isinstance(row, dict) or "datetime" not in row or "open" not in row:
                continue
            try:
                ts = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                ts = ts.astimezone(UTC).replace(second=0, microsecond=0)
                if ts == slot:
                    return float(row["open"])
            except (TypeError, ValueError):
                continue
        return None
    except Exception:
        return None


def _format_production_v2_status(now_bkk: datetime | None = None):
    now_bkk = now_bkk or datetime.now(UTC).astimezone(BANGKOK)
    now_utc = now_bkk.astimezone(UTC)
    gold_open = _current_m5_open("GOLD", now_utc)
    btc_open = _current_m5_open("BTC", now_utc)
    return (
        "<b>✅ สถานะระบบ PRODUCTION-V2</b>\n\n"
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8\n"
        "⏱ Timeframe: M5\n\n"
        f"🚨เวลาแจ้งเตือน: {now_bkk.strftime('%d/%m/%Y %H:%M:%S')} (ประเทศไทย)\n\n"
        "📡 ราคาแท่งปัจจุบัน:\n"
        f"🌕 GOLD: {_fmt_price(gold_open)}\n"
        f"🪙 BTC: {_fmt_price(btc_open)}\n\n"
        "✅ ระบบทำงานปกติ"
    )


def _is_system_monitor(text: str) -> bool:
    markers = (
        "ราคาสินทรัพย์ปัจจุบัน",
        "แจ้งเตือนสถานะระบบ ไม่ใช่สัญญาณ BUY/SELL",
        "สถานะระบบ",
        "Architecture:",
    )
    return any(marker in str(text) for marker in markers)


def send_telegram(text: str):
    """Send Telegram using the Production-V2 status presentation contract."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if not token or not chat_id:
        return {"success": False, "error": "TELEGRAM_NOT_CONFIGURED"}

    if _is_system_monitor(text):
        normalized_text = _format_production_v2_status()
    else:
        normalized_text = str(text)

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
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return {"success": False, "error_type": "TelegramResponseTypeError", "response": payload}
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

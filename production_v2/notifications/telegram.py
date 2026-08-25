from __future__ import annotations

import os
from typing import Any

import requests

from ..contracts import DecisionResult


FORBIDDEN_LEGACY_TERMS = (
    "V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3",
)


TECHNICAL_TERMS = ("BUY", "SELL", "BTC", "GOLD", "M5", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "LSE", "API", "RSI", "ATR", "EMA", "VWAP", "RR", "Telegram")


def _validate(text: str) -> str:
    assert not any(term in text for term in FORBIDDEN_LEGACY_TERMS)
    return text


def format_decision(result: DecisionResult) -> str:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed:
        raise ValueError("Only actionable E9 BUY/SELL decisions can be notified")
    direction = "شراء" if result.decision == "BUY" else "ขาย"
    risk_gate = "ผ่าน" if result.risk.get("risk_gate") else "ไม่ผ่าน"
    text = (
        f"{'🟢 BUY' if result.decision == 'BUY' else '🔴 SELL'} — {direction}\n\n"
        f"📊 สินทรัพย์: {result.symbol}\n"
        f"⏱ Timeframe: {result.timeframe}\n"
        f"🎯 คำตัดสิน: {result.decision}\n"
        f"📈 คะแนน: {result.score:.1f}\n\n"
        "🧠 เส้นทางการตัดสินใจ\n"
        "E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9\n\n"
        "👑 ผู้ตัดสินใจ: E9\n"
        f"🛡️ Risk Gate: {risk_gate}\n"
        f"📌 เหตุผล: {', '.join(result.reason_codes) if result.reason_codes else 'ไม่มี'}"
    )
    return _validate(text)


def format_startup(symbols: list[str]) -> str:
    text = (
        "🟢 ระบบ 9-Engine เริ่มทำงาน\n\n"
        "⚙️ ระบบ: PRODUCTION-V2\n"
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9\n"
        "👑 ผู้ตัดสินใจ: E9\n"
        "🧩 ระบบเก่า: ปิดใช้งาน\n"
        f"📊 สินทรัพย์: {', '.join(symbols)}\n"
        "⏱ Timeframe: M5\n\n"
        "✅ ระบบพร้อมทำงาน"
    )
    return _validate(text)


def format_status(status: dict[str, Any]) -> str:
    symbols = status.get("symbols", {})
    lines = [
        "🟢 สถานะระบบ",
        "",
        "⚙️ ระบบ: PRODUCTION-V2",
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "👑 ผู้ตัดสินใจ: E9",
        f"⏱ Timeframe: {status.get('timeframe', 'M5')}",
        "",
        "📡 สถานะการเชื่อมต่อ:",
    ]
    for symbol, state in symbols.items():
        price = status.get("prices", {}).get(symbol)
        suffix = f" — ราคา {price}" if price is not None else ""
        lines.append(f"• {symbol}: {state}{suffix}")
    lines.extend(["", "✅ ระบบทำงานปกติ"])
    return _validate("\n".join(lines))


def format_critical(message: str, component: str) -> str:
    text = (
        "🔴 ระบบผิดปกติ\n\n"
        f"⚠️ ส่วนที่มีปัญหา: {component}\n"
        f"📌 รายละเอียด: {message}\n\n"
        "⛔ กรุณาตรวจสอบระบบ"
    )
    return _validate(text)


def send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    response.raise_for_status()
    return True


def send_decision(result: DecisionResult) -> bool:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed:
        return False
    return send(format_decision(result))

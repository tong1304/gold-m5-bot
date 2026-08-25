from __future__ import annotations

import os
from typing import Any

import requests

from ..contracts import DecisionResult


FORBIDDEN_LEGACY_TERMS = (
    "V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3",
)


def format_decision(result: DecisionResult) -> str:
    text = (
        "🧠 9-ENGINE TRADING SYSTEM\n\n"
        f"📊 สินทรัพย์: {result.symbol}\n"
        f"⏱ Timeframe: {result.timeframe}\n"
        f"🎯 Decision: {result.decision}\n"
        f"📈 Score: {result.score:.1f}\n\n"
        "🔗 Pipeline\n"
        "E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9\n\n"
        "👑 Decision Authority: E9\n"
        f"🛡 Risk Gate: {'PASS' if result.risk.get('risk_gate') else 'FAIL'}\n"
        f"ℹ️ Reason: {', '.join(result.reason_codes) if result.reason_codes else 'NONE'}"
    )
    assert not any(term in text for term in FORBIDDEN_LEGACY_TERMS)
    return text


def format_startup(symbols: list[str]) -> str:
    return (
        "🟢 9-ENGINE TRADING SYSTEM\n\n"
        "⚙️ Environment: PRODUCTION-V2\n"
        "🧠 Architecture: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9\n"
        "👑 Decision Authority: E9\n"
        "🧩 Legacy Runtime: DISABLED\n"
        f"📊 Assets: {', '.join(symbols)}\n\n"
        "ℹ️ แจ้งเตือนสถานะระบบ ไม่ใช่สัญญาณ BUY/SELL"
    )


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
    return send(format_decision(result))

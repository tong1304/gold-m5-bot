from __future__ import annotations

import os
from typing import Any

import requests

from ..contracts import DecisionResult

FORBIDDEN_LEGACY_TERMS = (
    "V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3",
)
TELEGRAM_MAX_TEXT = 4096


def _validate(text: str) -> str:
    assert not any(term in text for term in FORBIDDEN_LEGACY_TERMS)
    return text


def _fmt_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}".rstrip('0').rstrip('.')
    if isinstance(value, dict):
        return ", ".join(f"{k}={_fmt_value(v)}" for k, v in value.items())
    if isinstance(value, bool):
        return "ใช่" if value else "ไม่"
    return str(value)


def _flatten_evidence(prefix: str, value: Any, lines: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            label = key.replace('_', ' ')
            if isinstance(item, dict):
                lines.append(f"• {prefix}{label}:")
                _flatten_evidence(prefix + "  ", item, lines)
            else:
                lines.append(f"• {prefix}{label}: {_fmt_value(item)}")
    elif value is not None:
        lines.append(f"• {prefix}{_fmt_value(value)}")


def _engine_detail(engine: Any) -> list[str]:
    output = getattr(engine, "output", None) or {}
    reason_codes = list(getattr(engine, "reason_codes", None) or [])
    lines: list[str] = []
    sub_items = [(k, v) for k, v in output.items() if len(str(k)) == 2 and str(k)[0].isdigit()]
    for sub_id, sub_output in sub_items:
        lines.append(f"  ▸ {sub_id}")
        _flatten_evidence("    ", sub_output, lines)
    if "trade_plan" in output:
        lines.append("  ▸ แผน Risk")
        _flatten_evidence("    ", output["trade_plan"], lines)
    if reason_codes:
        lines.append("  ▸ Reason Code")
        lines.extend(f"    • {code}" for code in reason_codes)
    return lines or ["  • ไม่มี Evidence ที่ส่งออกจาก Engine"]


def format_decision(result: DecisionResult) -> str:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed:
        raise ValueError("Only actionable E9 BUY/SELL decisions can be notified")
    plan = result.trade_plan
    required = ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2")
    if not plan.get("valid") or any(k not in plan for k in required):
        raise ValueError("Actionable E9 decision requires a complete E8 trade plan")
    direction = "ซื้อ" if result.decision == "BUY" else "ขาย"
    lines = [
        f"{'🟢 BUY' if result.decision == 'BUY' else '🔴 SELL'} — {direction}", "",
        f"📊 สินทรัพย์: {result.symbol}", f"⏱ Timeframe: {result.timeframe}", "",
        "━━━━━━━━━━━━━━━━━━", "🧠 เหตุผลจริงจาก 9 Engines / Sub-Engines", "━━━━━━━━━━━━━━━━━━",
    ]
    for engine in result.engines:
        lines.extend(["", f"{engine.engine_id} — {engine.name}", f"{'✅' if engine.gate_passed else '❌'} {'ผ่าน' if engine.gate_passed else 'ไม่ผ่าน'}"])
        lines.extend(_engine_detail(engine))
    lines.extend([
        "", "━━━━━━━━━━━━━━━━━━", "👑 E9 — Execution Decision", "🟢 อนุมัติคำสั่ง",
        "", "━━━━━━━━━━━━━━━━━━", "🎯 แผนการเทรด", "━━━━━━━━━━━━━━━━━━",
        f"📍 จุดเข้า: {plan['entry']}", f"🛑 Stop Loss: {plan['stop_loss']}",
        f"🎯 Take Profit 1: {plan['take_profit_1']}", f"🎯 Take Profit 2: {plan['take_profit_2']}",
        f"📐 RR: 1:{plan['rr_tp2']:.1f}", f"📈 Decision Score: {result.score:.1f}",
    ])
    if result.reason_codes:
        lines.extend(["", "📌 เหตุผลเพิ่มเติม:", *[f"• {code}" for code in result.reason_codes]])
    return _validate("\n".join(lines))


def format_startup(symbols: list[str]) -> str:
    return _validate("\n".join([
        "🟢 ระบบ 9-Engine เริ่มทำงาน", "", "⚙️ ระบบ: PRODUCTION-V2",
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "👑 ผู้ตัดสินใจ: E9", "🧩 ระบบเก่า: ปิดใช้งาน", f"📊 สินทรัพย์: {', '.join(symbols)}",
        "⏱ Timeframe: M5", "", "✅ ระบบพร้อมทำงาน",
    ]))


def format_status(status: dict[str, Any]) -> str:
    symbols = status.get("symbols", {})
    lines = ["🟢 สถานะระบบ", "", "⚙️ ระบบ: PRODUCTION-V2",
             "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
             "👑 ผู้ตัดสินใจ: E9", f"⏱ Timeframe: {status.get('timeframe', 'M5')}", "", "📡 สถานะการเชื่อมต่อ:"]
    for symbol, state in symbols.items():
        price = status.get("prices", {}).get(symbol)
        suffix = f" — ราคา {price}" if price is not None else ""
        lines.append(f"• {symbol}: {state}{suffix}")
    return _validate("\n".join(lines + ["", "✅ ระบบทำงานปกติ"]))


def format_critical(message: str, component: str) -> str:
    return _validate(f"🔴 ระบบผิดปกติ\n\n⚠️ ส่วนที่มีปัญหา: {component}\n📌 รายละเอียด: {message}\n\n⛔ กรุณาตรวจสอบระบบ")


def _chunk_text(text: str, limit: int = TELEGRAM_MAX_TEXT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(''.join(current).rstrip())
                current, size = [], 0
            for i in range(0, len(line), limit):
                chunks.append(line[i:i + limit].rstrip())
            continue
        if current and size + len(line) > limit:
            chunks.append(''.join(current).rstrip())
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append(''.join(current).rstrip())
    return chunks


def send(text: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    for chunk in _chunk_text(text):
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk},
            timeout=15,
        )
        if not response.ok:
            try:
                detail = response.json().get("description", response.text)
            except ValueError:
                detail = response.text
            raise RuntimeError(f"Telegram sendMessage failed ({response.status_code}): {detail}")
    return True


def send_decision(result: DecisionResult) -> bool:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed:
        return False
    return send(format_decision(result))

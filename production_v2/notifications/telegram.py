from __future__ import annotations

import os
from typing import Any

import requests

from ..contracts import DecisionResult

FORBIDDEN_LEGACY_TERMS = (
    "V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3",
)
TELEGRAM_MAX_TEXT = 4096

ENGINE_THAI_NAMES = {
    "E1": "สภาวะตลาด",
    "E2": "ระบอบตลาด",
    "E3": "โครงสร้างตลาด",
    "E4": "สภาพคล่อง",
    "E5": "ตำแหน่งราคา",
    "E6": "รูปแบบการเข้าเทรด",
    "E7": "การยืนยัน",
    "E8": "ความเสี่ยง",
    "E9": "การตัดสินใจส่งคำสั่ง",
}

TECH_LABELS = {
    "state": "สถานะ",
    "direction": "ทิศทาง",
    "trend_change": "การเปลี่ยนแปลงของ Trend",
    "volatility": "Volatility",
    "regime": "Regime",
    "higher_high": "Higher High",
    "lower_low": "Lower Low",
    "position_in_range": "ตำแหน่งในกรอบ",
    "body_ratio": "สัดส่วนแท่งเทียน",
    "rr": "RR",
    "risk_distance": "ระยะความเสี่ยง",
    "authority": "ผู้ตัดสินใจ",
}

STATE_TH = {
    "VALID": "ถูกต้อง",
    "UP": "ขาขึ้น",
    "DOWN": "ขาลง",
    "NEUTRAL": "เป็นกลาง",
    "BULLISH": "ขาขึ้น",
    "BEARISH": "ขาลง",
    "TREND_UP": "แนวโน้มขาขึ้น",
    "TREND_DOWN": "แนวโน้มขาลง",
    "TREND": "แนวโน้ม",
    "RANGE": "กรอบราคา",
    "COMPRESSION": "การบีบตัว",
    "EXPANSION": "การขยายตัว",
    "TRANSITION": "ช่วงเปลี่ยนผ่าน",
    "BOS_CONFIRMED": "BOS ยืนยัน",
    "NO_BOS": "ยังไม่พบ BOS",
    "REJECTION": "เกิดการปฏิเสธราคา",
    "NO_REJECTION": "ไม่พบการปฏิเสธราคา",
    "ACCEPTANCE": "ยอมรับราคา",
    "SPACE_AVAILABLE": "มีพื้นที่ราคา",
    "LIMITED_SPACE": "พื้นที่ราคาจำกัด",
    "EXTENDED": "ราคาอยู่ในภาวะยืดตัว",
    "NOT_EXTENDED": "ราคาไม่ยืดตัวเกินไป",
    "CONFIRMATION_PASS": "การยืนยันผ่าน",
    "CONFIRMATION_WEAK": "การยืนยันยังอ่อน",
    "TRIGGER_OBSERVED": "พบ Trigger",
    "NO_STRONG_TRIGGER": "ยังไม่พบ Trigger ที่แข็งแรง",
    "FOLLOW_THROUGH_OBSERVED": "มี Follow-through",
    "NO_FOLLOW_THROUGH": "ยังไม่มี Follow-through",
}


def _validate(text: str) -> str:
    assert not any(term in text for term in FORBIDDEN_LEGACY_TERMS)
    return text


def _fmt_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, bool):
        return "ใช่" if value else "ไม่"
    if isinstance(value, dict):
        return ", ".join(f"{k}={_fmt_value(v)}" for k, v in value.items())
    if isinstance(value, str):
        return STATE_TH.get(value, value)
    return str(value)


def _label(key: str) -> str:
    return TECH_LABELS.get(key, key.replace("_", " "))


def _collect_values(value: Any, result: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key in {"trade_plan", "reason_codes", "trace", "output"}:
            continue
        if isinstance(item, dict):
            _collect_values(item, result)
        elif key in {"state", "direction", "regime", "volatility", "trend_change", "higher_high", "lower_low", "position_in_range", "body_ratio", "rr", "risk_distance", "authority"}:
            result[key] = item


def _engine_summary(engine: Any) -> list[str]:
    engine_id = str(getattr(engine, "engine_id", ""))
    output = getattr(engine, "output", None) or {}
    summary: dict[str, Any] = {}
    _collect_values(output, summary)

    lines: list[str] = []
    # Keep only the most useful evidence at Engine level; Sub-Engine IDs are intentionally hidden.
    preferred = {
        "E1": ["state", "direction", "volatility"],
        "E2": ["regime", "direction", "state"],
        "E3": ["state", "direction", "higher_high", "lower_low"],
        "E4": ["state"],
        "E5": ["state", "position_in_range"],
        "E6": ["state", "direction", "body_ratio"],
        "E7": ["state", "direction", "body_ratio"],
        "E8": ["state", "rr", "risk_distance"],
        "E9": ["state", "direction", "authority"],
    }.get(engine_id, ["state", "direction"])

    used = set()
    for key in preferred:
        if key in summary and key not in used:
            lines.append(f"• {_label(key)}: {_fmt_value(summary[key])}")
            used.add(key)

    if engine_id == "E8":
        plan = output.get("trade_plan") or {}
        if plan.get("valid"):
            lines.append("• Risk Plan: ผ่าน")
            lines.append(f"• RR: 1:{float(plan.get('rr_tp2', 0)):.1f}")
            lines.append(f"• Stop Loss Distance: {_fmt_value(plan.get('risk_distance'))}")
    if engine_id == "E9":
        decision = output.get("decision")
        if decision:
            lines.append(f"• Execution Decision: {'อนุมัติ' if decision in {'BUY', 'SELL'} else 'ไม่อนุมัติ'}")

    return lines or ["• ผลประเมิน: ผ่าน"]


def format_decision(result: DecisionResult) -> str:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed:
        raise ValueError("Only actionable E9 BUY/SELL decisions can be notified")
    plan = result.trade_plan
    required = ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2")
    if not plan.get("valid") or any(k not in plan for k in required):
        raise ValueError("Actionable E9 decision requires a complete E8 trade plan")

    direction = "ซื้อ" if result.decision == "BUY" else "ขาย"
    lines = [
        f"{'🟢 BUY' if result.decision == 'BUY' else '🔴 SELL'} — {direction}",
        "",
        f"📊 สินทรัพย์: {result.symbol}",
        f"⏱ Timeframe: {result.timeframe}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🧠 เหตุผลจาก 9 Engines",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for engine in result.engines:
        engine_id = getattr(engine, "engine_id", "")
        name = ENGINE_THAI_NAMES.get(engine_id, getattr(engine, "name", engine_id))
        passed = bool(getattr(engine, "gate_passed", False))
        lines.extend(["", f"{engine_id} — {name}", f"{'✅' if passed else '❌'} {'ผ่าน' if passed else 'ไม่ผ่าน'}"])
        lines.extend(_engine_summary(engine))

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "👑 E9 — การตัดสินใจส่งคำสั่ง",
        "🟢 อนุมัติคำสั่ง",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🎯 แผนการเทรด",
        "━━━━━━━━━━━━━━━━━━",
        f"📍 จุดเข้า: {plan['entry']}",
        f"🛑 Stop Loss: {plan['stop_loss']}",
        f"🎯 Take Profit 1: {plan['take_profit_1']}",
        f"🎯 Take Profit 2: {plan['take_profit_2']}",
        f"📐 RR: 1:{plan['rr_tp2']:.1f}",
        f"📈 Decision Score: {result.score:.1f}",
    ])
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
                chunks.append("".join(current).rstrip())
                current, size = [], 0
            for i in range(0, len(line), limit):
                chunks.append(line[i:i + limit].rstrip())
            continue
        if current and size + len(line) > limit:
            chunks.append("".join(current).rstrip())
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current).rstrip())
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

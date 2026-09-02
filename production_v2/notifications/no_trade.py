from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import _engine_finding, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
REASON_TH = {
    "E1_DATA_INVALID": "ข้อมูลตลาดไม่สมบูรณ์",
    "E3_STRUCTURE_INVALIDATED": "โครงสร้างราคาถูกทำลาย",
    "E5_LOCATION_DISADVANTAGED": "Location ไม่ได้เปรียบ",
    "E5_SPACE_INSUFFICIENT": "พื้นที่เป้าหมายไม่เพียงพอ",
    "E6_SETUP_INVALIDATED": "Trade Setup ถูกทำลาย",
    "E6_NO_VALID_SETUP": "ยังไม่พบ Trade Setup ที่ชัดเจน",
    "E7_CONFIRMATION_INVALIDATED": "Confirmation ไม่ผ่าน",
    "ENTRY_CONFIRMATION_NOT_PROVEN": "Trigger/Follow-through ยังไม่ยืนยัน Entry",
    "TRADE_ECONOMICS_NOT_READY": "Trade Economics ยังไม่พร้อม",
    "E8_RR_BELOW_MINIMUM": "RR ไม่คุ้มความเสี่ยง",
    "E8_STOP_TOO_WIDE": "Stop Loss กว้างเกินไป",
    "STOP_TOO_WIDE_FOR_SHORT_TERM": "Stop Loss กว้างเกินไปสำหรับ M5",
    "INSUFFICIENT_RISK_DATA": "ข้อมูล Risk ยังไม่เพียงพอ",
}


def _main_reason(result: Any) -> str:
    reasons = list(getattr(result, "risk", {}).get("decision_reasons") or getattr(result, "reason_codes", ()) or ())
    e9 = next((e for e in _engines(result) if getattr(e, "engine_id", None) == "E9"), None)
    if e9 is not None:
        output = _output(e9)
        reasons.extend(output.get("decision_reasons") or getattr(e9, "reason_codes", ()) or ())
    for code in dict.fromkeys(str(x) for x in reasons if x):
        if code in REASON_TH:
            return REASON_TH[code]
    return "หลักฐานยังไม่เพียงพอสำหรับเปิด Position"


def _engines(result: Any) -> list[Any]:
    engines = getattr(result, "engines", None)
    if engines:
        return list(engines)
    if isinstance(result, dict):
        raw = result.get("engines") or result.get("engine_results") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []
    try:
        raw = result.as_dict().get("engines") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []
    except Exception:
        return []


def _output(engine: Any) -> dict[str, Any]:
    if hasattr(engine, "output"):
        value = getattr(engine, "output", {})
        return value if isinstance(value, dict) else {}
    if isinstance(engine, dict):
        value = engine.get("output")
        return value if isinstance(value, dict) else engine
    return {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _engine_compact(engine: Any, expected_id: str) -> str:
    """Report the engine's semantic conclusion without manufacturing meaning."""
    if hasattr(engine, "engine_id"):
        engine_id = str(engine.engine_id)
        finding = _engine_finding(engine)
    elif isinstance(engine, dict):
        engine_id = str(engine.get("engine_id") or engine.get("id") or expected_id)
        class _EngineView:
            pass
        view = _EngineView()
        view.engine_id = engine_id
        view.output = _output(engine)
        view.reason_codes = tuple(engine.get("reason_codes") or engine.get("reasons") or ())
        view.gate_passed = engine.get("gate_passed")
        finding = _engine_finding(view)
    else:
        engine_id = expected_id
        finding = "ANALYSIS_DATA_MISSING"

    output = _output(engine)
    finding = _text(finding)

    if engine_id == "E9":
        finding = _text(output.get("decision") or finding or "NO_TRADE")
    elif engine_id == "E1":
        reasoning = output.get("professional_reasoning")
        reasoning = reasoning if isinstance(reasoning, dict) else {}
        market_state = _text(output.get("market_state") or reasoning.get("market_state"))
        volatility = _text(output.get("volatility_state") or reasoning.get("volatility_state"))
        structure = _text(output.get("structure_state") or reasoning.get("structure_state"))
        pressure = _text(output.get("directional_pressure") or reasoning.get("directional_pressure"))
        trend = _text(output.get("trend_state") or reasoning.get("trend_state"))
        transition = _text(output.get("transition") or reasoning.get("transition"))
        parts = []
        if market_state: parts.append(f"MARKET_STATE={market_state}")
        if volatility: parts.append(f"VOLATILITY={volatility}")
        if structure: parts.append(f"STRUCTURE={structure}")
        if pressure: parts.append(f"PRESSURE={pressure}")
        if trend: parts.append(f"TREND_STATE={trend}")
        if transition: parts.append(f"TRANSITION={transition}")
        if parts: finding = "; ".join(parts)
    elif engine_id == "E2":
        decision = _text(output.get("opportunity_decision") or output.get("opportunity_state") or output.get("opportunity_stage"))
        direction = _text(output.get("opportunity_direction") or output.get("direction"))
        if decision and direction and any(token in decision for token in ("DEVELOP", "FORM", "PENDING", "WATCH")):
            finding = f"{direction} opportunity is developing based on closed-candle evidence"
        elif decision:
            finding = f"{direction + ' ' if direction else ''}{decision}"
        # WAIT is a valid E2 conclusion. Do not turn it into an executable setup.
        if decision == "WAIT":
            finding = _text(output.get("finding") or finding or "WAIT")
    elif engine_id == "E4":
        finding = _text(output.get("finding") or output.get("analyst_conclusion") or finding)
    elif engine_id == "E5":
        value = _text(output.get("value") or output.get("value_position") or output.get("value_state"))
        response = _text(output.get("value_response"))
        repricing = _text(output.get("repricing_state"))
        if value or response or repricing:
            finding = "FAVORABLE_LOCATION: " + ", ".join(x for x in (
                f"value={value}" if value else "",
                f"response={response}" if response else "",
                f"repricing={repricing}" if repricing else "",
            ) if x)
    elif engine_id == "E6":
        # A NONE/NO_SETUP field is not a semantic finding. Prefer E6's actual
        # conclusion so Telegram never emits phrases such as "BUY NONE is absent".
        explicit_finding = _text(output.get("finding") or output.get("analyst_conclusion") or output.get("conclusion"))
        setup = _text(output.get("setup") or output.get("setup_family") or output.get("setup_type"))
        state = _text(output.get("setup_state") or output.get("opportunity_state") or output.get("opportunity_stage"))
        if explicit_finding and (setup in {"", "UNKNOWN", "NONE", "NO_SETUP"} or state in {"", "UNKNOWN", "NONE", "NO_SETUP"}):
            finding = explicit_finding
        else:
            direction = _text(output.get("direction") or output.get("opportunity_direction"))
            if direction and setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
                finding = f"{direction} {setup}" + (f" is {state.lower()}" if state else "")
            elif setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
                finding = setup + (f" is {state.lower()}" if state else "")
            elif explicit_finding:
                finding = explicit_finding
    elif engine_id == "E7":
        confirmation = _text(output.get("confirmation_state") or output.get("confirmation") or output.get("finding") or finding)
        if confirmation: finding = confirmation
    elif engine_id == "E8":
        finding = _text(output.get("analyst_conclusion") or output.get("finding") or output.get("trade_economics_state") or finding)

    finding = finding or "ANALYSIS_DATA_MISSING"
    if len(finding) > 180:
        finding = finding[:177].rstrip() + "..."
    return f"{engine_id}: {finding}"


def _lifecycle_lines(result: Any) -> list[str]:
    risk = getattr(result, "risk", {}) or {}
    lifecycle = risk.get("opportunity_lifecycle") or {}
    if not isinstance(lifecycle, dict) or not lifecycle.get("state"):
        return []
    state = _text(lifecycle.get("state"))
    continuity = _text(lifecycle.get("continuity"))
    bars_waited = int(lifecycle.get("bars_waited", 0) or 0)
    opportunity_id = _text(lifecycle.get("opportunity_id"))
    next_event = _text(risk.get("next_required_event") or lifecycle.get("next_required_event"))
    lines = ["🔄 OPPORTUNITY LIFECYCLE", f"สถานะ: {state}"]
    if continuity: lines.append(f"continuity={continuity}")
    if opportunity_id: lines.append(f"opportunity_id={opportunity_id}")
    lines.append(f"bars_waited={bars_waited}")
    if next_event: lines.append(f"next={next_event}")
    if state == "WAITING":
        lines.append("ความหมาย: เฝ้ารอหลักฐานยืนยัน ไม่ใช่คำสั่งเปิด Position")
    return lines


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    """Build one NO_TRADE alert from actual E1-E9 outputs plus lifecycle state."""
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = [
        "🚫 NO_TRADE — ยังไม่มีการออกออเดอร์",
        "",
        "⚙️ PRODUCTION-V2 | E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "⏱ M5",
        f"🚨 {now:%d/%m/%Y %H:%M} (ประเทศไทย)",
    ]
    for symbol, result in results.items():
        lines += ["", "━━━━━━━━━━━━━━━━━━", f"📊 {symbol}", "━━━━━━━━━━━━━━━━━━"]
        engines_by_id = {getattr(e, "engine_id", None): e for e in _engines(result)}
        for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
            engine = engines_by_id.get(engine_id)
            lines.append(_engine_compact(engine, engine_id) if engine is not None else f"{engine_id}: ANALYSIS_DATA_MISSING")
        lines += _lifecycle_lines(result)
        lines += ["🎯 FINAL: NO_TRADE", f"เหตุผลหลัก: {_main_reason(result)}"]
    lines += [
        "",
        "🔄 รอหลักฐานเพิ่มเติมเมื่อแท่ง M5 ปิดถัดไป",
        "📌 Opportunity Lifecycle จะถูกเก็บต่อข้ามแท่งเมื่อยังไม่ถูก Invalidate",
        "📌 E9 เท่านั้นเป็น Final Decision Authority",
    ]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))

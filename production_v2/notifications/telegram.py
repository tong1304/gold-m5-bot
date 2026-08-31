from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests

from ..contracts import DecisionResult

FORBIDDEN_LEGACY_TERMS = ("V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3")
TELEGRAM_MAX_TEXT = 4096
ENGINE_THAI_NAMES = {"E1":"สภาวะตลาด","E2":"Regime / Playbook","E3":"โครงสร้างตลาด","E4":"สภาพคล่อง","E5":"ตำแหน่งราคา","E6":"Trade Setup","E7":"Confirmation","E8":"Risk / Trade Economics","E9":"การตัดสินใจ"}
STATE_TH = {"UP":"ขาขึ้น","DOWN":"ขาลง","BULLISH":"ขาขึ้น","BEARISH":"ขาลง","NEUTRAL":"เป็นกลาง","TREND":"Trend","RANGE":"Range","TRANSITION":"Transition","EXPANSION":"Expansion","COMPRESSION":"Compression","VALID":"ข้อมูลใช้ได้","MATURE":"สมบูรณ์","INVALIDATED":"ถูกยกเลิก","TRIGGER_OBSERVED":"พบ Trigger","QUALITY_PASS":"คุณภาพผ่าน","FOLLOW_THROUGH_OBSERVED":"มี Follow-through","CONFIRMATION_PASS":"ยืนยันผ่าน","FAILURE":"Failure","UNKNOWN":"ยังไม่ชัดเจน","NO_SWEEP":"ไม่มี Sweep","NO_RECLAIM":"ไม่มี Reclaim","CONFIRMATION_WAIT":"ยังไม่ยืนยัน"}


def _validate(text: str) -> str:
    assert not any(term in text for term in FORBIDDEN_LEGACY_TERMS)
    return text


def _fmt(value: Any) -> str:
    if value is None or value == "": return "ไม่พบข้อมูล"
    if isinstance(value, bool): return "ใช่" if value else "ไม่"
    if isinstance(value, float): return f"{value:.4f}".rstrip("0").rstrip(".")
    return STATE_TH.get(str(value), str(value))


def _professional(engine: Any) -> dict[str, Any]:
    value = (getattr(engine, "output", {}) or {}).get("professional_reasoning") or {}
    return value if isinstance(value, dict) else {}


def _list_values(value: Any) -> list[str]:
    if value is None: return []
    if isinstance(value, dict): return [f"{k}={v}" for k, v in value.items()]
    if isinstance(value, (list, tuple, set)): return [str(x) for x in value if x is not None and str(x)]
    return [str(value)]


def _first(engine: Any, *keys: str, default: Any = None) -> Any:
    output = getattr(engine, "output", {}) or {}; reasoning = _professional(engine)
    for key in keys:
        for source in (output, reasoning):
            if isinstance(source, dict) and source.get(key) not in (None, ""): return source[key]
    return default


def _evidence(engine: Any) -> list[str]:
    output = getattr(engine, "output", {}) or {}; reasoning = _professional(engine); values: list[str] = []
    for source in (output, reasoning):
        if not isinstance(source, dict): continue
        for key in ("observations", "evidence", "reasoning_trace", "missing_evidence", "counter_evidence"):
            values.extend(_list_values(source.get(key)))
    return list(dict.fromkeys(values))[:24]


def _reasons(engine: Any) -> list[str]:
    output = getattr(engine, "output", {}) or {}; values: list[str] = []
    for key in ("reason_codes", "analysis_reason_codes", "reasons", "decision_reasons", "conflicts"):
        values.extend(_list_values(output.get(key)))
    values.extend(_list_values(getattr(engine, "reason_codes", ())))
    return list(dict.fromkeys(x for x in values if x))[:24]


def _analysis_status(engine: Any) -> str:
    eid = engine.engine_id; output = getattr(engine, "output", {}) or {}
    finding = str(_first(engine, "finding", "conclusion", "analyst_conclusion", default="")).upper(); reasons = set(_reasons(engine))
    if eid == "E9": return "🟢" if output.get("decision") in {"BUY", "SELL"} else "🔴"
    if any(x in finding for x in ("INVALID", "FAILED", "CONFLICT")): return "🔴"
    if eid == "E7" and "CONFIRM" not in finding: return "🔴" if {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING"} & reasons else "🟡"
    if eid == "E8" and not bool((_first(engine, "trade_plan", default={}) or {}).get("valid")): return "🔴"
    return "🟡"


def _engine_finding(engine: Any) -> str:
    value = _first(engine, "finding", "conclusion", "analyst_conclusion", "thesis", "state")
    return str(value) if value not in (None, "") else "UNRESOLVED"


def _selected_details(engine: Any) -> list[str]:
    e = engine.engine_id; output = getattr(engine, "output", {}) or {}; reasoning = _professional(engine); details: list[str] = []
    keys = {
        "E1": ("market_state","volatility_state","structure_state","directional_pressure","trend_state","transition","ema20_vs_ema50","ema_gap_atr","directional_consensus","long_horizon_direction","persistence"),
        "E2": ("opportunity_decision","opportunity_direction","opportunity_state","opportunity_stage","opportunity_score","playbook","auction_state"),
        "E3": ("external_state","internal_state","bos","choch","failed_break","protected_high","protected_low","lifecycle","invalidation"),
        "E4": ("event","event_level","event_age_bars","liquidity_taker","response_actor","liquidity_type","liquidity_quality","auction_quality","auction_state","liquidity_externality","liquidity_proximity"),
        "E5": ("price","value","value_position","value_distance_atr","value_state","value_response","repricing_state","structural_location","next_resistance","next_support","available_space_atr_long","available_space_atr_short","extension_atr"),
        "E6": ("direction","setup","setup_state","opportunity_direction","opportunity_state","opportunity_stage"),
        "E7": ("observed","direction","closed_candle","is_confirmation","confirmation_state","follow_through","invalidation","next_required_event"),
        "E8": ("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2","real_rr","probability_edge","stop_quality","target_realism","effective_space","trade_plan"),
        "E9": ("decision","execution","setup","direction","trade_plan","governance_blockers","active_invalidations"),
    }.get(e, ())
    for key in keys:
        value = output.get(key) if output.get(key) not in (None, "") else reasoning.get(key)
        if value in (None, ""): continue
        if key == "trade_plan" and isinstance(value, dict):
            for plan_key in ("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2","valid"):
                if value.get(plan_key) is not None: details.append(f"{plan_key}={value[plan_key]}")
        elif isinstance(value, (dict,list,tuple,set)): details.append(f"{key}={_list_values(value)}")
        else: details.append(f"{key}={_fmt(value)}")
    return details


def _engine_answer(engine: Any) -> str:
    e = engine.engine_id
    # Report from the actual engine output/professional reasoning, not only `finding`.
    # Some brains intentionally store their conclusion in professional_reasoning or specialists.
    answer = _engine_finding(engine); details = _selected_details(engine); evidence = _evidence(engine); reasons = _reasons(engine)
    lines = [f"{_analysis_status(engine)} {e} — {ENGINE_THAI_NAMES.get(e, e)}", f"คำตอบ: {answer}"]
    if details: lines.append("ข้อมูลวิเคราะห์: " + " | ".join(details))
    lines.append("เหตุผล: " + (", ".join(reasons) if reasons else "ไม่มีเหตุผลเพิ่มเติม"))
    if evidence: lines.append("หลักฐาน: " + " | ".join(evidence))
    return "\n".join(lines)


def _e9_control_lines(result: DecisionResult) -> list[str]:
    e9 = next((e for e in result.engines if e.engine_id == "E9"), None)
    if e9 is None: return []
    output = e9.output or {}; reasoning = _professional(e9)
    control = reasoning.get("market_control") or reasoning.get("market_control_thesis") or output.get("market_control") or output.get("market_control_thesis") or {}
    if not isinstance(control, dict): control = {}
    def pick(*keys: str) -> Any:
        for key in keys:
            for source in (control, reasoning, output):
                if isinstance(source, dict) and source.get(key) not in (None, ""): return source[key]
        return None
    return ["", "━━━━━━━━━━━━━━━━━━", "🧠 มุมมอง MARKET-CONTROL ของ E9", "━━━━━━━━━━━━━━━━━━",
            f"เจตนาของตลาด: {_fmt(pick('market_intent','intent'))}", f"ฝ่ายที่ได้เปรียบ: {_fmt(pick('dominant_side','dominant'))}",
            f"ฝ่ายที่ถูกควบคุม: {_fmt(pick('controlled_side'))}", f"ฝ่ายที่ติดกับ: {_fmt(pick('trapped_side'))}",
            f"เป้าหมาย LIQUIDITY: {_fmt(pick('liquidity_target'))}", f"ทิศทาง REPRICING: {_fmt(pick('repricing_direction','repricing_thesis'))}",
            f"ความแข็งแรงของการควบคุม: {_fmt(pick('control_strength','market_control_strength'))}"]


def format_decision(result: DecisionResult) -> str:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed: raise ValueError("Only actionable E9 BUY/SELL decisions can be notified")
    plan = result.trade_plan; required = ("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2")
    if not plan.get("valid") or any(k not in plan for k in required): raise ValueError("Actionable E9 decision requires a complete E8 trade plan")
    lines = [f"{'🟢 BUY' if result.decision == 'BUY' else '🔴 SELL'}", "", f"📊 สินทรัพย์: {result.symbol}", f"⏱ Timeframe: {result.timeframe}", "🧠 E1-E8 ให้หลักฐาน → E9 เป็น Final Decision Authority", "", "━━━━━━━━━━━━━━━━━━", "🧠 สรุปจากแต่ละ Engine", "━━━━━━━━━━━━━━━━━━"]
    for engine in result.engines: lines += ["", _engine_answer(engine)]
    lines += _e9_control_lines(result)
    lines += ["", "━━━━━━━━━━━━━━━━━━", "🎯 FINAL DECISION", "━━━━━━━━━━━━━━━━━━", f"🟢 E9 อนุมัติการออกออเดอร์: {result.decision}", "", "━━━━━━━━━━━━━━━━━━", "📋 Trade Plan", "━━━━━━━━━━━━━━━━━━", f"📍 Entry: {plan['entry']}", f"🛑 Stop Loss: {plan['stop_loss']}", f"🎯 Take Profit 1: {plan['take_profit_1']}", f"🎯 Take Profit 2: {plan['take_profit_2']}", f"📐 RR: 1:{plan['rr_tp2']:.1f}"]
    return _validate("\n".join(lines))


def format_startup(symbols: list[str]) -> str:
    return _validate("\n".join(["🟢 ระบบ PRODUCTION-V2 เริ่มทำงาน", "", "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9", f"📊 สินทรัพย์: {', '.join(symbols)}", "⏱ Timeframe: M5", "🧠 E9: Final Decision Authority + MARKET-CONTROL", "", "🔄 ทุกแท่ง M5 ที่ปิดจะเริ่มวิเคราะห์ใหม่ตั้งแต่ E1", "🎯 E9 เท่านั้นที่มีสิทธิ์ตัดสิน BUY / SELL / NO_TRADE", "📡 Telegram: พร้อมส่งสถานะ, NO_TRADE และ Trade Alert", "", "✅ ระบบพร้อมทำงาน"]))


def format_status(status: dict[str, Any]) -> str:
    timestamp = status.get("timestamp"); timestamp_text = timestamp.strftime("%d/%m/%Y %H:%M:00") if isinstance(timestamp, datetime) else str(timestamp or datetime.now().strftime("%d/%m/%Y %H:%M:00")); prices = status.get("prices", {}); market_states = status.get("market_states", {})
    def price_text(symbol: str) -> str:
        if market_states.get(symbol) == "MARKET_CLOSED": return "🔴 ตลาดปิด"
        value = prices.get(symbol)
        if value is None: return "ไม่พร้อมใช้งาน"
        try: return f"{float(value):,.2f}"
        except (TypeError, ValueError): return str(value)
    return _validate("\n".join(["✅ สถานะระบบ PRODUCTION-V2", "", "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9", "⏱ Timeframe: M5", "", f"🚨 เวลาแจ้งเตือน: {timestamp_text} (ประเทศไทย)", "", "📡 สถานะตลาด/ราคาเปิดแท่ง M5:", f"🌕 GOLD: {price_text('GOLD')}", f"🪙 BTC: {price_text('BTC')}", "", "🎯 E9 เท่านั้นเป็น Final Decision Authority", "", "✅ ระบบทำงานปกติ"]))


def format_critical(message: str, component: str) -> str:
    return _validate(f"🔴 ระบบผิดปกติ\n\n⚠️ ส่วนที่มีปัญหา: {component}\n📌 รายละเอียด: {message}\n\n⛔ กรุณาตรวจสอบระบบ")


def _chunk_text(text: str, limit: int = TELEGRAM_MAX_TEXT) -> list[str]:
    if len(text) <= limit: return [text]
    chunks: list[str] = []; current: list[str] = []; size = 0
    for line in text.splitlines(keepends=True):
        if current and size + len(line) > limit: chunks.append("".join(current).rstrip()); current, size = [], 0
        if len(line) > limit:
            chunks.extend(line[i:i + limit].rstrip() for i in range(0, len(line), limit)); continue
        current.append(line); size += len(line)
    if current: chunks.append("".join(current).rstrip())
    return chunks


def send(text: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return False
    for chunk in _chunk_text(text):
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": chunk}, timeout=15)
        if not response.ok:
            try: detail = response.json().get("description", response.text)
            except ValueError: detail = response.text
            raise RuntimeError(f"Telegram sendMessage failed ({response.status_code}): {detail}")
    return True


def send_decision(result: DecisionResult) -> bool:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed: return False
    return send(format_decision(result))

"""Professional Decision Engine overlay for the production 9-engine architecture."""
from __future__ import annotations
from typing import Callable

ENGINE_VERSION = "PROFESSIONAL-DECISION-9E-v1.0"


def _num(value, default=None):
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _reason_list(value):
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value if x is not None]
    return [str(value)] if value else []


def _regime_name(result):
    regime = result.get("regime")
    if isinstance(regime, dict):
        return regime.get("m5_regime") or regime.get("regime") or "UNKNOWN"
    return regime or result.get("m5_regime") or "UNKNOWN"


def _selected(result):
    x = result.get("selected_setup")
    return x if isinstance(x, dict) else {}


def _evidence(result, original_signal):
    selected = _selected(result)
    evidence = selected.get("evidence") if isinstance(selected.get("evidence"), dict) else {}
    score = result.get("setup_score") if isinstance(result.get("setup_score"), dict) else {}
    levels = result.get("trade_levels") if isinstance(result.get("trade_levels"), dict) else {}
    reasons = _reason_list(result.get("rejection_reasons"))
    regime = _regime_name(result)
    dq = result.get("data_quality") if isinstance(result.get("data_quality"), dict) else {}
    dq_errors = [x for v in dq.values() if isinstance(v, (list, tuple)) for x in v]
    e1_state = "UNKNOWN" if dq_errors else (regime or "UNKNOWN")
    strategy = result.get("strategy") or selected.get("strategy") or "NONE"
    e2_playbook = strategy if strategy != "NONE" else "NO_PLAYBOOK"

    structure_keys = ("choch_index", "choch_swing", "structure", "bos", "structural_alignment", "swing_high", "swing_low")
    liquidity_keys = ("sweep_index", "sweep_low", "sweep_high", "liquidity", "liquidity_zone", "sweep", "breakout_index")
    location_keys = ("zone", "fvg", "order_block", "htf_zone_m15", "htf_zone_h1", "location", "extension", "space", "resistance", "support")
    e3_present = any(k in evidence and evidence.get(k) not in (None, False, "") for k in structure_keys)
    e4_present = any(k in evidence and evidence.get(k) not in (None, False, "") for k in liquidity_keys)
    e5_present = any(k in evidence and evidence.get(k) not in (None, False, "") for k in location_keys)

    e6_setup = bool(selected) and bool(selected.get("status") in (None, "PASS"))
    e6_score = _num(score.get("score"), _num(selected.get("quality"), 0))
    e6_quality_ok = e6_score is not None and e6_score > 0
    trigger_id = result.get("trigger_id") or selected.get("trigger_signature")
    entry_type = result.get("entry_type") or selected.get("entry_type_hint")
    e7_confirmed = bool(trigger_id) and original_signal in ("BUY", "SELL") and entry_type not in (None, "NO_TRIGGER")
    rr = _num(levels.get("risk_reward"))
    minimum_rr = _num(levels.get("minimum_rr"), _num(result.get("rr_target")))
    e8_valid = bool(levels.get("valid")) and rr is not None and (minimum_rr is None or rr >= minimum_rr)

    ledger = {
        "E1": {"question": "Market State คืออะไร?", "state": e1_state, "support": not bool(dq_errors), "hard_gate": not bool(dq_errors), "reasons": dq_errors},
        "E2": {"question": "Regime/Playbook ที่เหมาะคืออะไร?", "playbook": e2_playbook, "support": e2_playbook != "NO_PLAYBOOK", "hard_gate": True, "reasons": []},
        "E3": {"question": "Structure กำลังบอกอะไร?", "state": "EVIDENCE_PRESENT" if e3_present else "UNKNOWN", "support": e3_present, "hard_gate": True, "reasons": [] if e3_present else ["STRUCTURE_EVIDENCE_UNAVAILABLE"]},
        "E4": {"question": "Liquidity อยู่ที่ไหนและ Price Action ทำอะไรกับมัน?", "state": "EVIDENCE_PRESENT" if e4_present else "UNKNOWN", "support": e4_present, "hard_gate": True, "reasons": [] if e4_present else ["LIQUIDITY_EVIDENCE_UNAVAILABLE"]},
        "E5": {"question": "ราคาปัจจุบันอยู่ใน Location ที่ได้เปรียบหรือไม่?", "state": "EVIDENCE_PRESENT" if e5_present else "UNKNOWN", "support": e5_present, "hard_gate": True, "reasons": [] if e5_present else ["LOCATION_EVIDENCE_UNAVAILABLE"]},
        "E6": {"question": "มี Trade Setup อะไรและอยู่ระยะไหน?", "state": "VALID_SETUP" if e6_setup and e6_quality_ok else "NO_VALID_SETUP", "support": e6_setup and e6_quality_ok, "hard_gate": True, "reasons": reasons if not (e6_setup and e6_quality_ok) else []},
        "E7": {"question": "Setup ได้รับ Trigger/Confirmation แล้วหรือยัง?", "state": "CONFIRMED" if e7_confirmed else "NO_TRIGGER", "support": e7_confirmed, "hard_gate": True, "reasons": [] if e7_confirmed else ["NO_TRIGGER_OR_CONFIRMATION"]},
        "E8": {"question": "ถ้าเสี่ยงเงิน ณ จุดนี้ Trade Economics คุ้มไหม?", "state": "ECONOMICS_VALID" if e8_valid else "ECONOMICS_INVALID", "support": e8_valid, "hard_gate": True, "reasons": [] if e8_valid else ["TRADE_ECONOMICS_INVALID"]},
    }
    return ledger, evidence, levels


def _professional_analyze(original_analyze: Callable[..., dict], legacy_engine_version: str, *args, **kwargs):
    result = original_analyze(*args, **kwargs)
    if not isinstance(result, dict):
        return result
    original_signal = str(result.get("signal") or "NO_TRADE").upper()
    ledger, raw_evidence, levels = _evidence(result, original_signal)
    hard_failures = []
    for engine_id, item in ledger.items():
        if item["hard_gate"] and not item["support"]:
            hard_failures.extend(f"{engine_id}:{r}" for r in item.get("reasons", []) or [item["state"]])
    supporting = [k for k, v in ledger.items() if v.get("support")]
    unknown = [k for k, v in ledger.items() if v.get("state") == "UNKNOWN"]
    if original_signal in ("BUY", "SELL") and not hard_failures:
        final_signal = original_signal
        decision_reason = "E1-E8 evidence is present and risk-valid; E9 authorizes final action."
    else:
        final_signal = "NO_TRADE"
        decision_reason = "E9 blocked execution because one or more mandatory evidence layers are missing or invalid."

    result = dict(result)
    result["legacy_engine_version"] = legacy_engine_version
    result["engine_version"] = ENGINE_VERSION
    result["decision_authority"] = "E9"
    result["professional_decision"] = {
        "cycle_type": "FRESH_CLOSED_M5_CYCLE",
        "question": "ตลาดกำลังให้โอกาสแบบไหน และหลักฐานทั้ง 8 ชั้นสอดคล้องกันมากพอที่จะยอมเสี่ยงเงินจริงหรือไม่?",
        "evidence": ledger,
        "supporting_engines": supporting,
        "unknown_engines": unknown,
        "hard_failures": hard_failures,
        "raw_setup_evidence": raw_evidence,
        "economics": {"valid": bool(levels.get("valid")), "risk_reward": levels.get("risk_reward"), "minimum_rr": levels.get("minimum_rr")},
        "e9": {"final_decision": final_signal, "execution_eligible": final_signal in ("BUY", "SELL"), "reason": decision_reason},
    }
    result["signal"] = final_signal
    result["direction"] = final_signal if final_signal in ("BUY", "SELL") else None
    result["decision_reason"] = decision_reason
    if final_signal == "NO_TRADE":
        result["rejection_reasons"] = list(dict.fromkeys(_reason_list(result.get("rejection_reasons")) + hard_failures + ["E9_NO_TRADE"]))
    return result


def wrap(original_analyze: Callable[..., dict], gold_analyze: Callable[..., dict] | None = None, legacy_engine_version: str = "UNKNOWN"):
    """Return the analyze callable used by the live scanner/scheduler."""
    def analyze(m5, m15=None, symbol=None, index=None, setup_state=None, h1=None):
        normalized = str(symbol or "").upper()
        if normalized in ("GOLD", "XAU/USD", "XAU/USDT", "XAU", "XAUUSD") and gold_analyze is not None:
            return _professional_analyze(gold_analyze, legacy_engine_version, m5, m15=m15, symbol=symbol, index=index, setup_state=setup_state, h1=h1)
        return _professional_analyze(original_analyze, legacy_engine_version, m5, m15=m15, symbol=symbol, index=index, setup_state=setup_state, h1=h1)
    return analyze

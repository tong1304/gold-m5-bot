from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V2"
VERSION = "2.0"
MIN_BARS = 30
MIN_RR = 1.50
ATR_PERIOD = 14
RISK_ATR_BUFFER = 1.20
STRUCTURE_LOOKBACK = 20


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    start = max(1, len(bars) - period)
    for i in range(start, len(bars)):
        h = _num(bars[i].get("high")); l = _num(bars[i].get("low")); pc = _num(bars[i - 1].get("close"))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _direction(value: Any) -> str:
    t = _text(value)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _evidence(e: EngineResult | None) -> dict[str, Any]:
    return dict(e.output or {}) if e else {}


def _first_num(mapping: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in mapping:
            v = _num(mapping.get(key), float("nan"))
            if v == v:
                return v
    return None


def _levels(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    """Extract only existing upstream evidence; never invent a new setup thesis."""
    highs = [_num(x.get("high")) for x in bars[-STRUCTURE_LOOKBACK:]]
    lows = [_num(x.get("low")) for x in bars[-STRUCTURE_LOOKBACK:]]
    hi20 = max(highs) if highs else 0.0
    lo20 = min(lows) if lows else 0.0

    protected_high = _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high"))
    protected_low = _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low"))
    resistance = _first_num(e5, ("next_resistance", "nearest_resistance", "resistance"))
    support = _first_num(e5, ("next_support", "nearest_support", "support"))
    liquidity_level = _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level"))

    if direction == "BUY":
        opposing = [x for x in (resistance, protected_high, liquidity_level, hi20) if x is not None and x > 0]
        target = min(opposing) if opposing else hi20
        invalidation = min(x for x in (protected_low, lo20) if x is not None and x > 0) if any(x is not None and x > 0 for x in (protected_low, lo20)) else lo20
    else:
        opposing = [x for x in (support, protected_low, liquidity_level, lo20) if x is not None and x > 0]
        target = max(opposing) if opposing else lo20
        invalidation = max(x for x in (protected_high, hi20) if x is not None and x > 0) if any(x is not None and x > 0 for x in (protected_high, hi20)) else hi20

    return {
        "protected_high": protected_high,
        "protected_low": protected_low,
        "next_resistance": resistance,
        "next_support": support,
        "liquidity_level": liquidity_level,
        "structure_high_20": hi20,
        "structure_low_20": lo20,
        "opposing_levels": opposing,
        "nearest_opposing_level": target,
        "structural_invalidation": invalidation,
    }


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 is the independent economic/risk gate between E7 confirmation and E9 decision authority."""
    bars = list(snapshot.get("bars") or [])
    e5o = _evidence(upstream.get("E5")); e6o = _evidence(upstream.get("E6")); e7o = _evidence(upstream.get("E7"))
    e3o = _evidence(upstream.get("E3")); e4o = _evidence(upstream.get("E4"))
    base = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "reasoning_role": "TRADE_ECONOMICS_RISK_ANALYST", "decision_authority": "E9",
        "trade_decision_authority": False, "closed_candle_only": True, "lookahead": False,
    }
    if len(bars) < MIN_BARS:
        return EngineResult("E8", NAME, False, 0.0, {**base, "state": "WAIT", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "supporting_evidence": [], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["sufficient risk sample"], "invalidation": ["new closed candle"]}, ("INSUFFICIENT_DATA",))

    direction = _direction(e6o.get("direction", e6o.get("direction_thesis")))
    setup = str(e6o.get("setup") or e6o.get("setup_family") or "NONE")
    confirmation = _text(e7o.get("confirmation"))
    atr = max(_atr(bars), 1e-9)
    entry = _num(bars[-1].get("close"))
    counter: list[str] = []; missing: list[str] = []; support: list[str] = []

    if direction not in {"BUY", "SELL"}: counter.append("NO_VALID_DIRECTION")
    if confirmation != "CONFIRMED": missing.append("ENTRY_CONFIRMATION")
    if not setup or _text(setup) in {"NONE", "UNKNOWN", "UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")

    levels = _levels(e3o, e4o, e5o, bars, direction) if direction in {"BUY", "SELL"} else {}
    protected = levels.get("structural_invalidation")
    nearest = levels.get("nearest_opposing_level")
    plan: dict[str, Any] = {}

    if direction in {"BUY", "SELL"}:
        # Structural invalidation is primary. ATR is only a survivability buffer.
        if direction == "BUY":
            candidates = [x for x in (protected, entry - RISK_ATR_BUFFER * atr) if x is not None and x < entry]
            stop = min(candidates) if candidates else None
        else:
            candidates = [x for x in (protected, entry + RISK_ATR_BUFFER * atr) if x is not None and x > entry]
            stop = max(candidates) if candidates else None

        if stop is None:
            counter.append("STRUCTURAL_INVALIDATION_UNCLEAR")
        else:
            risk = abs(entry - stop)
            if risk <= 0:
                counter.append("INVALID_RISK_DISTANCE")
            else:
                # Target is structural/liquidity based; minimum RR is a gate, not a target generator.
                target = nearest
                if target is None or (direction == "BUY" and target <= entry) or (direction == "SELL" and target >= entry):
                    counter.append("NO_USABLE_STRUCTURAL_TARGET")
                else:
                    reward = abs(target - entry)
                    raw_rr = reward / risk
                    tp1 = entry + reward * 0.50 if direction == "BUY" else entry - reward * 0.50
                    tp2 = target
                    space_r = reward / risk
                    if raw_rr < MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")
                    if space_r < MIN_RR: counter.append("STRUCTURAL_SPACE_INSUFFICIENT")
                    plan = {
                        "valid": not counter,
                        "entry": entry, "stop_loss": stop, "take_profit_1": tp1, "take_profit_2": tp2,
                        "risk_distance": risk, "reward_distance": reward, "rr_tp2": raw_rr,
                        "real_rr": raw_rr, "structural_space_r": space_r, "rr_minimum": MIN_RR,
                        "target_type": "STRUCTURAL_OR_LIQUIDITY", "target_level": target,
                        "structural_invalidation": protected, "risk_buffer_atr": RISK_ATR_BUFFER,
                    }
                    support += [f"atr={atr:.6f}", f"risk_distance={risk:.6f}", f"real_rr={raw_rr:.3f}", f"structural_space_r={space_r:.3f}"]

    # Explicit opposing liquidity from E4 is treated as a risk only when it is actually between entry and target.
    liq = levels.get("liquidity_level") if levels else None
    target = plan.get("take_profit_2")
    if liq is not None and target is not None:
        between = min(entry, target) < liq < max(entry, target)
        if between and abs(liq - entry) / max(plan.get("risk_distance", atr), 1e-9) < MIN_RR:
            counter.append("OPPOSING_LIQUIDITY_TOO_CLOSE")

    # Consume structured E5 location evidence without allowing a text finding to create the whole decision.
    location = _text(e5o.get("structural_location"))
    space = _first_num(e5o, ("available_space_atr_long", "available_space_atr_short"))
    if "SPACE_CONSTRAINED" in _text(e5o.get("finding")) or (space is not None and space < 0.75):
        counter.append("LOCATION_SPACE_CONSTRAINED")

    # Volatility/execution sanity: a very large current candle relative to ATR makes the proposed stop less survivable.
    last_range = _num(bars[-1].get("high")) - _num(bars[-1].get("low"))
    volatility_ratio = last_range / atr
    if volatility_ratio >= 2.5:
        counter.append("VOLATILITY_RISK_HIGH")
    if plan and plan.get("risk_distance", 0) < 0.50 * atr:
        counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")

    critical = {"NO_VALID_DIRECTION", "ENTRY_CONFIRMATION", "VALID_SETUP_THESIS", "STRUCTURAL_INVALIDATION_UNCLEAR", "INVALID_RISK_DISTANCE", "NO_USABLE_STRUCTURAL_TARGET", "REAL_RR_BELOW_MINIMUM", "STRUCTURAL_SPACE_INSUFFICIENT", "OPPOSING_LIQUIDITY_TOO_CLOSE", "LOCATION_SPACE_CONSTRAINED", "VOLATILITY_RISK_HIGH", "STOP_TOO_TIGHT_FOR_VOLATILITY"}
    counter = _dedupe(counter); missing = _dedupe(missing)
    risk_ready = bool(plan.get("valid")) and not any(x in critical for x in counter) and not missing
    economic = "ATTRACTIVE" if risk_ready else "CONDITIONAL" if plan and not any(x in counter for x in {"REAL_RR_BELOW_MINIMUM", "STRUCTURAL_SPACE_INSUFFICIENT", "STRUCTURAL_INVALIDATION_UNCLEAR", "NO_USABLE_STRUCTURAL_TARGET"}) else "UNATTRACTIVE" if plan else "UNRESOLVED"
    gate = economic == "ATTRACTIVE" and confirmation == "CONFIRMED" and direction in {"BUY", "SELL"} and risk_ready
    score = 95.0 if gate else 70.0 if economic == "CONDITIONAL" else 35.0 if economic == "UNATTRACTIVE" else 20.0

    invalidation = ["closed-candle structural invalidation", "risk/reward falls below minimum", "opposing liquidity blocks target", "available space collapses", "volatility becomes materially abnormal"]
    output = {
        **base, "state": economic, "economic_state": economic, "risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        "direction": direction, "setup": setup, "confirmation": confirmation, "trade_plan": plan,
        "risk_model": {"atr": atr, "atr_period": ATR_PERIOD, "last_range_atr": volatility_ratio, "structure_lookback": STRUCTURE_LOOKBACK},
        "structural_evidence": levels, "location_evidence": {"structural_location": location, "available_space_atr": space},
        "supporting_evidence": support, "counter_evidence": counter, "missing_evidence": missing,
        "invalidation": invalidation,
        "professional_reasoning": {
            "8A_data_integrity": "PASS",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "PASS" if plan.get("structural_invalidation") is not None else "FAIL",
            "8E_liquidity_risk": "PASS" if "OPPOSING_LIQUIDITY_TOO_CLOSE" not in counter else "FAIL",
            "8F_available_space": "PASS" if plan.get("structural_space_r", 0) >= MIN_RR else "FAIL",
            "8G_dynamic_target": "PASS" if plan.get("target_type") == "STRUCTURAL_OR_LIQUIDITY" else "FAIL",
            "8H_real_rr": "PASS" if plan.get("real_rr", 0) >= MIN_RR else "FAIL",
            "8I_volatility_execution": "PASS" if "VOLATILITY_RISK_HIGH" not in counter and "STOP_TOO_TIGHT_FOR_VOLATILITY" not in counter else "FAIL",
            "8J_trade_economics": economic,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
            "decision_path": "Risk evaluates survivability and economics; E9 retains final trade authority.",
        },
    }
    reasons = () if gate else tuple(counter + missing or ["ECONOMICS_NOT_READY"])
    return EngineResult("E8", NAME, gate, score, output, reasons)

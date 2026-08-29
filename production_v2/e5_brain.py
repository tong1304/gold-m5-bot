from __future__ import annotations

"""E5 — Professional Location / Value Brain v9.1.

E5 evaluates price geometry only: value, structure, liquidity, extension,
available space, asymmetry, repricing and counter-evidence. E9 owns decisions.
"""

from math import isfinite
from statistics import mean, median
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V9_1"
VERSION = "9.1"
QUESTION = "Is current location advantageous?"
MIN_BARS, ATR_PERIOD = 80, 14
VALUE_LOOKBACK, STRUCTURE_LOOKBACK, LIQUIDITY_LOOKBACK = 20, 60, 30
PIVOT_WING = 2
DISCOUNT, PREMIUM = 0.35, 0.65


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _bars(s: dict[str, Any]) -> tuple[list[dict[str, float]], list[str]]:
    out, problems = [], []
    for i, raw in enumerate(s.get("bars") or []):
        if not isinstance(raw, dict):
            problems.append(f"BAR_{i}_INVALID"); continue
        o, h, l, c = (_num(raw.get(k)) for k in ("open", "high", "low", "close"))
        v = _num(raw.get("volume"))
        if None in (o, h, l, c) or h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"BAR_{i}_OHLC_INVALID"); continue
        b = {"open": float(o), "high": float(h), "low": float(l), "close": float(c)}
        if v is not None and v >= 0: b["volume"] = float(v)
        out.append(b)
    return out, problems


def _atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2: return 0.0
    sample, trs = bars[-(period + 1):], []
    for i, b in enumerate(sample):
        if i == 0: trs.append(b["high"] - b["low"]); continue
        pc = sample[i - 1]["close"]
        trs.append(max(b["high"] - b["low"], abs(b["high"] - pc), abs(b["low"] - pc)))
    return mean(trs[-period:]) if trs else 0.0


def _range(bars: list[dict[str, float]], n: int) -> tuple[float, float]:
    x = bars[-n:]
    return min(b["low"] for b in x), max(b["high"] for b in x)


def _value(bars: list[dict[str, float]]) -> tuple[float, str]:
    x = bars[-VALUE_LOOKBACK:]
    prices = [(b["high"] + b["low"] + 2*b["close"]) / 4 for b in x]
    vols = [b.get("volume", 0.0) for b in x]
    total = sum(v for v in vols if v > 0)
    if total > 0:
        return sum(p*v for p, v in zip(prices, vols) if v > 0) / total, "VOLUME_WEIGHTED_TYPICAL_PRICE"
    return median(prices), "MEDIAN_TYPICAL_PRICE"


def _pivots(bars: list[dict[str, float]]) -> tuple[list[float], list[float]]:
    hi, lo = [], []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        w = bars[i-PIVOT_WING:i+PIVOT_WING+1]
        if bars[i]["high"] >= max(b["high"] for b in w): hi.append(bars[i]["high"])
        if bars[i]["low"] <= min(b["low"] for b in w): lo.append(bars[i]["low"])
    return hi[-20:], lo[-20:]


def _above(price: float, levels: list[float], tol: float) -> float | None:
    x = [v for v in levels if v > price + tol]
    return min(x) if x else None


def _below(price: float, levels: list[float], tol: float) -> float | None:
    x = [v for v in levels if v < price - tol]
    return max(x) if x else None


def _atr_dist(price: float, level: float | None, atr: float) -> float | None:
    return None if level is None or atr <= 0 else abs(price-level)/atr


def _space_component(x: float | None) -> float:
    if x is None or x >= 2: return 1.0
    if x >= 1: return 0.70
    if x >= 0.5: return 0.35
    return 0.10


def _space_label(x: float | None) -> str:
    if x is None or x >= 2: return "OPEN"
    if x >= 1: return "LIMITED"
    if x >= 0.5: return "CONSTRAINED"
    return "VERY_CONSTRAINED"


def _extension(x: float) -> str:
    if x < 0.75: return "NORMAL"
    if x < 1.50: return "STRETCHED"
    if x < 2.50: return "EXTENDED"
    return "EXCESSIVE"


def _context(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    ctx, evidence, conflicts = {}, [], []
    for eid in ("E1", "E2", "E3", "E4"):
        p = (permitted or {}).get(eid)
        if not isinstance(p, dict): continue
        e = p.get("evidence")
        payload = e.get("output") if isinstance(e, dict) and isinstance(e.get("output"), dict) else e
        if not isinstance(payload, dict): payload = p.get("output") or {}
        if not isinstance(payload, dict): continue
        ctx[eid] = dict(payload); evidence.append(f"{eid}_QUALITATIVE_CONTEXT_READ")
        t = str(payload).upper()
        if any(k in t for k in ("CONFLICT", "MIXED", "UNRESOLVED", "PENDING")):
            conflicts.append(f"{eid}_CONTEXT_CONFLICT")
    return ctx, evidence, conflicts


def _fresh_sweeps(bars: list[dict[str, float]]) -> tuple[bool, bool, float, float]:
    if len(bars) <= LIQUIDITY_LOOKBACK: return False, False, 0.0, 0.0
    prior, last = bars[-(LIQUIDITY_LOOKBACK+1):-1], bars[-1]
    ph, pl = max(b["high"] for b in prior), min(b["low"] for b in prior)
    return last["high"] > ph and last["close"] < ph, last["low"] < pl and last["close"] > pl, ph, pl


def _side(side: str, vp: float, vd: float, ext: str, blocked: bool, sweep: bool, space: float | None) -> dict[str, Any]:
    long = side == "LONG"
    fav = vp <= DISCOUNT if long else vp >= PREMIUM
    adverse = vp >= PREMIUM if long else vp <= DISCOUNT
    value = 1.0 if fav else 0.0 if adverse else 0.55
    structure, liquidity = 0.0 if blocked else 1.0, 1.0 if sweep else 0.45
    extension = {"NORMAL":1.0, "STRETCHED":0.65, "EXTENDED":0.30, "EXCESSIVE":0.05}[ext]
    space_c = _space_component(space)
    score = round(0.30*value + 0.15*structure + 0.15*liquidity + 0.20*extension + 0.20*space_c, 4)
    evidence, counter = [], []
    evidence.append("VALUE_FAVORABLE" if fav else "VALUE_NEUTRAL") if not adverse else counter.append("VALUE_ADVERSE")
    evidence.append("STRUCTURAL_SPACE_AVAILABLE") if not blocked else counter.append("OPPOSING_STRUCTURE_NEARBY")
    evidence.append("FRESH_LIQUIDITY_SWEEP_SUPPORTIVE") if sweep else counter.append("NO_FRESH_LIQUIDITY_CONFIRMATION")
    evidence.append(f"EXTENSION_{ext}") if ext in {"NORMAL","STRETCHED"} else counter.append("EXTENSION_RISK")
    if space is not None and space < 1: counter.append("SPACE_CONSTRAINED")
    if space is not None and space < 0.5: counter.append("SPACE_VERY_CONSTRAINED")
    quality = "HIGH" if score >= .72 else "ACCEPTABLE" if score >= .58 else "CONDITIONAL" if score >= .45 else "UNFAVORABLE"
    return {"score":score,"quality":quality,"evidence":evidence,"counter_evidence":counter,
            "components":{"value":value,"structure":structure,"liquidity":liquidity,"extension":extension,"space":space_c},
            "value_distance_atr":round(vd,6),"available_space_atr":None if space is None else round(space,6)}


def _repricing(side: str, vp: float, ext: str, space: float | None, blocked: bool, sweep: bool, value_response: str) -> dict[str, Any]:
    """Describe what would improve location; never predict a reversal.

    Acceptance beyond value is continuation evidence, not repricing. Repricing
    becomes active only when price is actually moving back toward accepted value.
    """
    c = []
    accepted_counter_value = value_response in {"ACCEPTED_ABOVE_VALUE", "ACCEPTED_BELOW_VALUE"}
    rejection = value_response in {"REJECTED_ABOVE_VALUE", "REJECTED_BELOW_VALUE"}

    if side == "LONG":
        if vp > DISCOUNT:
            c.append("PRICE_REPRICES_TOWARD_DISCOUNT_OR_ACCEPTED_VALUE")
        if value_response == "REJECTED_BELOW_VALUE":
            c.append("LOW_VALUE_REJECTION_CONFIRMED")
        elif value_response == "ACCEPTED_BELOW_VALUE":
            c.append("DISCOUNT_ACCEPTED_CONTINUATION_RISK")
        elif not sweep:
            c.append("FRESH_LOW_LIQUIDITY_REJECTION_OR_RECLAIM")
    else:
        if vp < PREMIUM:
            c.append("PRICE_REPRICES_TOWARD_PREMIUM_OR_ACCEPTED_VALUE")
        if value_response == "REJECTED_ABOVE_VALUE":
            c.append("HIGH_VALUE_REJECTION_CONFIRMED")
        elif value_response == "ACCEPTED_ABOVE_VALUE":
            c.append("PREMIUM_ACCEPTED_CONTINUATION_RISK")
        elif not sweep:
            c.append("FRESH_HIGH_LIQUIDITY_REJECTION_OR_RECLAIM")

    if ext in {"EXTENDED","EXCESSIVE"}: c.append("EXTENSION_NORMALIZES")
    if space is not None and space < 1: c.append("AVAILABLE_SPACE_REOPENS")

    if rejection:
        mode = "REJECTION_CONFIRMED"
    elif accepted_counter_value:
        mode = "ACCEPTANCE_CONTINUATION"
    elif abs(vp - 0.5) <= 0.15:
        mode = "VALUE_REBALANCING"
    else:
        mode = "WAIT_FOR_REPRICING"

    return {
        "required_for_improvement": c,
        "thesis_invalidators":["PRICE_ACCEPTS_DEEPER_COUNTER_VALUE","OPPOSING_STRUCTURE_BECOMES_IMMEDIATE"],
        "mode": mode,
        "is_prediction": False,
    }


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    e = problems or ["NO_RELIABLE_EVIDENCE"]
    return {"architecture":ARCHITECTURE,"version":VERSION,"question":QUESTION,
            "task":"ASSESS_PRICE_LOCATION_ONLY","location_state":"UNRESOLVED","location_quality":"UNRESOLVED",
            "direction":"NEUTRAL","value_state":"UNKNOWN","structural_location":"UNKNOWN",
            "liquidity_location":"UNKNOWN","extension_state":"UNKNOWN","available_space":"UNKNOWN",
            "available_space_atr":None,"long_location_quality":"UNKNOWN","short_location_quality":"UNKNOWN",
            "preferred_location":"NONE","confidence":0.0,"evidence":e,"observations":e,"counter_evidence":[],
            "conflicts":problems,"reason_codes":["E5_DATA_INCOMPLETE"],
            "reasoning_trace":[f"QUESTION -> {QUESTION}",f"DATA_QUALITY -> {reason}"],
            "professional_reasoning":{"question":QUESTION,"thesis":reason,
                "evidence_hierarchy":"VALUE -> VALUE_RESPONSE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> REPRICING_MAP -> COUNTER_EVIDENCE",
                "upstream_decisions_used":False,"upstream_gates_used":False,"upstream_scores_used":False,
                "upstream_direction_used_for_location_score":False,"decision_authority":"E9_ONLY"},
            "trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"decision":None,
            "specialist_gate":"NONE","specialists":{},"specialists_active":False,"specialists_status":"NOT_USED"}


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Professional E5 location/value analysis; E9 remains decision authority."""
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])
    atr = _atr(bars)
    if atr <= 0:
        return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])

    price = bars[-1]["close"]
    value, value_method = _value(bars)
    vl, vh = _range(bars, VALUE_LOOKBACK)
    width = max(vh - vl, atr)
    vp = max(0.0, min(1.0, (price - vl) / width))
    vd = (price - value) / atr
    value_state = "DISCOUNT" if vp <= DISCOUNT else "PREMIUM" if vp >= PREMIUM else "EQUILIBRIUM"
    extension_atr = abs(vd)
    extension_state = _extension(extension_atr)

    sl, sh = _range(bars, STRUCTURE_LOOKBACK)
    phs, pls = _pivots(bars)
    tol = 0.15 * atr
    resistance, support = _above(price, phs + [sh], tol), _below(price, pls + [sl], tol)
    long_space, short_space = _atr_dist(price, resistance, atr), _atr_dist(price, support, atr)
    rd, sd = _atr_dist(price, sh, atr), _atr_dist(price, sl, atr)
    near_r, near_s = rd is not None and rd <= .75, sd is not None and sd <= .75
    structural = "COMPRESSED_STRUCTURE" if near_r and near_s else "AT_RESISTANCE" if near_r else "AT_SUPPORT" if near_s else "INSIDE_STRUCTURE"

    high_sweep, low_sweep, prior_high, prior_low = _fresh_sweeps(bars)
    liquidity = "BOTH_FRESH_SWEEPS" if high_sweep and low_sweep else "FRESH_HIGH_SWEEP" if high_sweep else "FRESH_LOW_SWEEP" if low_sweep else "NO_FRESH_SWEEP"

    # Closed-candle value response: discount/premium is a location fact, not
    # a reversal thesis. Acceptance and rejection must be observed first.
    lookback = min(5, len(bars) - 1)
    recent = bars[-lookback:]
    value_band = max(0.25 * atr, 0.10 * width)
    near_value = abs(price - value) <= value_band
    closes_below = sum(b["close"] < value - value_band for b in recent)
    closes_above = sum(b["close"] > value + value_band for b in recent)
    reclaim_from_below = any(b["low"] < value and b["close"] >= value for b in recent)
    reject_from_above = any(b["high"] > value and b["close"] <= value for b in recent)

    if reclaim_from_below and closes_below >= 1:
        value_response = "REJECTED_BELOW_VALUE"
    elif reject_from_above and closes_above >= 1:
        value_response = "REJECTED_ABOVE_VALUE"
    elif near_value:
        value_response = "ACCEPTING_VALUE"
    elif closes_below >= max(2, lookback // 2):
        value_response = "ACCEPTED_BELOW_VALUE"
    elif closes_above >= max(2, lookback // 2):
        value_response = "ACCEPTED_ABOVE_VALUE"
    else:
        value_response = "UNRESOLVED_VALUE_RESPONSE"

    # Acceptance beyond value means the auction is being accepted there; it is
    # not evidence that price is already repricing back. Repricing is a state
    # only when the observed response supports movement toward value.
    if value_response == "REJECTED_BELOW_VALUE":
        repricing_state = "REPRICING_FAILED"
    elif value_response == "REJECTED_ABOVE_VALUE":
        repricing_state = "REPRICING_FAILED"
    elif value_response == "ACCEPTED_BELOW_VALUE":
        repricing_state = "ACCEPTANCE_BELOW_VALUE"
    elif value_response == "ACCEPTED_ABOVE_VALUE":
        repricing_state = "ACCEPTANCE_ABOVE_VALUE"
    elif value_response == "ACCEPTING_VALUE":
        repricing_state = "REPRICING_STARTING"
    else:
        repricing_state = "NO_REPRICING"

    long_blocked = long_space is not None and long_space < .5
    short_blocked = short_space is not None and short_space < .5
    long_side = _side("LONG", vp, vd, extension_state, long_blocked, low_sweep, long_space)
    short_side = _side("SHORT", vp, vd, extension_state, short_blocked, high_sweep, short_space)

    # Professional rule: cheap/expensive without rejection is not a reversal
    # edge. Acceptance is explicitly treated as continuation evidence.
    if value_state == "DISCOUNT":
        if value_response in {"ACCEPTED_BELOW_VALUE", "UNRESOLVED_VALUE_RESPONSE"}:
            long_side["components"]["value"] *= .35
            long_side["counter_evidence"].append("DISCOUNT_WITHOUT_REJECTION")
        elif value_response == "REJECTED_BELOW_VALUE":
            long_side["components"]["value"] = min(1.0, long_side["components"]["value"] + .20)
            long_side["evidence"].append("DISCOUNT_REJECTION_CONFIRMED")
    elif value_state == "PREMIUM":
        if value_response in {"ACCEPTED_ABOVE_VALUE", "UNRESOLVED_VALUE_RESPONSE"}:
            short_side["components"]["value"] *= .35
            short_side["counter_evidence"].append("PREMIUM_WITHOUT_REJECTION")
        elif value_response == "REJECTED_ABOVE_VALUE":
            short_side["components"]["value"] = min(1.0, short_side["components"]["value"] + .20)
            short_side["evidence"].append("PREMIUM_REJECTION_CONFIRMED")

    def recompute(side_data: dict[str, Any]) -> None:
        c = side_data["components"]
        side_data["score"] = round(.30*c["value"] + .15*c["structure"] + .15*c["liquidity"] + .20*c["extension"] + .20*c["space"], 4)
        s = side_data["score"]
        side_data["quality"] = "HIGH" if s >= .72 else "ACCEPTABLE" if s >= .58 else "CONDITIONAL" if s >= .45 else "UNFAVORABLE"

    recompute(long_side)
    recompute(short_side)

    # E5 may describe a preferred location only when the location evidence is
    # asymmetric. Acceptance at premium/discount alone cannot create reversal bias.
    if long_side["score"] >= .58 and long_side["score"] > short_side["score"] + .05:
        preferred = "LONG"
    elif short_side["score"] >= .58 and short_side["score"] > long_side["score"] + .05:
        preferred = "SHORT"
    else:
        preferred = "NONE"

    if preferred == "NONE":
        if value_response in {"ACCEPTED_ABOVE_VALUE", "ACCEPTED_BELOW_VALUE"}:
            location_state = "ACCEPTED_AUCTION_NO_REVERSAL_EDGE"
        elif value_response == "ACCEPTING_VALUE":
            location_state = "WAIT_REPRICING"
        elif repricing_state == "REPRICING_FAILED":
            location_state = "WAIT_CONFIRMATION"
        else:
            location_state = "WAIT_REPRICING"
    else:
        location_state = "FAVORABLE_LOCATION"

    quality_score = max(long_side["score"], short_side["score"])
    confidence = round(max(0.0, min(1.0, quality_score)), 4)

    counter_evidence = []
    if extension_state in {"EXTENDED", "EXCESSIVE"}: counter_evidence.append("EXTENSION_RISK")
    if not high_sweep and not low_sweep: counter_evidence.append("NO_FRESH_LIQUIDITY_CONFIRMATION")
    if long_space is not None and long_space < 1: counter_evidence.append("LONG_SPACE_CONSTRAINED")
    if short_space is not None and short_space < 1: counter_evidence.append("SHORT_SPACE_CONSTRAINED")
    if value_state == "DISCOUNT" and value_response != "REJECTED_BELOW_VALUE": counter_evidence.append("DISCOUNT_NOT_PROVEN_AS_REVERSAL")
    if value_state == "PREMIUM" and value_response != "REJECTED_ABOVE_VALUE": counter_evidence.append("PREMIUM_NOT_PROVEN_AS_REVERSAL")
    if value_response == "ACCEPTED_ABOVE_VALUE": counter_evidence.append("PREMIUM_ACCEPTED_CONTINUATION_RISK")
    if value_response == "ACCEPTED_BELOW_VALUE": counter_evidence.append("DISCOUNT_ACCEPTED_CONTINUATION_RISK")

    repricing = _repricing(
        preferred if preferred != "NONE" else ("LONG" if value_state == "DISCOUNT" else "SHORT" if value_state == "PREMIUM" else "LONG"),
        vp, extension_state,
        long_space if preferred == "LONG" else short_space if preferred == "SHORT" else None,
        long_blocked if preferred == "LONG" else short_blocked if preferred == "SHORT" else False,
        low_sweep if preferred == "LONG' else high_sweep if preferred == "SHORT" else (low_sweep or high_sweep),
        value_response,
    )

    ctx, upstream_evidence, conflicts = _context(permitted)
    evidence = [f"VALUE_{value_state}", f"VALUE_RESPONSE_{value_response}", f"REPRICING_{repricing_state}", f"STRUCTURE_{structural}", f"LIQUIDITY_{liquidity}", f"EXTENSION_{extension_state}"]
    observations = [
        f"closed_candles={len(bars)}", f"atr14_current={atr:.6f}", f"price={price:.8f}",
        f"value={value:.8f}", f"value_method={value_method}", f"value_position={vp:.4f}",
        f"value_distance_atr={vd:.6f}", f"value_state={value_state}", f"value_response={value_response}",
        f"repricing_state={repricing_state}", f"structural_location={structural}",
        f"next_resistance={resistance}", f"next_support={support}",
        f"available_space_atr_long={long_space}", f"available_space_atr_short={short_space}",
        f"extension_atr={extension_atr:.6f}", f"extension_state={extension_state}", f"liquidity_location={liquidity}",
    ]

    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": location_state,
        "location_quality": "HIGH" if confidence >= .72 else "ACCEPTABLE" if confidence >= .58 else "CONDITIONAL" if confidence >= .45 else "UNFAVORABLE",
        "direction": "NEUTRAL", "value_state": value_state, "value_response": value_response,
        "value_quality": "REJECTED" if value_response.startswith("REJECTED") else "ACCEPTED" if value_response.startswith("ACCEPTED") or value_response == "ACCEPTING_VALUE" else "UNRESOLVED",
        "structural_location": structural, "liquidity_location": liquidity,
        "extension_state": extension_state, "extension_atr": round(extension_atr, 6),
        "available_space": _space_label(long_space if preferred == "LONG" else short_space if preferred == "SHORT" else max((x for x in (long_space, short_space) if x is not None), default=None)),
        "available_space_atr": max((x for x in (long_space, short_space) if x is not None), default=None),
        "long_location_quality": long_side["quality"], "short_location_quality": short_side["quality"],
        "long_location_score": long_side["score"], "short_location_score": short_side["score"],
        "preferred_location": preferred, "confidence": confidence,
        "evidence": evidence + upstream_evidence, "observations": observations,
        "counter_evidence": counter_evidence, "conflicts": conflicts,
        "reason_codes": ["VALUE_LOCATION_ANALYSIS", "VALUE_RESPONSE_CLASSIFIED", "REPRICING_STATE_EXPLICIT", "COUNTER_EVIDENCE_APPLIED"],
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}", f"VALUE -> {value_state} distance={vd:.3f}ATR",
            f"VALUE_RESPONSE -> {value_response}", f"REPRICING -> {repricing_state}",
            f"STRUCTURE -> {structural}", f"LIQUIDITY -> {liquidity}", f"EXTENSION -> {extension_state}",
            f"ASYMMETRY -> LONG={long_side['score']:.4f} SHORT={short_side['score']:.4f}",
            f"LOCATION_DECISION -> {location_state}",
        ],
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": f"{location_state}: value={value_state}, response={value_response}, repricing={repricing_state}",
            "evidence_hierarchy": "VALUE -> VALUE_RESPONSE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> REPRICING_MAP -> COUNTER_EVIDENCE",
            "upstream_decisions_used": bool(ctx), "upstream_gates_used": False,
            "upstream_scores_used": False, "upstream_direction_used_for_location_score": False,
            "decision_authority": "E9_ONLY",
        },
        "repricing": repricing, "trade_decision_authority": False,
        "decision_authority": "E9_ONLY", "gate": None, "decision": None,
        "specialist_gate": "NONE", "specialists": {}, "specialists_active": False,
        "specialists_status": "NOT_USED",
    }

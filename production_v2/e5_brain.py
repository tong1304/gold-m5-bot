from __future__ import annotations

"""E5 — Professional Location / Value Brain v9.0.

Specialist question: "Is current location advantageous?"
E5 evaluates price geometry only: value, structure, liquidity, extension,
available space, asymmetry, repricing and counter-evidence. E1-E4 are
qualitative context only and cannot alter E5 scoring. E9 owns decisions.
"""

from math import isfinite
from statistics import mean, median
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V9_0"
VERSION = "9.0"
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


def _direction(ctx: dict[str, Any]) -> str:
    t = str(ctx).upper()
    up = any(k in t for k in ("TREND_UP", "BULLISH", "DIRECTION=UP", "PRESSURE=UP", "PRESSURE=BULLISH"))
    down = any(k in t for k in ("TREND_DOWN", "BEARISH", "DIRECTION=DOWN", "PRESSURE=DOWN", "PRESSURE=BEARISH"))
    return "UP" if up and not down else "DOWN" if down and not up else "NEUTRAL"


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


def _repricing(side: str, vp: float, ext: str, space: float | None, blocked: bool, sweep: bool) -> dict[str, Any]:
    c = []
    if side == "LONG":
        if vp > DISCOUNT: c.append("PRICE_REPRICES_TOWARD_DISCOUNT_OR_ACCEPTED_VALUE")
        if blocked: c.append("CLEAR_OPPOSING_STRUCTURE")
        if not sweep: c.append("FRESH_LOW_LIQUIDITY_REJECTION_OR_RECLAIM")
    else:
        if vp < PREMIUM: c.append("PRICE_REPRICES_TOWARD_PREMIUM_OR_ACCEPTED_VALUE")
        if blocked: c.append("CLEAR_OPPOSING_STRUCTURE")
        if not sweep: c.append("FRESH_HIGH_LIQUIDITY_REJECTION_OR_RECLAIM")
    if ext in {"EXTENDED","EXCESSIVE"}: c.append("EXTENSION_NORMALIZES")
    if space is not None and space < 1: c.append("AVAILABLE_SPACE_REOPENS")
    return {"required_for_improvement":c,
            "thesis_invalidators":["PRICE_ACCEPTS_DEEPER_COUNTER_VALUE","OPPOSING_STRUCTURE_BECOMES_IMMEDIATE"],
            "is_prediction":False}


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
                "evidence_hierarchy":"VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> REPRICING_MAP -> COUNTER_EVIDENCE",
                "upstream_decisions_used":False,"upstream_gates_used":False,"upstream_scores_used":False,
                "upstream_direction_used_for_location_score":False,"decision_authority":"E9_ONLY"},
            "trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"decision":None,
            "specialist_gate":"NONE","specialists":{},"specialists_active":False,"specialists_status":"NOT_USED"}


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS: return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])
    atr = _atr(bars)
    if atr <= 0: return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])
    price = bars[-1]["close"]

    value, value_method = _value(bars)
    vl, vh = _range(bars, VALUE_LOOKBACK)
    width = max(vh-vl, atr)
    vp = max(0.0, min(1.0, (price-vl)/width))
    vd = (price-value)/atr
    value_state = "DISCOUNT" if vp <= DISCOUNT else "PREMIUM" if vp >= PREMIUM else "EQUILIBRIUM"

    sl, sh = _range(bars, STRUCTURE_LOOKBACK)
    phs, pls = _pivots(bars)
    tol = 0.15*atr
    resistance, support = _above(price, phs+[sh], tol), _below(price, pls+[sl], tol)
    long_space, short_space = _atr_dist(price,resistance,atr), _atr_dist(price,support,atr)
    rd, sd = _atr_dist(price,sh,atr), _atr_dist(price,sl,atr)
    near_r, near_s = rd is not None and rd <= .75, sd is not None and sd <= .75
    structural = "COMPRESSED_STRUCTURE" if near_r and near_s else "AT_RESISTANCE" if near_r else "AT_SUPPORT" if near_s else "INSIDE_STRUCTURE"

    high_sweep, low_sweep, prior_high, prior_low = _fresh_sweeps(bars)
    liquidity = "BOTH_FRESH_SWEEPS" if high_sweep and low_sweep else "FRESH_HIGH_SWEEP" if high_sweep else "FRESH_LOW_SWEEP" if low_sweep else "NO_FRESH_SWEEP"
    extension_atr, extension_state = abs(vd), _extension(abs(vd))

    ctx, upstream_evidence, conflicts = _context(permitted)
    qualitative_direction = _direction(ctx)

    le = _side("LONG",vp,vd,extension_state,near_r,low_sweep,long_space)
    se = _side("SHORT",vp,vd,extension_state,near_s,high_sweep,short_space)
    gap = round(abs(le["score"]-se["score"]),4)
    # Qualitative direction may constrain a preferred-location label, but it
    # never changes either side's location score. Counter-direction preference
    # requires fresh current-candle liquidity evidence.
    short_allowed = not (qualitative_direction == "UP" and not high_sweep)
    long_allowed = not (qualitative_direction == "DOWN" and not low_sweep)
    preferred = "LONG" if long_allowed and gap >= .12 and le["score"] > se["score"] and max(le["score"],se["score"]) >= .45 else \
                "SHORT" if short_allowed and gap >= .12 and se["score"] > le["score"] and max(le["score"],se["score"]) >= .45 else \
                "BOTH_CONDITIONAL" if max(le["score"],se["score"]) >= .45 else "NONE"
    best = le["score"] if preferred=="LONG" else se["score"] if preferred=="SHORT" else max(le["score"],se["score"])

    lr, sr = (_repricing("LONG",vp,extension_state,long_space,near_r,low_sweep),
              _repricing("SHORT",vp,extension_state,short_space,near_s,high_sweep))

    hard = []
    if long_space is not None and long_space < .5: hard.append("LONG_SPACE_VERY_CONSTRAINED")
    if short_space is not None and short_space < .5: hard.append("SHORT_SPACE_VERY_CONSTRAINED")
    if extension_state in {"EXTENDED","EXCESSIVE"}: hard.append("EXTENSION_RISK")
    if value_state=="EQUILIBRIUM": hard.append("VALUE_NOT_DIRECTIONALLY_FAVORABLE")

    state = "WAIT_REPRICING" if preferred=="NONE" or extension_state in {"EXTENDED","EXCESSIVE"} else \
            "SPACE_CONSTRAINED" if hard else \
            "ADVANTAGEOUS" if best >= .72 else "ACCEPTABLE" if best >= .58 else "WAIT_REPRICING"
    quality = "HIGH" if best>=.72 else "ACCEPTABLE" if best>=.58 else "CONDITIONAL" if best>=.45 else "UNFAVORABLE"

    observations = [
        f"closed_candles={len(bars)}",f"atr14_current={atr:.6f}",f"price={price:.8f}",
        f"value={value:.8f}",f"value_method={value_method}",f"value_position={vp:.4f}",
        f"value_distance_atr={vd:.6f}",f"value_state={value_state}",
        f"STRUCTURAL_LOCATION={structural}",f"next_resistance={resistance}",f"next_support={support}",
        f"available_space_atr_long={long_space}",f"available_space_atr_short={short_space}",
        f"extension_atr={extension_atr:.6f}",f"extension_state={extension_state}",
        f"LIQUIDITY_LOCATION={liquidity}",f"LONG_LOCATION={le['score']:.3f}/{le['quality']}",
        f"SHORT_LOCATION={se['score']:.3f}/{se['quality']}",f"LOCATION_ASYMMETRY_GAP={gap:.4f}",
        f"QUALITATIVE_UPSTREAM_DIRECTION={qualitative_direction}",f"QUESTION -> {QUESTION}",
        f"VALUE -> {value_state} distance={vd:.3f}ATR",f"STRUCTURE -> {structural}",
        f"LIQUIDITY -> {liquidity}",f"EXTENSION -> {extension_state} {extension_atr:.3f}ATR",
        f"SPACE -> LONG={_space_label(long_space)} SHORT={_space_label(short_space)}",
    ]
    counter = le["counter_evidence"] + se["counter_evidence"] + hard
    reasons = []
    if extension_state in {"STRETCHED","EXTENDED","EXCESSIVE"}: reasons.append("EXTENSION_RISK")
    if long_space is not None and long_space < 1: reasons.append("LONG_SPACE_CONSTRAINED")
    if short_space is not None and short_space < 1: reasons.append("SHORT_SPACE_CONSTRAINED")
    if not high_sweep and not low_sweep: reasons.append("NO_FRESH_LIQUIDITY_CONFIRMATION")
    if value_state=="PREMIUM": reasons.append("VALUE_PREMIUM")
    if value_state=="DISCOUNT": reasons.append("VALUE_DISCOUNT")
    if preferred=="BOTH_CONDITIONAL": reasons.append("LOCATION_ASYMMETRY_NOT_DECISIVE")
    if preferred=="NONE": reasons.append("LOCATION_REPRICING_REQUIRED")
    if conflicts: reasons.append("UPSTREAM_CONTEXT_CONFLICT_NON_DECISIVE")

    trace = [f"QUESTION -> {QUESTION}",f"VALUE -> {value_state} distance={vd:.3f}ATR",
             f"STRUCTURE -> {structural}",f"LIQUIDITY -> {liquidity}",f"EXTENSION -> {extension_state}",
             f"SPACE -> LONG={_space_label(long_space)} SHORT={_space_label(short_space)}",
             f"ASYMMETRY -> LONG={le['score']:.3f} SHORT={se['score']:.3f} GAP={gap:.3f}",
             f"REPRICING_LONG -> {lr['required_for_improvement']}",f"REPRICING_SHORT -> {sr['required_for_improvement']}",
             f"COUNTER_EVIDENCE -> {counter}",f"THESIS -> {state}"]

    return {"architecture":ARCHITECTURE,"version":VERSION,"question":QUESTION,"task":"ASSESS_PRICE_LOCATION_ONLY",
            "location_state":state,"location_quality":quality,"direction":qualitative_direction,
            "value_state":value_state,"value_price":round(value,8),"value_method":value_method,
            "value_position":round(vp,6),"value_distance_atr":round(vd,6),
            "structural_location":structural,"structure_low":round(sl,8),"structure_high":round(sh,8),
            "next_resistance":None if resistance is None else round(resistance,8),
            "next_support":None if support is None else round(support,8),
            "liquidity_location":liquidity,"fresh_high_sweep":high_sweep,"fresh_low_sweep":low_sweep,
            "extension_atr":round(extension_atr,6),"extension_state":extension_state,
            "available_space":"LONG_AND_SHORT" if long_space is not None and short_space is not None else "PARTIAL",
            "available_space_atr":{"LONG":None if long_space is None else round(long_space,6),
                                   "SHORT":None if short_space is None else round(short_space,6)},
            "long_location_quality":le["quality"],"short_location_quality":se["quality"],
            "long_location_score":le["score"],"short_location_score":se["score"],
            "location_asymmetry_gap":gap,"preferred_location":preferred,
            "long_components":le["components"],"short_components":se["components"],
            "long_repricing":lr,"short_repricing":sr,
            "evidence":upstream_evidence+le["evidence"]+se["evidence"],"observations":observations,
            "counter_evidence":counter,"conflicts":conflicts,"reason_codes":reasons,
            "confidence":round(min(1,.86 if preferred!="NONE" else .80),4),"reasoning_trace":trace,
            "professional_reasoning":{"question":QUESTION,"thesis":state,
                "evidence_hierarchy":"VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> REPRICING_MAP -> COUNTER_EVIDENCE",
                "upstream_decisions_used":False,"upstream_gates_used":False,"upstream_scores_used":False,
                "upstream_direction_used_for_location_score":False,"upstream_context_role":"QUALITATIVE_TRACE_ONLY",
                "fresh_liquidity_source":"CURRENT_CLOSED_CANDLE_ONLY","lookahead_used":False,
                "execution_decision_made":False,"decision_authority":"E9_ONLY"},
            "trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"decision":None,
            "specialist_gate":"NONE","specialists":{},"specialists_active":False,"specialists_status":"NOT_USED"}

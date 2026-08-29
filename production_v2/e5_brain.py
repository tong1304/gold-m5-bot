# E5 upgrade: professional location/value reasoning
# NOTE: preserve existing public analyze_e5() contract and E5-only scope.

from typing import Any


# The existing module-level helpers/constants are intentionally preserved.
# This replacement body is applied inside the existing module implementation.


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Professional location/value analysis only.

    E5 answers: is current price location advantageous, for which side, and
    what repricing/acceptance evidence is still required?  It never authorizes
    a trade, entry, target, or stop. E9 remains the sole decision authority.
    """
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

    # Value quality: being cheap/expensive is not itself an edge. Distance
    # from value and current response determine whether the location is
    # accepted, rejected, or merely undergoing repricing.
    abs_vd = abs(vd)
    extension_atr = abs_vd
    extension_state = _extension(extension_atr)

    sl, sh = _range(bars, STRUCTURE_LOOKBACK)
    phs, pls = _pivots(bars)
    tol = 0.15 * atr
    resistance = _above(price, phs + [sh], tol)
    support = _below(price, pls + [sl], tol)
    long_space = _atr_dist(price, resistance, atr)
    short_space = _atr_dist(price, support, atr)
    rd, sd = _atr_dist(price, sh, atr), _atr_dist(price, sl, atr)
    near_r, near_s = rd is not None and rd <= 0.75, sd is not None and sd <= 0.75
    structural = (
        "COMPRESSED_STRUCTURE" if near_r and near_s else
        "AT_RESISTANCE" if near_r else
        "AT_SUPPORT" if near_s else
        "INSIDE_STRUCTURE"
    )

    high_sweep, low_sweep, prior_high, prior_low = _fresh_sweeps(bars)
    liquidity = (
        "BOTH_FRESH_SWEEPS" if high_sweep and low_sweep else
        "FRESH_HIGH_SWEEP" if high_sweep else
        "FRESH_LOW_SWEEP" if low_sweep else
        "NO_FRESH_SWEEP"
    )

    # Current closed-candle response around calculated value. This is not a
    # directional trigger; it only distinguishes acceptance/rejection of the
    # value area and prevents "discount = buy" / "premium = sell" thinking.
    lookback = min(5, len(bars) - 1)
    recent = bars[-lookback:]
    recent_typical = [(b["high"] + b["low"] + b["close"]) / 3.0 for b in recent]
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

    if value_state == "DISCOUNT":
        if value_response == "ACCEPTED_BELOW_VALUE":
            repricing_state = "REPRICING_ACTIVE"
        elif value_response == "REJECTED_BELOW_VALUE":
            repricing_state = "REPRICING_FAILED"
        elif value_response == "ACCEPTING_VALUE":
            repricing_state = "REPRICING_STARTING"
        else:
            repricing_state = "NO_REPRICING"
    elif value_state == "PREMIUM":
        if value_response == "ACCEPTED_ABOVE_VALUE":
            repricing_state = "REPRICING_ACTIVE"
        elif value_response == "REJECTED_ABOVE_VALUE":
            repricing_state = "REPRICING_FAILED"
        elif value_response == "ACCEPTING_VALUE":
            repricing_state = "REPRICING_STARTING"
        else:
            repricing_state = "NO_REPRICING"
    else:
        repricing_state = "REPRICING_ACCEPTED" if value_response == "ACCEPTING_VALUE" else "NO_REPRICING"

    # Direction-neutral location quality. Upstream context may explain the
    # market, but it cannot manufacture location quality.
    long_blocked = long_space is not None and long_space < 0.5
    short_blocked = short_space is not None and short_space < 0.5
    long_side = _side("LONG", vp, vd, extension_state, long_blocked, low_sweep, long_space)
    short_side = _side("SHORT", vp, vd, extension_state, short_blocked, high_sweep, short_space)

    # Professional correction: an extreme discount/premium without rejection
    # is not automatically favorable. Penalize unresolved/accepted continuation
    # on the adverse side; reward actual closed-candle rejection only.
    if value_state == "DISCOUNT":
        if value_response in {"ACCEPTED_BELOW_VALUE", "UNRESOLVED_VALUE_RESPONSE"}:
            long_side["components"]["value"] *= 0.35
            long_side["counter_evidence"].append("DISCOUNT_WITHOUT_REJECTION")
        elif value_response == "REJECTED_BELOW_VALUE":
            long_side["components"]["value"] = min(1.0, long_side["components"]["value"] + 0.20)
            long_side["evidence"].append("DISCOUNT_REJECTION_CONFIRMED")
    elif value_state == "PREMIUM":
        if value_response in {"ACCEPTED_ABOVE_VALUE", "UNRESOLVED_VALUE_RESPONSE"}:
            short_side["components"]["value"] *= 0.35
            short_side["counter_evidence"].append("PREMIUM_WITHOUT_REJECTION")
        elif value_response == "REJECTED_ABOVE_VALUE":
            short_side["components"]["value"] = min(1.0, short_side["components"]["value"] + 0.20)
            short_side["evidence"].append("PREMIUM_REJECTION_CONFIRMED")

    def _recompute(side_data: dict[str, Any]) -> None:
        c = side_data["components"]
        side_data["score"] = round(
            0.30 * c["value"] + 0.15 * c["structure"] + 0.15 * c["liquidity"] +
            0.20 * c["extension"] + 0.20 * c["space"], 4
        )
        s = side_data["score"]
        side_data["quality"] = "HIGH" if s >= .72 else "ACCEPTABLE" if s >= .58 else "CONDITIONAL" if s >= .45 else "UNFAVORABLE"

    _recompute(long_side)
    _recompute(short_side)

    # Location thesis must survive counter-evidence. A side is only preferred
    # when its location is independently favorable; otherwise E5 explicitly
    # waits for repricing/acceptance instead of forcing a directional answer.
    if long_side["score"] >= 0.58 and long_side["score"] > short_side["score"] + 0.05:
        preferred = "LONG"
    elif short_side["score"] >= 0.58 and short_side["score"] > long_side["score"] + 0.05:
        preferred = "SHORT"
    else:
        preferred = "NONE"

    if preferred == "NONE":
        if repricing_state in {"REPRICING_STARTING", "REPRICING_ACTIVE", "NO_REPRICING"}:
            location_state = "WAIT_REPRICING"
        else:
            location_state = "WAIT_CONFIRMATION"
    else:
        location_state = "FAVORABLE_LOCATION"

    quality_score = max(long_side["score"], short_side["score"])
    confidence = round(max(0.0, min(1.0, quality_score)), 4)

    evidence = [
        f"VALUE_{value_state}",
        f"VALUE_RESPONSE_{value_response}",
        f"REPRICING_{repricing_state}",
        f"STRUCTURE_{structural}",
        f"LIQUIDITY_{liquidity}",
        f"EXTENSION_{extension_state}",
    ]
    counter_evidence = []
    if extension_state in {"EXTENDED", "EXCESSIVE"}:
        counter_evidence.append("EXTENSION_RISK")
    if not high_sweep and not low_sweep:
        counter_evidence.append("NO_FRESH_LIQUIDITY_CONFIRMATION")
    if long_space is not None and long_space < 1:
        counter_evidence.append("LONG_SPACE_CONSTRAINED")
    if short_space is not None and short_space < 1:
        counter_evidence.append("SHORT_SPACE_CONSTRAINED")
    if value_state == "DISCOUNT" and value_response != "REJECTED_BELOW_VALUE":
        counter_evidence.append("DISCOUNT_NOT_PROVEN_AS_REVERSAL")
    if value_state == "PREMIUM" and value_response != "REJECTED_ABOVE_VALUE":
        counter_evidence.append("PREMIUM_NOT_PROVEN_AS_REVERSAL")

    repricing = _repricing(
        preferred if preferred != "NONE" else ("LONG" if value_state == "DISCOUNT" else "SHORT" if value_state == "PREMIUM" else "LONG"),
        vp, extension_state,
        long_space if preferred == "LONG" else short_space if preferred == "SHORT" else None,
        long_blocked if preferred == "LONG" else short_blocked if preferred == "SHORT" else False,
        low_sweep if preferred == "LONG" else high_sweep if preferred == "SHORT" else (low_sweep or high_sweep),
    )
    if value_response in {"ACCEPTED_BELOW_VALUE", "ACCEPTED_ABOVE_VALUE"}:
        repricing["required_for_improvement"].append("CLOSED_CANDLE_RECLAIM_OR_VALUE_ACCEPTANCE")

    ctx, upstream_evidence, conflicts = _context(permitted)
    observations = [
        f"closed_candles={len(bars)}",
        f"atr14_current={atr:.6f}",
        f"price={price:.8f}",
        f"value={value:.8f}",
        f"value_method={value_method}",
        f"value_position={vp:.4f}",
        f"value_distance_atr={vd:.6f}",
        f"value_state={value_state}",
        f"value_response={value_response}",
        f"repricing_state={repricing_state}",
        f"structural_location={structural}",
        f"next_resistance={resistance}",
        f"next_support={support}",
        f"available_space_atr_long={long_space}",
        f"available_space_atr_short={short_space}",
        f"extension_atr={extension_atr:.6f}",
        f"extension_state={extension_state}",
        f"liquidity_location={liquidity}",
    ]

    return {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY",
        "location_state": location_state,
        "location_quality": "HIGH" if confidence >= .72 else "ACCEPTABLE" if confidence >= .58 else "CONDITIONAL" if confidence >= .45 else "UNFAVORABLE",
        "direction": "NEUTRAL",
        "value_state": value_state,
        "value_response": value_response,
        "value_quality": "REJECTED" if value_response.startswith("REJECTED") else "ACCEPTED" if value_response.startswith("ACCEPTED") or value_response == "ACCEPTING_VALUE" else "UNRESOLVED",
        "structural_location": structural,
        "liquidity_location": liquidity,
        "extension_state": extension_state,
        "extension_atr": round(extension_atr, 6),
        "available_space": _space_label(long_space if preferred == "LONG" else short_space if preferred == "SHORT" else max(x for x in (long_space, short_space) if x is not None) if any(x is not None for x in (long_space, short_space)) else None),
        "available_space_atr": max(x for x in (long_space, short_space) if x is not None) if any(x is not None for x in (long_space, short_space)) else None,
        "long_location_quality": long_side["quality"],
        "short_location_quality": short_side["quality"],
        "long_location_score": long_side["score"],
        "short_location_score": short_side["score"],
        "preferred_location": preferred,
        "confidence": confidence,
        "evidence": evidence + upstream_evidence,
        "observations": observations,
        "counter_evidence": counter_evidence,
        "conflicts": conflicts,
        "reason_codes": ["VALUE_LOCATION_ANALYSIS", "VALUE_RESPONSE_CLASSIFIED", "REPRICING_STATE_EXPLICIT", "COUNTER_EVIDENCE_APPLIED"],
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            f"VALUE -> {value_state} distance={vd:.3f}ATR",
            f"VALUE_RESPONSE -> {value_response}",
            f"REPRICING -> {repricing_state}",
            f"STRUCTURE -> {structural}",
            f"LIQUIDITY -> {liquidity}",
            f"EXTENSION -> {extension_state}",
            f"ASYMMETRY -> LONG={long_side['score']:.4f} SHORT={short_side['score']:.4f}",
            f"LOCATION_DECISION -> {location_state}",
        ],
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": f"{location_state}: value={value_state}, response={value_response}, repricing={repricing_state}",
            "evidence_hierarchy": "VALUE -> VALUE_RESPONSE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> REPRICING_MAP -> COUNTER_EVIDENCE",
            "upstream_decisions_used": bool(ctx),
            "upstream_gates_used": False,
            "upstream_scores_used": False,
            "upstream_direction_used_for_location_score": False,
            "decision_authority": "E9_ONLY",
        },
        "repricing": repricing,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "gate": None,
        "decision": None,
        "specialist_gate": "NONE",
        "specialists": {},
        "specialists_active": False,
        "specialists_status": "NOT_USED",
    }

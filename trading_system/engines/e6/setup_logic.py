from __future__ import annotations

from statistics import mean


def _ema(values, period):
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = float(values[0])
    for item in values[1:]:
        value = alpha * float(item) + (1.0 - alpha) * value
    return value


def _atr(bars, period=14):
    ranges = []
    previous_close = None
    for bar in bars[-period:]:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        ranges.append(high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    return mean(ranges) if ranges else 0.0


def refine_e6(result, data, sub_engine_id):
    """Trend context alone is not a setup; require measurable pullback/repricing."""
    output, score, reasons = result
    bars = [b for b in (data.get("bars") or []) if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]
    if len(bars) < 30:
        return result

    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    atr = max(_atr(bars), 1e-12)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    short_slope = closes[-1] - closes[-6]
    context_slope = closes[-1] - closes[-21]
    direction = "UP" if ema20 > ema50 and context_slope > 0 else "DOWN" if ema20 < ema50 and context_slope < 0 else "NEUTRAL"
    last, previous = closes[-1], closes[-2]

    recent_high = max(highs[-9:-1])
    recent_low = min(lows[-9:-1])
    pullback_depth = max(0.0, recent_high - recent_low)

    if direction == "UP":
        pullback_active = pullback_depth >= 0.60 * atr and (last <= ema20 + 0.30 * atr or min(closes[-4:]) <= ema20 + 0.15 * atr)
        reclaim = previous <= ema20 + 0.15 * atr and last > ema20 and last > previous
        continuation = last > previous and (last - min(lows[-3:])) >= 0.25 * atr
    elif direction == "DOWN":
        pullback_active = pullback_depth >= 0.60 * atr and (last >= ema20 - 0.30 * atr or max(closes[-4:]) >= ema20 - 0.15 * atr)
        reclaim = previous >= ema20 - 0.15 * atr and last < ema20 and last < previous
        continuation = last < previous and (max(highs[-3:]) - last) >= 0.25 * atr
    else:
        pullback_active = reclaim = continuation = False

    formed = direction in {"UP", "DOWN"} and pullback_active
    mature = formed and (reclaim or continuation)
    invalidated = output.get("state") == "INVALIDATED"
    archetype = "TREND_PULLBACK" if formed else "NO_VALID_SETUP"

    states = {
        "6A": "CONTEXT_ALIGNED" if formed else "CONTEXT_UNCLEAR",
        "6B": archetype,
        "6C": "SETUP_FORMING" if formed else "NO_SETUP",
        "6D": "INVALIDATED" if invalidated else "NOT_INVALIDATED",
        "6E": "QUALITY_PASS" if mature and not invalidated else "QUALITY_WEAK",
        "6F": "MATURE" if mature and not invalidated else "DEVELOPING" if formed else "ABSENT",
    }
    state = states.get(sub_engine_id, output.get("state", "UNRESOLVED"))
    thesis = (
        "Trend context exists, but no objective pullback/repricing has formed a setup."
        if not formed else
        f"{archetype} is {'mature' if mature else 'developing'}."
    )
    if sub_engine_id == "6C":
        thesis = "Setup formation requires measurable repricing; trend alone is insufficient."
    elif sub_engine_id == "6E":
        thesis = "Setup quality requires pullback evidence plus a response; no response is not quality."
    elif sub_engine_id == "6F":
        thesis = "Setup maturity requires pullback formation and continuation/reclaim evidence."

    observations = [
        f"direction={direction}", f"ema20={ema20:.6f}", f"ema50={ema50:.6f}",
        f"context_slope_atr={context_slope / atr:.3f}", f"short_slope_atr={short_slope / atr:.3f}",
        f"pullback_depth_atr={pullback_depth / atr:.3f}", f"pullback_active={pullback_active}",
        f"reclaim={reclaim}", f"continuation={continuation}",
        f"setup_formed={formed}", f"setup_mature={mature}",
    ]
    output = dict(output)
    output.update({
        "state": state,
        "thesis": thesis,
        "direction": direction,
        "setup_archetype": archetype,
        "pullback_active": pullback_active,
        "pullback_depth_atr": round(pullback_depth / atr, 3),
        "reclaim_observed": reclaim,
        "continuation_observed": continuation,
        "setup_formed": formed,
        "setup_mature": mature,
        "observations": observations,
        "evidence": observations,
        "counter_evidence": [] if formed else ["TREND_CONTEXT_WITHOUT_PULLBACK"],
        "missing_evidence": [] if mature else ["pullback_response"] if formed else ["objective_pullback_repricing"],
        "confidence": 0.88 if mature and not invalidated else 0.65 if formed else 0.35,
    })
    return output, round(output["confidence"] * 100.0, 1), list(reasons or [])

from __future__ import annotations

# E6 v31 — Setup Formation / Hypothesis Ranking
# A directional context is not automatically a tradeable continuation setup.
# Counter-trend hypotheses remain alternatives until reversal proof is complete.

from typing import Any, Dict, List


def _s(value: Any) -> str:
    return str(value or "").strip().upper()


def _pick(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _flag(d: Dict[str, Any], *keys: str) -> bool:
    value = _pick(d, *keys, default=False)
    if isinstance(value, str):
        return value.strip().upper() in {"TRUE", "YES", "CONFIRMED", "VALID", "READY", "UP", "DOWN", "BULLISH", "BEARISH"}
    return bool(value)


def analyze_e6(context: Dict[str, Any]) -> Dict[str, Any]:
    """Form and rank setups without promoting unproven ideas to primary setups.

    E6 is setup formation/reasoning only. E9 remains final trade authority.
    """
    e1 = context.get("e1") or {}
    e3 = context.get("e3") or {}
    e4 = context.get("e4") or {}
    e5 = context.get("e5") or {}

    e1_finding = _s(_pick(e1, "finding", "market_state", "trend_state"))
    e3_finding = _s(_pick(e3, "finding", "structure"))
    e4_finding = _s(_pick(e4, "finding", "event"))
    e5_finding = _s(_pick(e5, "finding", "location"))

    e1_obs = e1.get("observations") or {}
    e3_obs = e3.get("observations") or {}
    e4_obs = e4.get("observations") or {}
    e5_obs = e5.get("observations") or {}
    for name, value in (("e1", e1_obs), ("e3", e3_obs), ("e4", e4_obs), ("e5", e5_obs)):
        if not isinstance(value, dict):
            locals()[f"{name}_obs"] = {}

    # --- Context state -------------------------------------------------
    transition = "TRANSITION" in e1_finding or _s(_pick(e1, "transition", default=_pick(e1_obs, "transition"))) in {"WATCH", "ACTIVE", "TRANSITION"}
    trend_down = "DOWN" in e1_finding or "BEARISH" in e1_finding or "DOWN" in e3_finding or "BEARISH" in e3_finding
    trend_up = "UP" in e1_finding or "BULLISH" in e1_finding or "UP" in e3_finding or "BULLISH" in e3_finding
    directional_context = (trend_up and not trend_down) or (trend_down and not trend_up)
    structure_bull = "BULLISH_STRUCTURE" in e3_finding or _s(_pick(e3, "external_state", "structure_direction", default=_pick(e3_obs, "external_state"))) in {"UP", "BULLISH"}
    structure_bear = "BEARISH_STRUCTURE" in e3_finding or _s(_pick(e3, "external_state", "structure_direction", default=_pick(e3_obs, "external_state"))) in {"DOWN", "BEARISH"}
    structure_directional = structure_bull or structure_bear

    # --- Auction state -------------------------------------------------
    auction_state = _s(_pick(e4, "auction_state", default=_pick(e4_obs, "auction_state")))
    auction_pending = auction_state in {"PENDING", "WATCH", "UNRESOLVED", "UNKNOWN", ""}
    terminal_auction = auction_state in {"CONFIRMED", "TERMINAL", "ACCEPTED_REJECTION", "REJECTED"}
    auction_quality = float(_pick(e4, "auction_quality", default=_pick(e4_obs, "auction_quality", default=0)) or 0)
    event = e4_finding or _s(_pick(e4_obs, "event"))

    # --- Structural proof ----------------------------------------------
    bos = _s(_pick(e3, "bos", "break_of_structure", default=_pick(e3_obs, "bos")))
    choch = _s(_pick(e3, "choch", "change_of_character", default=_pick(e3_obs, "choch")))
    structural_reversal = (
        bos in {"UP", "BULLISH", "YES"}
        or choch in {"UP", "BULLISH", "YES"}
        or bos in {"DOWN", "BEARISH"}
        or choch in {"DOWN", "BEARISH"}
        or e3_finding in {"BULLISH_STRUCTURE", "BEARISH_STRUCTURE", "REVERSAL_CONFIRMED"}
    ) and not (bos == "NO_BREAK" and choch == "NO")

    reversal_event = any(x in event for x in ("FAILED_BREAK_RECLAIM", "SWEEP_RECLAIM", "LIQUIDITY_REVERSAL", "REVERSAL"))
    counter_buy = trend_down and reversal_event
    counter_sell = trend_up and reversal_event
    counter_trend_proven = terminal_auction and structural_reversal

    # --- Continuation maturity -----------------------------------------
    # These fields are deliberately evidence-led. Missing evidence is false.
    freshness = _s(_pick(e4, "event_age_bars", default=_pick(e4_obs, "event_age_bars")))
    try:
        event_age_bars = int(float(freshness)) if freshness else 999999
    except (TypeError, ValueError):
        event_age_bars = 999999

    closed_trigger = _flag(e4, "closed_candle_confirmation", "closed_candle_trigger", "trigger_confirmed") or _flag(e3, "closed_candle_confirmation", "closed_candle_trigger", "trigger_confirmed")
    follow_through = _flag(e4, "follow_through", "follow_through_confirmed") or _flag(e3, "follow_through", "follow_through_confirmed")
    acceptance = _flag(e4, "acceptance_confirmed", "auction_acceptance", "acceptance")
    pullback = _flag(context, "pullback_confirmed", "continuation_pullback") or _flag(e5, "pullback_confirmed", "continuation_pullback")
    fresh_impulse = _flag(context, "fresh_impulse", "impulse_confirmed", "expansion_confirmed") or _flag(e1, "fresh_impulse", "impulse_confirmed", "expansion_confirmed")
    space_ok = _flag(context, "space_ok", "effective_space_ok", "space_confirmed") or _flag(e5, "space_ok", "effective_space_ok", "space_confirmed")

    # A generic HIGH/LOW liquidity interaction is not continuation proof.
    meaningful_auction_for_continuation = terminal_auction or (acceptance and not auction_pending)
    continuation_core = directional_context and structure_directional and not transition
    continuation_proof = fresh_impulse and (pullback or acceptance or follow_through) and closed_trigger
    continuation_mature = continuation_core and continuation_proof and meaningful_auction_for_continuation and space_ok and event_age_bars <= 3

    observations: List[str] = [
        f"transition={transition}",
        f"directional_context={directional_context}",
        f"structure_directional={structure_directional}",
        f"auction_state={auction_state or 'UNKNOWN'}",
        f"auction_quality={auction_quality:.2f}",
        f"event_age_bars={event_age_bars}",
        f"fresh_impulse={fresh_impulse}",
        f"pullback={pullback}",
        f"acceptance={acceptance}",
        f"follow_through={follow_through}",
        f"closed_trigger={closed_trigger}",
        f"space_ok={space_ok}",
        f"continuation_mature={continuation_mature}",
        f"terminal_auction={terminal_auction}",
        f"structural_reversal={structural_reversal}",
        f"counter_trend_proven={counter_trend_proven}",
    ]
    reasons: List[str] = ["HYPOTHESIS_RANKING", "EVENT_NOT_EQUAL_CONFIRMATION", "E6_NOT_TRADE_AUTHORITY"]

    # Priority 1: proven counter-trend reversal.
    if counter_buy and not counter_trend_proven:
        selected, alternative, state = None, "BUY LIQUIDITY_REVERSAL", "ALTERNATIVE_COUNTER_TREND_BLOCKED"
        reasons += ["COUNTER_TREND_CANNOT_BE_PRIMARY", "TERMINAL_AUCTION_REQUIRED", "STRUCTURAL_REVERSAL_REQUIRED"]
        text = "BUY LIQUIDITY_REVERSAL remains an alternative hypothesis; reversal proof is incomplete."
    elif counter_sell and not counter_trend_proven:
        selected, alternative, state = None, "SELL LIQUIDITY_REVERSAL", "ALTERNATIVE_COUNTER_TREND_BLOCKED"
        reasons += ["COUNTER_TREND_CANNOT_BE_PRIMARY", "TERMINAL_AUCTION_REQUIRED", "STRUCTURAL_REVERSAL_REQUIRED"]
        text = "SELL LIQUIDITY_REVERSAL remains an alternative hypothesis; reversal proof is incomplete."
    elif counter_trend_proven and counter_buy:
        selected, alternative, state = "BUY LIQUIDITY_REVERSAL", None, "VALIDATING"
        reasons += ["TERMINAL_AUCTION_CONFIRMED", "STRUCTURAL_REVERSAL_CONFIRMED"]
        text = "BUY LIQUIDITY_REVERSAL is eligible for validation; E7/E8 proof gates still apply."
    elif counter_trend_proven and counter_sell:
        selected, alternative, state = "SELL LIQUIDITY_REVERSAL", None, "VALIDATING"
        reasons += ["TERMINAL_AUCTION_CONFIRMED", "STRUCTURAL_REVERSAL_CONFIRMED"]
        text = "SELL LIQUIDITY_REVERSAL is eligible for validation; E7/E8 proof gates still apply."

    # Priority 2: continuation only after maturity is proven.
    elif trend_up and continuation_mature:
        selected, alternative, state = "BUY IMPULSE_CONTINUATION", None, "VALIDATING"
        reasons += ["CONTINUATION_MATURITY_CONFIRMED", "CLOSED_CANDLE_TRIGGER_CONFIRMED", "SPACE_CONFIRMED"]
        text = "BUY IMPULSE_CONTINUATION is mature enough for validation; E7/E8 proof gates still apply."
    elif trend_down and continuation_mature:
        selected, alternative, state = "SELL IMPULSE_CONTINUATION", None, "VALIDATING"
        reasons += ["CONTINUATION_MATURITY_CONFIRMED", "CLOSED_CANDLE_TRIGGER_CONFIRMED", "SPACE_CONFIRMED"]
        text = "SELL IMPULSE_CONTINUATION is mature enough for validation; E7/E8 proof gates still apply."
    elif trend_up and directional_context:
        selected, alternative, state = None, "BUY IMPULSE_CONTINUATION", "WAITING_CONTINUATION_PROOF"
        reasons += ["CONTINUATION_NOT_MATURE", "WAITING_CLOSED_CANDLE_TRIGGER", "WAITING_AUCTION_ACCEPTANCE", "WAITING_FRESH_IMPULSE_OR_PULLBACK", "SPACE_NOT_PROVEN"]
        text = "Bullish continuation is only a hypothesis; continuation maturity proof is incomplete."
    elif trend_down and directional_context:
        selected, alternative, state = None, "SELL IMPULSE_CONTINUATION", "WAITING_CONTINUATION_PROOF"
        reasons += ["CONTINUATION_NOT_MATURE", "WAITING_CLOSED_CANDLE_TRIGGER", "WAITING_AUCTION_ACCEPTANCE", "WAITING_FRESH_IMPULSE_OR_PULLBACK", "SPACE_NOT_PROVEN"]
        text = "Bearish continuation is only a hypothesis; continuation maturity proof is incomplete."
    else:
        selected, alternative, state = None, None, "UNRESOLVED"
        reasons += ["NO_MATURE_SETUP"]
        text = "No sufficiently mature directional setup is established."

    return {
        "role": "SETUP_FORMATION_REASONER",
        "question": "What setup is forming, in what direction, and at what stage?",
        "finding": text,
        "observations": observations,
        "reasons": reasons,
        "selected_hypothesis": selected,
        "alternative_hypothesis": alternative,
        "context_role": "PRIMARY" if selected else ("ALTERNATIVE" if alternative else "UNRESOLVED"),
        "setup_state": state,
        "terminal_auction": terminal_auction,
        "structural_reversal": structural_reversal,
        "counter_trend_proven": counter_trend_proven,
        "continuation_mature": continuation_mature,
        "execution_ready": False,
    }

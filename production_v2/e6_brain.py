from __future__ import annotations

# E6 v30 — Setup Formation / Hypothesis Ranking
# Counter-trend hypotheses remain alternatives until terminal auction + structural reversal are proven.

from typing import Any, Dict, List


def _s(value: Any) -> str:
    return str(value or "").strip().upper()


def _pick(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def analyze_e6(context: Dict[str, Any]) -> Dict[str, Any]:
    """Form/rank setups; E9 remains final trade authority."""
    e1 = context.get("e1") or {}
    e3 = context.get("e3") or {}
    e4 = context.get("e4") or {}

    e1_finding = _s(_pick(e1, "finding", "market_state", "trend_state"))
    e3_finding = _s(_pick(e3, "finding", "structure"))
    e4_finding = _s(_pick(e4, "finding", "event"))
    e4_obs = e4.get("observations") or {}
    if not isinstance(e4_obs, dict):
        e4_obs = {}

    auction_state = _s(_pick(e4, "auction_state", default=_pick(e4_obs, "auction_state")))
    auction_quality = float(_pick(e4, "auction_quality", default=_pick(e4_obs, "auction_quality", default=0)) or 0)
    event = e4_finding or _s(_pick(e4_obs, "event"))

    terminal_auction = auction_state in {"CONFIRMED", "TERMINAL", "ACCEPTED_REJECTION", "REJECTED"}
    structural_reversal = (
        _s(_pick(e3, "bos", "break_of_structure")) in {"UP", "BULLISH", "YES"}
        or _s(_pick(e3, "choch", "change_of_character")) in {"UP", "BULLISH", "YES"}
        or e3_finding in {"BULLISH_STRUCTURE", "REVERSAL_CONFIRMED"}
    )

    context_down = "DOWN" in e1_finding or "BEARISH" in e1_finding or "DOWN" in e3_finding or "BEARISH" in e3_finding
    context_up = "UP" in e1_finding or "BULLISH" in e1_finding or "UP" in e3_finding or "BULLISH" in e3_finding
    reversal_event = any(x in event for x in ("FAILED_BREAK_RECLAIM", "SWEEP_RECLAIM", "LIQUIDITY_REVERSAL", "REVERSAL"))
    counter_buy = context_down and reversal_event
    counter_sell = context_up and reversal_event
    counter_trend_proven = terminal_auction and structural_reversal

    observations: List[str] = [
        f"context_down={context_down}", f"context_up={context_up}",
        f"auction_state={auction_state or 'UNKNOWN'}", f"auction_quality={auction_quality:.2f}",
        f"terminal_auction={terminal_auction}", f"structural_reversal={structural_reversal}",
        f"counter_trend_proven={counter_trend_proven}",
    ]
    reasons: List[str] = ["HYPOTHESIS_RANKING", "EVENT_NOT_EQUAL_CONFIRMATION", "E6_NOT_TRADE_AUTHORITY"]

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
    elif context_down:
        selected, alternative, state = "SELL_CONTEXT_ALIGNED", None, "CONTEXT_ALIGNED"
        reasons += ["PRIMARY_CONTEXT_ALIGNED"]
        text = "Bearish context dominates; no counter-trend setup has sufficient reversal proof."
    elif context_up:
        selected, alternative, state = "BUY_CONTEXT_ALIGNED", None, "CONTEXT_ALIGNED"
        reasons += ["PRIMARY_CONTEXT_ALIGNED"]
        text = "Bullish context dominates; no counter-trend setup has sufficient reversal proof."
    else:
        selected, alternative, state = None, None, "UNRESOLVED"
        reasons += ["NO_DOMINANT_CONTEXT"]
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
        "execution_ready": False,
    }

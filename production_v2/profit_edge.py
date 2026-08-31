from __future__ import annotations

from statistics import mean
from typing import Any

MIN_SAMPLE = 30
TRUSTED_SAMPLE = 50
MIN_EXPECTED_VALUE_R = 0.10
STRESS_PROBABILITY = 0.03
STRESS_COST_MULTIPLIER = 1.50


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _records(source: Any) -> list[dict[str, Any]]:
    if isinstance(source, dict):
        for key in ("records", "outcomes", "trades", "historical_outcomes", "setup_history"):
            if isinstance(source.get(key), list):
                return [x for x in source[key] if isinstance(x, dict)]
    if isinstance(source, list):
        return [x for x in source if isinstance(x, dict)]
    return []


def _resolved(row: dict[str, Any]) -> tuple[bool | None, float | None]:
    win = row.get("win")
    if win is None:
        outcome = _text(row.get("outcome"))
        if outcome in {"WIN", "WON", "PROFIT", "TP", "SUCCESS"}:
            win = True
        elif outcome in {"LOSS", "LOST", "SL", "FAIL"}:
            win = False
    if not isinstance(win, bool):
        return None, None
    r = row.get("r_multiple", row.get("r", row.get("return_r")))
    if r is None:
        r = None
    else:
        r = _num(r, 0.0)
    return win, r


def _matches(row: dict[str, Any], symbol: str, regime: str, direction: str, setup: str, location: str, confirmation: str) -> bool:
    pairs = (
        ("symbol", symbol),
        ("regime", regime),
        ("direction", direction),
        ("setup", setup),
        ("setup_family", setup),
        ("location", location),
        ("location_state", location),
        ("confirmation", confirmation),
        ("confirmation_state", confirmation),
    )
    # Optional dimensions only constrain when the historical row contains them.
    for key, wanted in pairs:
        if key not in row or row.get(key) in (None, "", "UNKNOWN"):
            continue
        if _text(row.get(key)) != _text(wanted):
            return False
    return True


def evaluate_profit_edge(*, symbol: str, regime: str, direction: str, setup: str,
                         location: str = "UNKNOWN", confirmation: str = "UNKNOWN",
                         historical_outcomes: Any = None, realized_rr: float = 0.0,
                         cost_r: float = 0.0) -> dict[str, Any]:
    """Evaluate conditional expectancy from completed outcomes only.

    This module is deliberately non-predictive: it never manufactures outcomes,
    never inspects future candles, and never authorizes execution. Historical
    records must already represent completed trades/outcomes supplied by the
    caller.
    """
    symbol = _text(symbol)
    regime = _text(regime)
    direction = _text(direction)
    setup = _text(setup)
    location = _text(location)
    confirmation = _text(confirmation)

    candidates = [
        row for row in _records(historical_outcomes)
        if _matches(row, symbol, regime, direction, setup, location, confirmation)
    ]
    resolved = []
    for row in candidates:
        win, r = _resolved(row)
        if win is not None:
            resolved.append((win, r, row))

    n = len(resolved)
    wins = sum(1 for win, _, _ in resolved if win)
    losses = n - wins
    p = (wins + 1.0) / (n + 2.0) if n else None

    observed_r = [r for _, r, _ in resolved if r is not None and r != 0.0]
    avg_win_r = mean([r for win, r, _ in resolved if win and r is not None and r > 0]) if any(win and r is not None and r > 0 for win, r, _ in resolved) else max(realized_rr, 0.0)
    avg_loss_r = abs(mean([r for win, r, _ in resolved if not win and r is not None and r < 0])) if any((not win) and r is not None and r < 0 for win, r, _ in resolved) else 1.0
    reward_r = max(avg_win_r, _num(realized_rr, 0.0), 0.0)
    risk_r = max(avg_loss_r, 1e-9)

    expected = None
    stress_expected = None
    break_even = None
    if p is not None:
        net_reward = max(0.0, reward_r - max(cost_r, 0.0))
        net_risk = risk_r + max(cost_r, 0.0)
        expected = p * net_reward - (1.0 - p) * net_risk
        stress_p = max(0.0, p - STRESS_PROBABILITY)
        stress_cost = max(cost_r, 0.0) * STRESS_COST_MULTIPLIER
        stress_expected = stress_p * max(0.0, reward_r - stress_cost) - (1.0 - stress_p) * (risk_r + stress_cost)
        break_even = net_risk / max(net_risk + net_reward, 1e-9)

    sample_quality = min(100.0, 100.0 * n / TRUSTED_SAMPLE) if n else 0.0
    probability_quality = min(100.0, 50.0 + 50.0 * min(1.0, n / TRUSTED_SAMPLE)) if n else 0.0
    blockers: list[str] = []
    if n < MIN_SAMPLE:
        blockers.append("PROFIT_EDGE_NOT_PROVEN")
    if expected is None:
        blockers.append("PROFIT_EXPECTANCY_UNQUANTIFIED")
    elif expected < MIN_EXPECTED_VALUE_R:
        blockers.append("PROFIT_EXPECTANCY_BELOW_MINIMUM")
    if stress_expected is not None and stress_expected <= 0.0:
        blockers.append("PROFIT_EDGE_FAILS_COST_STRESS")

    state = "UNQUANTIFIED" if n == 0 else "UNTRUSTED" if n < MIN_SAMPLE else "NEGATIVE_EDGE" if expected is not None and expected < MIN_EXPECTED_VALUE_R else "POSITIVE_EDGE"
    trusted = n >= MIN_SAMPLE and expected is not None and expected >= MIN_EXPECTED_VALUE_R and (stress_expected or -1.0) > 0.0
    if trusted:
        state = "POSITIVE_EDGE"
    elif n >= MIN_SAMPLE and expected is not None and expected < MIN_EXPECTED_VALUE_R:
        state = "NEGATIVE_EDGE"

    return {
        "state": state,
        "trusted": trusted,
        "sample": n,
        "wins": wins,
        "losses": losses,
        "win_probability": p,
        "probability_quality": round(probability_quality, 2),
        "sample_quality": round(sample_quality, 2),
        "average_win_r": round(avg_win_r, 6),
        "average_loss_r": round(avg_loss_r, 6),
        "expected_value_r": None if expected is None else round(expected, 6),
        "stress_expected_value_r": None if stress_expected is None else round(stress_expected, 6),
        "break_even_probability": None if break_even is None else round(break_even, 6),
        "cost_r": round(max(cost_r, 0.0), 6),
        "conditioning": {"symbol": symbol, "regime": regime, "direction": direction, "setup": setup, "location": location, "confirmation": confirmation},
        "observed_r_samples": len(observed_r),
        "source": "COMPLETED_HISTORICAL_OUTCOMES_ONLY",
        "lookahead": False,
        "blockers": list(dict.fromkeys(blockers)),
        "decision_authority": "E9_ONLY",
    }

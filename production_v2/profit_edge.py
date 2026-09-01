from __future__ import annotations

from statistics import mean
from typing import Any
import math
import os

MIN_SAMPLE = 30
TRUSTED_SAMPLE = 50
MIN_EXPECTED_VALUE_R = 0.10
STRESS_PROBABILITY = 0.03
STRESS_COST_MULTIPLIER = 1.50
EXACT_CONDITIONING = ("symbol", "direction", "setup", "regime", "location", "confirmation")


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _records(source: Any) -> list[dict[str, Any]]:
    if source is None:
        path = os.getenv("E9_LEARNING_PATH", "").strip()
        if path:
            try:
                from .e9_learning import load_records
                source = [r.__dict__ for r in load_records(path)]
            except Exception:
                source = []
    if isinstance(source, dict):
        for key in ("records", "outcomes", "trades", "historical_outcomes", "setup_history"):
            value = source.get(key)
            if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
    if isinstance(source, list): return [x for x in source if isinstance(x, dict)]
    return []


def _resolved(row: dict[str, Any]) -> tuple[bool | None, float | None]:
    win = row.get("win")
    if win is None:
        outcome = _text(row.get("outcome"))
        if outcome in {"WIN", "WON", "PROFIT", "TP", "SUCCESS"}: win = True
        elif outcome in {"LOSS", "LOST", "SL", "FAIL", "TIMEOUT"}: win = False
    if not isinstance(win, bool): return None, None
    raw_r = row.get("r_multiple", row.get("realized_r", row.get("r", row.get("return_r"))))
    return win, None if raw_r is None else _num(raw_r, 0.0)


def _field(row: dict[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, "", "UNKNOWN"): return _text(value)
    return ""


def _field_present(row: dict[str, Any], names: tuple[str, ...]) -> bool:
    return any(row.get(name) not in (None, "", "UNKNOWN") for name in names)


def _match(row: dict[str, Any], dimensions: dict[str, str], keys: tuple[str, ...]) -> bool:
    aliases = {"setup": ("setup", "setup_family", "setup_type"), "location": ("location", "location_state", "value_state"), "confirmation": ("confirmation", "confirmation_state", "proof_state"), "regime": ("regime", "market_state", "trend_state"), "direction": ("direction",), "symbol": ("symbol", "asset")}
    for key in keys:
        names = aliases[key]
        if not _field_present(row, names): return False
        if _field(row, names) != dimensions[key]: return False
    return True


def _conditional_candidates(records: list[dict[str, Any]], dimensions: dict[str, str]) -> tuple[list[dict[str, Any]], tuple[str, ...], str, list[dict[str, Any]]]:
    tiers = (EXACT_CONDITIONING, ("symbol", "direction", "setup", "regime", "location"), ("symbol", "direction", "setup", "regime"), ("symbol", "direction", "setup"))
    attempts: list[tuple[list[dict[str, Any]], tuple[str, ...]]] = []
    trace = []
    for keys in tiers:
        matched = [r for r in records if _match(r, dimensions, keys)]
        resolved = [r for r in matched if _resolved(r)[0] is not None]
        attempts.append((resolved, keys))
        trace.append({"keys": list(keys), "resolved_sample": len(resolved)})
        if len(resolved) >= MIN_SAMPLE:
            return resolved, keys, "EXACT_OR_PROGRESSIVELY_RELAXED", trace
    best, keys = max(attempts, key=lambda item: len(item[0]))
    return best, keys, "INSUFFICIENT_SAMPLE_AT_ALL_TIERS", trace


def _wilson_lower(wins: int, n: int, z: float = 1.96) -> float | None:
    if n <= 0: return None
    p = wins / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt(max(0.0, (p * (1.0 - p) + z * z / (4.0 * n)) / n))
    return max(0.0, (centre - margin) / denom)


def evaluate_profit_edge(*, symbol: str, regime: str, direction: str, setup: str,
                         location: str = "UNKNOWN", confirmation: str = "UNKNOWN",
                         historical_outcomes: Any = None, realized_rr: float = 0.0,
                         cost_r: float = 0.0) -> dict[str, Any]:
    dimensions = {"symbol": _text(symbol), "regime": _text(regime), "direction": _text(direction), "setup": _text(setup), "location": _text(location), "confirmation": _text(confirmation)}
    records = _records(historical_outcomes)
    candidates, conditioning_keys, selection_mode, calibration_trace = _conditional_candidates(records, dimensions)
    resolved = [(w, r, row) for row in candidates for w, r in [_resolved(row)] if w is not None]
    n = len(resolved); wins = sum(1 for win, _, _ in resolved if win); losses = n - wins
    p = (wins + 1.0) / (n + 2.0) if n else None
    win_rs = [r for win, r, _ in resolved if win and r is not None and r > 0]
    loss_rs = [r for win, r, _ in resolved if not win and r is not None and r < 0]
    avg_win_r = mean(win_rs) if win_rs else max(_num(realized_rr), 0.0)
    avg_loss_r = abs(mean(loss_rs)) if loss_rs else 1.0
    reward_r = max(avg_win_r, _num(realized_rr), 0.0); risk_r = max(avg_loss_r, 1e-9); cost_r = max(_num(cost_r), 0.0)
    expected = stress_expected = break_even = stress_p = None
    if p is not None:
        net_reward = max(0.0, reward_r - cost_r); net_risk = risk_r + cost_r
        expected = p * net_reward - (1.0 - p) * net_risk
        stress_p = max(0.0, p - STRESS_PROBABILITY); stress_cost = cost_r * STRESS_COST_MULTIPLIER
        stress_reward = max(0.0, reward_r - stress_cost); stress_risk = risk_r + stress_cost
        stress_expected = stress_p * stress_reward - (1.0 - stress_p) * stress_risk
        break_even = net_risk / max(net_risk + net_reward, 1e-9)
    lower_probability = _wilson_lower(wins, n)
    sample_quality = min(100.0, 100.0 * n / TRUSTED_SAMPLE) if n else 0.0
    probability_quality = min(100.0, 50.0 + 50.0 * min(1.0, n / TRUSTED_SAMPLE)) if n else 0.0
    blockers: list[str] = []
    if n < MIN_SAMPLE: blockers.append("PROFIT_EDGE_NOT_PROVEN")
    if expected is None: blockers.append("PROFIT_EXPECTANCY_UNQUANTIFIED")
    elif expected < MIN_EXPECTED_VALUE_R: blockers.append("PROFIT_EXPECTANCY_BELOW_MINIMUM")
    if stress_expected is not None and stress_expected <= 0.0: blockers.append("PROFIT_EDGE_FAILS_COST_STRESS")
    exact = conditioning_keys == EXACT_CONDITIONING
    if not exact: blockers.append("CONDITIONAL_SAMPLE_RELAXED")
    if selection_mode == "INSUFFICIENT_SAMPLE_AT_ALL_TIERS": blockers.append("HISTORICAL_SAMPLE_INSUFFICIENT")
    if exact and lower_probability is not None and break_even is not None and lower_probability <= break_even: blockers.append("PROBABILITY_EDGE_NOT_STATISTICALLY_ROBUST")
    if n == 0: state = "UNQUANTIFIED"
    elif n < MIN_SAMPLE: state = "UNTRUSTED"
    elif expected is not None and expected < MIN_EXPECTED_VALUE_R: state = "NEGATIVE_EDGE"
    else: state = "POSITIVE_EDGE"
    trusted = bool(exact and n >= MIN_SAMPLE and expected is not None and expected >= MIN_EXPECTED_VALUE_R and stress_expected is not None and stress_expected > 0.0 and (lower_probability is None or break_even is None or lower_probability > break_even))
    if not trusted and state == "POSITIVE_EDGE": state = "UNTRUSTED"; blockers.append("PROFIT_EDGE_NOT_TRUSTED")
    return {"state":state,"trusted":trusted,"sample":n,"wins":wins,"losses":losses,"win_probability":p,"probability_lower_95":lower_probability,"probability_quality":round(probability_quality,2),"sample_quality":round(sample_quality,2),"average_win_r":round(avg_win_r,6),"average_loss_r":round(avg_loss_r,6),"expected_value_r":None if expected is None else round(expected,6),"stress_expected_value_r":None if stress_expected is None else round(stress_expected,6),"break_even_probability":None if break_even is None else round(break_even,6),"stress_probability":None if stress_p is None else round(stress_p,6),"cost_r":round(cost_r,6),"conditioning":dimensions,"conditioning_used":list(conditioning_keys),"conditioning_mode":selection_mode,"calibration_trace":calibration_trace,"observed_r_samples":len([r for _,r,_ in resolved if r is not None]),"source":"COMPLETED_HISTORICAL_OUTCOMES_ONLY","lookahead":False,"blockers":list(dict.fromkeys(blockers)),"decision_authority":"E9_ONLY"}

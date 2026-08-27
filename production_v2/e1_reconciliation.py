from __future__ import annotations

from typing import Any

from .e1_brain_v3 import analyze_e1 as _base_analyze_e1


def _slope_atr(closes: list[float], atr: float, lookback: int) -> float:
    if len(closes) <= lookback or atr <= 0:
        return 0.0
    return (closes[-1] - closes[-1 - lookback]) / atr


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Final E1 reconciliation layer.

    It prevents a coherent, persistent regime from being downgraded merely
    because one quality metric is modest, while preserving genuine long-horizon
    conflict as TRANSITION. It also prevents low-efficiency chop with negligible
    EMA separation from being mislabeled as directional pressure.
    No setup, entry, risk, liquidity or execution logic is introduced here.
    """
    result = _base_analyze_e1(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    pr = result.get("professional_reasoning", {})
    ev = pr.get("independent_evidence", {})
    consensus = pr.get("directional_consensus", {})
    direction = pr.get("direction")
    pressure = result.get("directional_pressure")
    persistence = float(pr.get("persistence_detail", {}).get("aligned_windows", 0)) / 3.0 if isinstance(pr.get("persistence_detail"), dict) else None
    if persistence is None:
        trace = " ".join(result.get("reasoning_trace", []))
        persistence = 1.0 if "PERSISTENCE -> 1.00" in trace else 0.0

    # Professional market-state rule: directional pressure requires actual
    # directional efficiency. Alternating/choppy price action near the EMA
    # equilibrium is NEUTRAL even when one short lookback happens to lean UP/DOWN.
    efficiency20 = float(ev.get("efficiency_20", 1.0) or 0.0)
    ema_gap_abs = abs(float(ev.get("ema_gap_atr", 0.0) or 0.0))
    if direction in ("UP", "DOWN") and pressure in ("BULLISH", "BEARISH") and efficiency20 < 0.20 and ema_gap_abs < 0.15:
        pressure = "NEUTRAL"
        direction = None
        result["directional_pressure"] = "NEUTRAL"
        result["trend_state"] = "NONE"
        result["transition"] = "ABSENT"
        if result.get("market_state") not in {"COMPRESSION", "RANGE"}:
            result["market_state"] = "RANGE"
        reasons = list(result.get("reasons", []))
        if "LOW_EFFICIENCY_BALANCED_PRESSURE" not in reasons:
            reasons.append("LOW_EFFICIENCY_BALANCED_PRESSURE")
        result["reasons"] = reasons
        pr["primary_state"] = result["market_state"]
        pr["market_state"] = result["market_state"]
        pr["direction"] = "NEUTRAL"
        pr["directional_pressure"] = "NEUTRAL"
        pr["trend_confirmed"] = False
        pr["trend_maturity"] = "NONE"
        pr["classification_reason"] = "low_directional_efficiency_near_ema_equilibrium"
        pr["directional_consensus"] = {
            "ema": consensus.get("ema"),
            "short": consensus.get("short"),
            "medium": consensus.get("medium"),
            "long": consensus.get("long"),
            "confirmed": False,
            "count": 0,
            "required_count": 2,
        }
        result["reasoning_trace"].append(
            f"RECONCILIATION -> low efficiency ({efficiency20:.3f}) + near-zero EMA separation ({ema_gap_abs:.3f}); pressure neutralized"
        )

    # A professional state claim may be ESTABLISHED when independent evidence
    # is strongly coherent. Efficiency is quality evidence, not a veto.
    coherent = (
        direction in ("UP", "DOWN")
        and consensus.get("confirmed") is True
        and persistence >= 1.0
        and abs(float(ev.get("ema_gap_atr", 0.0))) >= 0.10
        and ev.get("structure") == ("BULLISH" if direction == "UP" else "BEARISH")
        and float(ev.get("structure_quality", 0.0)) >= 0.55
        and not result.get("conflicts")
    )
    if coherent and result.get("market_state") in {"UNCLEAR", "DEVELOPING", "EXPANSION"}:
        state = "TREND_UP" if direction == "UP" else "TREND_DOWN"
        result["market_state"] = state
        result["trend_state"] = direction
        result["transition"] = "ABSENT"
        result["reasons"] = ["COHERENT_REGIME_CONFIRMED"]
        result["professional_reasoning"]["primary_state"] = state
        result["professional_reasoning"]["market_state"] = state
        result["professional_reasoning"]["trend_maturity"] = "ESTABLISHED"
        result["professional_reasoning"]["trend_confirmed"] = True
        result["professional_reasoning"]["classification_reason"] = "persistent_multi_horizon_direction_with_ema_and_structure_coherence"
        result["reasoning_trace"].append("RECONCILIATION -> coherent persistent regime confirmed")

    # A recent impulse against the established long horizon is a transition,
    # not an automatic trend reversal. Use a 40-candle horizon as independent
    # context, without allowing it to issue a trade decision.
    closes = [float(b["close"]) for b in (bars or []) if isinstance(b, dict) and b.get("close") is not None]
    atr_value = 0.0
    if closes and len(closes) >= 14:
        trs = []
        prev = None
        for b in (bars or [])[-14:]:
            try:
                h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
            except (TypeError, ValueError, KeyError):
                continue
            trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
            prev = c
        atr_value = sum(trs) / len(trs) if trs else 0.0
    long40 = _slope_atr(closes, atr_value, 40)
    if pressure in {"BULLISH", "BEARISH"} and long40:
        long40_dir = "UP" if long40 > 0 else "DOWN"
        pressure_dir = "UP" if pressure == "BULLISH" else "DOWN"
        if long40_dir != pressure_dir and abs(long40) >= 0.50:
            conflicts = list(result.get("conflicts", []))
            if "LONG_HORIZON_CONTEXT_CONFLICT" not in conflicts:
                conflicts.append("LONG_HORIZON_CONTEXT_CONFLICT")
            result["conflicts"] = conflicts
            result["transition"] = "PRESENT"
            result["market_state"] = "TRANSITION"
            result["trend_state"] = "NONE"
            result["reasons"] = conflicts + ["REGIME_CONFLICT_ACTIVE"]
            result["professional_reasoning"]["primary_state"] = "TRANSITION"
            result["professional_reasoning"]["market_state"] = "TRANSITION"
            result["professional_reasoning"]["trend_maturity"] = "DIRECTIONAL_ONLY"
            result["professional_reasoning"]["trend_confirmed"] = False
            result["professional_reasoning"]["classification_reason"] = "short_term_pressure_conflicts_with_long_horizon_context"
            result["professional_reasoning"]["long_horizon_context_slope_atr"] = round(long40, 4)
            result["reasoning_trace"].append(f"LONG_HORIZON -> slope40_atr={long40:.3f} conflicts_with={pressure_dir}")
            result["reasoning_trace"].append("RECONCILIATION -> active horizon conflict preserved as TRANSITION")

    return result

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...core.subengine import SubEngine as _Base


class SubEngine(_Base):
    """E8G risk gate: publish trade economics only when risk is ready.

    E8 owns entry/stop/targets. E9 may challenge the plan, but must not invent
    execution prices merely to turn an otherwise incomplete setup into a trade.
    """

    def __init__(self):
        super().__init__()

    @staticmethod
    def _bars(d: dict[str, Any]):
        return [b for b in (d.get("bars") or []) if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]

    @staticmethod
    def _atr(bs, n=14):
        if not bs:
            return 0.0
        trs = []
        prev = None
        for b in bs[-n:]:
            h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
            trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
            prev = c
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def _direction(bs):
        if len(bs) < 30:
            return "NEUTRAL"
        closes = [float(b["close"]) for b in bs]
        def ema(xs, n):
            a = 2.0 / (n + 1.0)
            x = xs[0]
            for y in xs[1:]:
                x = a * y + (1.0 - a) * x
            return x
        e20, e50 = ema(closes, 20), ema(closes, 50)
        slope = closes[-1] - closes[-6]
        if e20 > e50 and slope > 0 and closes[-1] >= e20:
            return "BUY"
        if e20 < e50 and slope < 0 and closes[-1] <= e20:
            return "SELL"
        return "NEUTRAL"

    @staticmethod
    def _peer_blob(d: dict[str, Any], engine: str) -> str:
        value = d.get(f"{engine}_result") or {}
        return str(value).upper()

    def run(self, d: dict[str, Any]):
        base = super().run(d)
        out = dict(base.output)

        if out.get("risk_gate") != "RISK_READY":
            return base

        bs = self._bars(d)
        direction = self._direction(bs)
        if direction not in {"BUY", "SELL"} or len(bs) < 30:
            return base

        atr = self._atr(bs)
        if atr <= 0:
            return base

        policy = d.get("risk_policy") or {}
        min_rr = float(policy.get("min_rr", 1.5))
        max_stop_atr = float(policy.get("max_stop_atr", 3.0))
        entry = float(bs[-1]["close"])
        recent_high = max(float(b["high"]) for b in bs[-10:])
        recent_low = min(float(b["low"]) for b in bs[-10:])
        recent_range = max(float(b["high"]) for b in bs[-40:]) - min(float(b["low"]) for b in bs[-40:])
        buffer = 0.10 * atr

        if direction == "BUY":
            stop = recent_low - buffer
            risk = entry - stop
            if risk <= 0 or risk > max_stop_atr * atr:
                return base
            tp1 = entry + risk * min_rr
            tp2 = entry + risk * max(min_rr, 2.0)
            target_side = "ABOVE"
        else:
            stop = recent_high + buffer
            risk = stop - entry
            if risk <= 0 or risk > max_stop_atr * atr:
                return base
            tp1 = entry - risk * min_rr
            tp2 = entry - risk * max(min_rr, 2.0)
            target_side = "BELOW"

        if recent_range <= 0:
            return base

        plan = {
            "direction": direction,
            "entry": round(entry, 8),
            "stop_loss": round(stop, 8),
            "take_profit_1": round(tp1, 8),
            "take_profit_2": round(tp2, 8),
            "rr_tp1": round(abs(tp1 - entry) / risk, 4),
            "rr_tp2": round(abs(tp2 - entry) / risk, 4),
            "risk_distance": round(risk, 8),
            "atr": round(atr, 8),
            "target_side": target_side,
            "basis": "E8_INVALIDATION_STOP_TARGET_RR",
            "verified": True,
            "e9_authority": "CHALLENGE_OR_REJECT_ONLY",
        }
        out["trade_plan"] = plan
        out["plan_status"] = "COMPLETE"
        out["risk_basis"] = "E8_VERIFIED_PLAN"
        out["observations"] = list(out.get("observations") or []) + [
            "verified_trade_plan_published",
            f"direction={direction}",
            f"rr_tp2={plan['rr_tp2']:.4f}",
        ]
        trace = dict(base.trace or {})
        trace["trade_plan"] = plan
        trace["plan_status"] = "COMPLETE"
        return replace(base, output=out, trace=trace)

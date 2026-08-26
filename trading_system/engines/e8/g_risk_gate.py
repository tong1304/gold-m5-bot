from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...core.subengine import SubEngine as _Base


class SubEngine(_Base):
    """E8G risk gate: construct and verify trade economics independently.

    E8 owns entry/stop/targets/RR and invalidation geometry. Setup maturity and
    confirmation belong to E6/E7 and are judged by E9. Therefore E8 must not
    refuse to publish a risk plan merely because the setup is still developing.
    E9 remains the sole authority that can turn the evidence into a trade.
    """

    def __init__(self):
        super().__init__()

    @staticmethod
    def _bars(d: dict[str, Any]):
        return [
            b for b in (d.get("bars") or [])
            if isinstance(b, dict)
            and all(k in b for k in ("open", "high", "low", "close"))
        ]

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
    def _ema(xs, n):
        if not xs:
            return 0.0
        a = 2.0 / (n + 1.0)
        x = xs[0]
        for y in xs[1:]:
            x = a * y + (1.0 - a) * x
        return x

    @classmethod
    def _direction(cls, bs):
        if len(bs) < 30:
            return "NEUTRAL"
        closes = [float(b["close"]) for b in bs]
        e20 = cls._ema(closes, 20)
        e50 = cls._ema(closes, 50)
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
        # Keep the base specialist analysis for traceability, but do not let
        # its setup-dependent RISK_NOT_READY state suppress E8's own geometry.
        base = super().run(d)
        out = dict(base.output)
        bs = self._bars(d)
        direction = self._direction(bs)

        if direction not in {"BUY", "SELL"} or len(bs) < 30:
            out["plan_status"] = "PENDING"
            out["risk_gate"] = "RISK_NOT_READY"
            out["risk_basis"] = "INSUFFICIENT_DIRECTION_OR_DATA"
            trace = dict(base.trace or {})
            trace["plan_status"] = "PENDING"
            return replace(base, output=out, trace=trace)

        atr = self._atr(bs)
        if atr <= 0:
            out["plan_status"] = "PENDING"
            out["risk_gate"] = "RISK_NOT_READY"
            out["risk_basis"] = "INVALID_ATR"
            trace = dict(base.trace or {})
            trace["plan_status"] = "PENDING"
            return replace(base, output=out, trace=trace)

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
            tp1 = entry + risk * min_rr
            tp2 = entry + risk * max(min_rr, 2.0)
            target_side = "ABOVE"
        else:
            stop = recent_high + buffer
            risk = stop - entry
            tp1 = entry - risk * min_rr
            tp2 = entry - risk * max(min_rr, 2.0)
            target_side = "BELOW"

        if risk <= 0:
            out["plan_status"] = "PENDING"
            out["risk_gate"] = "RISK_NOT_READY"
            out["risk_basis"] = "NON_POSITIVE_RISK_DISTANCE"
            trace = dict(base.trace or {})
            trace["plan_status"] = "PENDING"
            return replace(base, output=out, trace=trace)

        if risk > max_stop_atr * atr:
            out["plan_status"] = "PENDING"
            out["risk_gate"] = "RISK_NOT_READY"
            out["risk_basis"] = "STOP_TOO_WIDE"
            trace = dict(base.trace or {})
            trace["plan_status"] = "PENDING"
            return replace(base, output=out, trace=trace)

        if recent_range <= 0:
            out["plan_status"] = "PENDING"
            out["risk_gate"] = "RISK_NOT_READY"
            out["risk_basis"] = "ZERO_MARKET_RANGE"
            trace = dict(base.trace or {})
            trace["plan_status"] = "PENDING"
            return replace(base, output=out, trace=trace)

        rr_tp1 = abs(tp1 - entry) / risk
        rr_tp2 = abs(tp2 - entry) / risk
        if rr_tp2 < min_rr:
            out["plan_status"] = "PENDING"
            out["risk_gate"] = "RISK_NOT_READY"
            out["risk_basis"] = "RR_BELOW_MINIMUM"
            trace = dict(base.trace or {})
            trace["plan_status"] = "PENDING"
            return replace(base, output=out, trace=trace)

        plan = {
            "direction": direction,
            "entry": round(entry, 8),
            "stop_loss": round(stop, 8),
            "take_profit_1": round(tp1, 8),
            "take_profit_2": round(tp2, 8),
            "rr_tp1": round(rr_tp1, 4),
            "rr_tp2": round(rr_tp2, 4),
            "risk_distance": round(risk, 8),
            "atr": round(atr, 8),
            "target_side": target_side,
            "basis": "E8_INVALIDATION_STOP_TARGET_RR",
            "verified": True,
            "setup_authority": "E6_E7",
            "e9_authority": "CHALLENGE_OR_REJECT_ONLY",
        }
        out["trade_plan"] = plan
        out["plan_status"] = "COMPLETE"
        out["risk_gate"] = "RISK_READY"
        out["risk_basis"] = "E8_VERIFIED_GEOMETRY"
        out["observations"] = list(out.get("observations") or []) + [
            "verified_trade_plan_published",
            "risk_geometry_independent_of_setup_maturity",
            f"direction={direction}",
            f"rr_tp2={rr_tp2:.4f}",
        ]
        trace = dict(base.trace or {})
        trace["trade_plan"] = plan
        trace["plan_status"] = "COMPLETE"
        trace["risk_gate"] = "RISK_READY"
        return replace(base, output=out, trace=trace)

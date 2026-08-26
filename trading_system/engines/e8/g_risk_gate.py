from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...core.subengine import SubEngine as _Base


class SubEngine(_Base):
    """E8G risk engine: publish verified execution geometry without deciding direction.

    E8 owns entry/stop/targets/RR and invalidation geometry. Directional thesis,
    setup maturity and confirmation belong to E1-E7/E9. When direction is not
    resolved by specialist evidence, E8 publishes *both* valid directional
    execution candidates so E9 can select the candidate matching its final
    thesis without sending a decision backwards into E8.
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
        trs, prev = [], None
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
    def _local_direction(cls, bs):
        if len(bs) < 30:
            return "NEUTRAL"
        closes = [float(b["close"]) for b in bs]
        e20, e50 = cls._ema(closes, 20), cls._ema(closes, 50)
        slope = closes[-1] - closes[-6]
        if e20 > e50 and slope > 0 and closes[-1] >= e20:
            return "BUY"
        if e20 < e50 and slope < 0 and closes[-1] <= e20:
            return "SELL"
        return "NEUTRAL"

    @staticmethod
    def _walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield str(k).upper()
                yield from SubEngine._walk(x)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                yield from SubEngine._walk(x)
        else:
            yield str(v).upper()

    @classmethod
    def _peer_direction(cls, d: dict[str, Any]) -> tuple[str, float, float]:
        """Infer direction from E1-E7 evidence only; never consume decisions/gates."""
        weights = {"E1": 1.5, "E2": 1.0, "E3": 1.5, "E4": 1.0, "E5": 1.0, "E6": 1.5, "E7": 1.5}
        buy = sell = 0.0
        for engine_id, weight in weights.items():
            package = d.get(f"{engine_id}_result") or {}
            if not isinstance(package, dict):
                continue
            evidence = package.get("evidence") or package.get("specialists") or {}
            if not isinstance(evidence, dict):
                continue
            buy_hit = sell_hit = False
            for item in evidence.values():
                if not isinstance(item, dict):
                    continue
                output = item.get("output") or {}
                blob = " ".join(cls._walk(output))
                explicit = str(output.get("direction") or output.get("bias") or "").upper()
                if explicit in {"BUY", "BULLISH", "UP", "LONG", "TREND_UP"}:
                    buy_hit = True
                elif explicit in {"SELL", "BEARISH", "DOWN", "SHORT", "TREND_DOWN"}:
                    sell_hit = True
                else:
                    if any(token in blob for token in ("TREND_UP", "BULLISH", "HIGHER_HIGH", "BULLISH_BOS", "DIRECTION=UP", "DISCOUNT")):
                        buy_hit = True
                    if any(token in blob for token in ("TREND_DOWN", "BEARISH", "LOWER_LOW", "BEARISH_BOS", "DIRECTION=DOWN", "PREMIUM")):
                        sell_hit = True
            if buy_hit and not sell_hit:
                buy += weight
            elif sell_hit and not buy_hit:
                sell += weight
        if buy > sell and buy - sell >= 1.0:
            return "BUY", round(buy, 2), round(sell, 2)
        if sell > buy and sell - buy >= 1.0:
            return "SELL", round(buy, 2), round(sell, 2)
        return "NEUTRAL", round(buy, 2), round(sell, 2)

    @classmethod
    def _direction(cls, bs, d):
        peer_direction, buy, sell = cls._peer_direction(d)
        if peer_direction in {"BUY", "SELL"}:
            return peer_direction, "PEER_EVIDENCE", buy, sell
        return cls._local_direction(bs), "LOCAL_PRICE_STRUCTURE", buy, sell

    @staticmethod
    def _build_plan(direction: str, entry: float, atr: float, recent_high: float, recent_low: float, min_rr: float) -> dict[str, Any]:
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
            raise ValueError("NON_POSITIVE_RISK_DISTANCE")
        rr_tp1, rr_tp2 = abs(tp1 - entry) / risk, abs(tp2 - entry) / risk
        if rr_tp2 < min_rr:
            raise ValueError("RR_BELOW_MINIMUM")
        return {
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
            "e9_authority": "SELECT_MATCHING_THESIS",
        }

    def run(self, d: dict[str, Any]):
        base = super().run(d)
        out = dict(base.output)
        bs = self._bars(d)
        direction, direction_source, peer_buy, peer_sell = self._direction(bs, d)
        out.update({"direction": direction, "direction_source": direction_source,
                    "peer_direction_score": {"BUY": peer_buy, "SELL": peer_sell}})

        if len(bs) < 30:
            out.update({"plan_status": "PENDING", "risk_gate": "RISK_NOT_READY", "risk_basis": "INSUFFICIENT_DATA"})
            trace = dict(base.trace or {})
            trace.update({"plan_status": "PENDING", "direction_source": direction_source})
            return replace(base, output=out, trace=trace)

        atr = self._atr(bs)
        if atr <= 0:
            out.update({"plan_status": "PENDING", "risk_gate": "RISK_NOT_READY", "risk_basis": "INVALID_ATR"})
            return replace(base, output=out, trace=dict(base.trace or {}))

        policy = d.get("risk_policy") or {}
        min_rr, max_stop_atr = float(policy.get("min_rr", 1.5)), float(policy.get("max_stop_atr", 3.0))
        entry = float(bs[-1]["close"])
        recent_high = max(float(b["high"]) for b in bs[-10:])
        recent_low = min(float(b["low"]) for b in bs[-10:])
        recent_range = max(float(b["high"]) for b in bs[-40:]) - min(float(b["low"]) for b in bs[-40:])
        if recent_range <= 0:
            out.update({"plan_status": "PENDING", "risk_gate": "RISK_NOT_READY", "risk_basis": "ZERO_MARKET_RANGE"})
            return replace(base, output=out, trace=dict(base.trace or {}))

        candidates, errors = {}, {}
        directions = ("BUY", "SELL") if direction == "NEUTRAL" else (direction,)
        for candidate_direction in directions:
            try:
                plan = self._build_plan(candidate_direction, entry, atr, recent_high, recent_low, min_rr)
                if float(plan["risk_distance"]) > max_stop_atr * atr:
                    errors[candidate_direction] = "STOP_TOO_WIDE"
                    continue
                candidates[candidate_direction] = plan
            except ValueError as exc:
                errors[candidate_direction] = str(exc)

        if direction == "NEUTRAL":
            if not candidates:
                out.update({"plan_status": "PENDING", "risk_gate": "RISK_NOT_READY", "risk_basis": "NO_VALID_DIRECTIONAL_CANDIDATE"})
                trace = dict(base.trace or {})
                trace.update({"plan_status": "PENDING", "candidate_errors": errors})
                return replace(base, output=out, trace=trace)
            out.update({"trade_plan_candidates": candidates, "candidate_errors": errors,
                        "plan_status": "CANDIDATES_READY", "risk_gate": "RISK_CANDIDATES_READY",
                        "risk_basis": "E8_DIRECTION_NEUTRAL_CANDIDATE_GEOMETRY"})
            out["observations"] = list(out.get("observations") or []) + [
                "direction_unresolved_execution_candidates_published",
                "e8_does_not_choose_trade_direction",
            ]
            trace = dict(base.trace or {})
            trace.update({"plan_status": "CANDIDATES_READY", "trade_plan_candidates": candidates,
                          "candidate_errors": errors, "risk_gate": "RISK_CANDIDATES_READY"})
            return replace(base, output=out, trace=trace)

        if direction not in candidates:
            out.update({"plan_status": "PENDING", "risk_gate": "RISK_NOT_READY",
                        "risk_basis": errors.get(direction, "INVALID_RISK_GEOMETRY")})
            return replace(base, output=out, trace=dict(base.trace or {}))

        plan = candidates[direction]
        out.update({"trade_plan": plan, "plan_status": "COMPLETE", "risk_gate": "RISK_READY",
                    "risk_basis": "E8_VERIFIED_GEOMETRY"})
        out["observations"] = list(out.get("observations") or []) + [
            "verified_trade_plan_published", "risk_geometry_independent_of_setup_maturity",
            f"direction={direction}", f"direction_source={direction_source}",
            f"peer_buy={peer_buy:.2f}", f"peer_sell={peer_sell:.2f}",
            f"rr_tp2={plan['rr_tp2']:.4f}",
        ]
        trace = dict(base.trace or {})
        trace.update({"trade_plan": plan, "plan_status": "COMPLETE", "risk_gate": "RISK_READY",
                      "direction_source": direction_source,
                      "peer_direction_score": {"BUY": peer_buy, "SELL": peer_sell}})
        return replace(base, output=out, trace=trace)

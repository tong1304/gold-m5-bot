from __future__ import annotations

from statistics import mean
from typing import Any

from ...core.subengine import SubEngine as _Base


class ProfessionalE2Brain(_Base):
    """E2 professional opportunity/regime brain.

    E2 forms its own thesis from closed-candle auction evidence. E1 is only a
    later cross-check; it cannot manufacture an E2 conclusion. E2 never
    executes a trade and never delegates its reasoning to paused sub-engines.
    """

    QUESTION = "What opportunity is the market offering right now?"
    MIN_BARS = 50

    @staticmethod
    def _norm_direction(v: Any) -> str:
        v = str(v or "NEUTRAL").upper().strip()
        if v in {"UP", "BULLISH", "BUY", "LONG"}:
            return "UP"
        if v in {"DOWN", "BEARISH", "SELL", "SHORT"}:
            return "DOWN"
        return "NEUTRAL"

    @staticmethod
    def _candle(o: float, h: float, l: float, c: float) -> tuple[float, float]:
        span = max(h - l, 1e-12)
        return abs(c - o) / span, (c - l) / span

    def _e1(self, d: dict[str, Any]) -> dict[str, Any]:
        x = d.get("E1_result") or {}
        return x if isinstance(x, dict) else {}

    def _analyse(self, d: dict[str, Any]):
        bs = self._bars(d)
        if len(bs) < self.MIN_BARS:
            out = {
                "state": "UNAVAILABLE", "question": self.QUESTION,
                "thesis": "Insufficient closed-candle evidence.", "regime": "UNRESOLVED",
                "direction": "NEUTRAL", "phase": "UNRESOLVED", "opportunity": "NONE",
                "opportunity_state": "UNPROVEN", "quality": "UNPROVEN",
                "alignment_with_e1": "INCONCLUSIVE", "independence": "E2_FIRST_E1_CROSS_CHECK",
                "auction_state": "UNKNOWN", "location_context": "UNKNOWN",
                "regime_confidence": 0.0, "decision_factors": [], "observations": [],
                "evidence": [], "counter_evidence": ["insufficient closed-candle history"],
                "missing_evidence": [f"{self.MIN_BARS} valid closed candles"],
                "confidence": 0.0, "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
            }
            return out, 0.0, ["INSUFFICIENT_MARKET_DATA"]

        h = [float(x["high"]) for x in bs]
        l = [float(x["low"]) for x in bs]
        c = [float(x["close"]) for x in bs]
        o = [float(x["open"]) for x in bs]
        last = c[-1]
        atr = max(self._atr(bs), 1e-12)
        ema20, ema50 = self._ema(c, 20), self._ema(c, 50)
        gap = (ema20 - ema50) / atr
        slope5 = (c[-1] - c[-6]) / atr
        slope20 = (c[-1] - c[-21]) / atr

        rr = [max(h[i] - l[i], 0.0) for i in range(len(bs))]
        avg20 = max(mean(rr[-20:]), 1e-12)
        vol_ratio = mean(rr[-6:]) / avg20
        body, close_pos = self._candle(o[-1], h[-1], l[-1], last)
        efficiency = abs(c[-1] - c[-13]) / max(sum(rr[-12:]), 1e-12)

        hi20, lo20 = max(h[-21:-1]), min(l[-21:-1])
        hi40, lo40 = max(h[-41:-1]), min(l[-41:-1])
        width = max(hi40 - lo40, 1e-12)
        pos = max(0.0, min(1.0, (last - lo40) / width))

        broke_up = last > hi20
        broke_down = last < lo20
        sweep_up = h[-1] > hi20 and last <= hi20
        sweep_down = l[-1] < lo20 and last >= lo20
        accept_up = broke_up and close_pos >= 0.65 and body >= 0.50
        accept_down = broke_down and close_pos <= 0.35 and body >= 0.50
        fail_up = sweep_up and close_pos <= 0.45
        fail_down = sweep_down and close_pos >= 0.55

        ph, pl = self._pivots(bs)
        hh = len(ph) >= 2 and ph[-1] > ph[-2]
        lh = len(ph) >= 2 and ph[-1] < ph[-2]
        hl = len(pl) >= 2 and pl[-1] > pl[-2]
        ll = len(pl) >= 2 and pl[-1] < pl[-2]
        bull_struct, bear_struct = hh and hl, lh and ll

        up = sum((gap > 0.35, slope5 > 0.20, slope20 > 0.50, bull_struct, efficiency >= 0.30))
        down = sum((gap < -0.35, slope5 < -0.20, slope20 < -0.50, bear_struct, efficiency >= 0.30))

        expansion = vol_ratio > 1.30 or (rr[-1] > 1.35 * avg20 and body >= 0.60)
        compression = vol_ratio < 0.70

        # Professional hierarchy: accepted repricing > established trend >
        # failed auction at an extreme > genuine balance > transition.
        if accept_up and not accept_down:
            regime, direction = "BREAKOUT", "UP"
        elif accept_down and not accept_up:
            regime, direction = "BREAKOUT", "DOWN"
        elif up >= 4 and up > down:
            regime, direction = "TREND", "UP"
        elif down >= 4 and down > up:
            regime, direction = "TREND", "DOWN"
        elif fail_down and pos <= 0.25:
            regime, direction = "MEAN_REVERSION", "UP"
        elif fail_up and pos >= 0.75:
            regime, direction = "MEAN_REVERSION", "DOWN"
        else:
            # Crucial correction: low volatility alone is NOT range. A range
            # requires bounded price, low efficiency, balanced trend scores,
            # and no directional pressure strong enough to imply transition.
            true_balance = (
                abs(gap) < 0.45 and abs(slope20) < 0.55 and efficiency < 0.25
                and 0.15 < pos < 0.85 and max(up, down) <= 3
                and not (accept_up or accept_down) and width / atr < 8.0
            )
            if true_balance:
                regime, direction = "RANGE", "NEUTRAL"
            else:
                regime, direction = "TRANSITION", "NEUTRAL"

        if regime == "BREAKOUT":
            auction = "ACCEPTING_UP" if direction == "UP" else "ACCEPTING_DOWN"
            phase = "EXPANSION" if expansion else "BREAKOUT_DEVELOPING"
            opportunity = "BREAKOUT_CONTINUATION"
        elif regime == "TREND":
            auction = "REPRICING_UP" if direction == "UP" else "REPRICING_DOWN"
            phase = "EXPANSION" if expansion and efficiency >= 0.30 else "COMPRESSION" if compression else "BALANCED"
            opportunity = "TREND_CONTINUATION"
        elif regime == "MEAN_REVERSION":
            auction = "FAILED_AUCTION_DOWN" if direction == "UP" else "FAILED_AUCTION_UP"
            phase, opportunity = "REJECTION", "MEAN_REVERSION"
        elif regime == "RANGE":
            auction, phase = "BALANCED", "COMPRESSION" if compression else "BALANCED"
            opportunity = "RANGE_ROTATION" if pos <= 0.20 or pos >= 0.80 else "WAIT_FOR_RANGE_EDGE"
        else:
            auction, phase, opportunity = "REPRICING_UNRESOLVED", "TRANSITION", "WAIT_FOR_REPRICING"

        location = "EDGE_LOW" if pos <= 0.20 else "EDGE_HIGH" if pos >= 0.80 else "MID_RANGE"
        e1 = self._e1(d)
        e1_dir = self._norm_direction(e1.get("directional_pressure") or e1.get("direction"))
        alignment = "ALIGNED" if direction != "NEUTRAL" and direction == e1_dir else "CONFLICT" if direction != "NEUTRAL" and e1_dir != "NEUTRAL" else "INCONCLUSIVE"

        counter, missing = [], []
        if regime == "TREND" and not (bull_struct if direction == "UP" else bear_struct):
            counter.append("trend lacks complete swing confirmation")
        if regime == "BREAKOUT" and not expansion:
            missing.append("volatility expansion after repricing")
        if regime == "MEAN_REVERSION" and not (fail_up or fail_down):
            missing.append("failed-auction rejection")
        if regime == "RANGE" and opportunity == "WAIT_FOR_RANGE_EDGE":
            missing.append("range edge/rejection before rotation")
        if regime == "TRANSITION":
            missing.append("stable directional or balanced regime commitment")
        if alignment == "CONFLICT":
            counter.append(f"E1 cross-check conflicts with independent E2 direction={direction}")

        regime_score = {"BREAKOUT": 0.90, "TREND": 0.82, "MEAN_REVERSION": 0.72, "RANGE": 0.62, "TRANSITION": 0.30}[regime]
        evidence_score = (
            0.25 * min(efficiency / 0.50, 1.0)
            + 0.20 * (1.0 if (bull_struct or bear_struct) else 0.0)
            + 0.20 * (1.0 if expansion else 0.0)
            + 0.20 * regime_score
            + 0.15 * (1.0 if (accept_up or accept_down or fail_up or fail_down) else 0.0)
        )
        confidence = max(0.20, min(0.95, 0.20 + evidence_score - (0.08 if alignment == "CONFLICT" else 0.0)))

        if regime == "TRANSITION" or opportunity == "WAIT_FOR_RANGE_EDGE":
            state, quality = "WAIT", "LOW"
        elif counter or missing:
            state, quality = "DEVELOPING", "MEDIUM" if confidence >= 0.55 else "LOW"
        elif regime in {"BREAKOUT", "TREND", "MEAN_REVERSION"} and confidence >= 0.68:
            state, quality = "ACTIONABLE_CONTEXT", "HIGH"
        else:
            state, quality = "DEVELOPING", "MEDIUM"

        evidence = [
            f"ema_gap_atr={gap:.3f}", f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}",
            f"trend_up_score={up}/5", f"trend_down_score={down}/5", f"efficiency={efficiency:.3f}",
            f"volatility_ratio={vol_ratio:.3f}", f"position40={pos:.3f}", f"range_width_atr={width/atr:.3f}",
            f"structure={'BULLISH' if bull_struct else 'BEARISH' if bear_struct else 'MIXED'}",
            f"breakout_up={broke_up}", f"breakout_down={broke_down}", f"accepted_up={accept_up}",
            f"accepted_down={accept_down}", f"failed_auction_up={fail_up}", f"failed_auction_down={fail_down}",
            f"e1_direction={e1_dir}", f"e1_e2_alignment={alignment}",
        ]
        observations = [
            f"independent_regime={regime}", f"independent_direction={direction}", f"phase={phase}",
            f"auction_state={auction}", f"location_context={location}", f"opportunity={opportunity}",
            f"opportunity_state={state}", f"quality={quality}",
        ]
        factors = [f"regime={regime}", f"auction={auction}", f"location={location}", f"confidence={confidence:.3f}"]
        thesis = f"E2 independently concludes {regime}/{direction}: {opportunity}; state={state}."
        out = {
            "state": "ANALYZED", "question": self.QUESTION, "thesis": thesis,
            "regime": regime, "direction": direction, "phase": phase, "opportunity": opportunity,
            "opportunity_state": state, "quality": quality, "alignment_with_e1": alignment,
            "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": auction,
            "location_context": location, "regime_confidence": confidence,
            "decision_factors": factors, "observations": observations, "evidence": evidence,
            "counter_evidence": counter, "missing_evidence": missing, "confidence": confidence,
            "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        }
        return out, confidence, []

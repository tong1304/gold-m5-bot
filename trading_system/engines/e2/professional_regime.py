from __future__ import annotations

from statistics import mean
from typing import Any

from ...core.subengine import SubEngine as _Base


class ProfessionalE2Brain(_Base):
    """E2: independent professional opportunity/regime analyst.

    E2 answers what the market is offering, not whether to execute.
    It reasons from auction state, regime, phase, location, acceptance/rejection,
    and counter-evidence. E9 remains the sole trade-decision authority.
    """

    QUESTION = "What opportunity is the market offering right now?"
    MIN_BARS = 50

    @staticmethod
    def _direction(value: Any) -> str:
        value = str(value or "NEUTRAL").upper().strip()
        if value in {"UP", "BULLISH", "BUY", "LONG"}:
            return "UP"
        if value in {"DOWN", "BEARISH", "SELL", "SHORT"}:
            return "DOWN"
        return "NEUTRAL"

    def _e1_context(self, d: dict[str, Any]) -> dict[str, Any]:
        raw = d.get("E1_result") or {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _candle_quality(o: float, h: float, l: float, c: float) -> tuple[float, float, float]:
        span = max(h - l, 1e-12)
        return abs(c - o) / span, (c - l) / span, span

    def _analyse(self, d: dict[str, Any]):
        bs = self._bars(d)
        if len(bs) < self.MIN_BARS:
            output = {
                "state": "UNAVAILABLE", "question": self.QUESTION,
                "thesis": "Insufficient closed-candle history; opportunity is unproven.",
                "regime": "UNRESOLVED", "direction": "NEUTRAL", "phase": "UNRESOLVED",
                "opportunity": "NONE", "opportunity_state": "UNPROVEN", "quality": "UNPROVEN",
                "alignment_with_e1": "INCONCLUSIVE", "independence": "E2_FIRST_E1_CROSS_CHECK",
                "auction_state": "UNKNOWN", "location_context": "UNKNOWN",
                "regime_confidence": 0.0, "decision_factors": [],
                "observations": [], "evidence": [],
                "counter_evidence": ["insufficient closed-candle history"],
                "missing_evidence": [f"{self.MIN_BARS} valid closed candles"],
                "confidence": 0.0, "decision": None, "entry": None, "trigger": None,
                "risk": None, "gate": None,
            }
            return output, 0.0, ["INSUFFICIENT_MARKET_DATA"]

        h = [float(b["high"]) for b in bs]
        l = [float(b["low"]) for b in bs]
        c = [float(b["close"]) for b in bs]
        o = [float(b["open"]) for b in bs]
        last = c[-1]
        atr = max(self._atr(bs), 1e-12)
        ema20, ema50 = self._ema(c, 20), self._ema(c, 50)
        ema_gap = (ema20 - ema50) / atr
        slope5, slope20 = (c[-1] - c[-6]) / atr, (c[-1] - c[-21]) / atr

        ranges = [max(h[i] - l[i], 0.0) for i in range(len(bs))]
        avg20, avg6 = max(mean(ranges[-20:]), 1e-12), mean(ranges[-6:])
        range_ratio = avg6 / avg20
        body_ratio, close_pos, current_range = self._candle_quality(o[-1], h[-1], l[-1], last)

        hi20, lo20 = max(h[-21:-1]), min(l[-21:-1])
        hi40, lo40 = max(h[-41:-1]), min(l[-41:-1])
        width40 = max(hi40 - lo40, 1e-12)
        position40 = max(0.0, min(1.0, (last - lo40) / width40))
        broke_up, broke_down = last > hi20, last < lo20
        swept_up = h[-1] > hi20 and last <= hi20
        swept_down = l[-1] < lo20 and last >= lo20
        accepted_up = broke_up and close_pos >= 0.65
        accepted_down = broke_down and close_pos <= 0.35

        travelled = max(sum(ranges[-12:]), 1e-12)
        efficiency = abs(c[-1] - c[-13]) / travelled
        ph, pl = self._pivots(bs)
        hh = len(ph) > 1 and ph[-1] > ph[-2]
        lh = len(ph) > 1 and ph[-1] < ph[-2]
        hl = len(pl) > 1 and pl[-1] > pl[-2]
        ll = len(pl) > 1 and pl[-1] < pl[-2]
        bull_structure, bear_structure = hh and hl, lh and ll

        compressed = range_ratio < 0.70
        expansion = range_ratio > 1.30 or (current_range > 1.35 * avg20 and body_ratio >= 0.60)
        directional_up = body_ratio >= 0.55 and close_pos >= 0.70
        directional_down = body_ratio >= 0.55 and close_pos <= 0.30

        trend_up_score = sum((ema_gap > 0.35, slope5 > 0.20, slope20 > 0.50,
                              bull_structure, efficiency >= 0.30))
        trend_down_score = sum((ema_gap < -0.35, slope5 < -0.20, slope20 < -0.50,
                                bear_structure, efficiency >= 0.30))
        breakout_up = broke_up and last > ema20 and (expansion or directional_up)
        breakout_down = broke_down and last < ema20 and (expansion or directional_down)
        failed_auction_up = swept_up and close_pos <= 0.45
        failed_auction_down = swept_down and close_pos >= 0.55
        reversion_up = position40 <= 0.20 and failed_auction_down
        reversion_down = position40 >= 0.80 and failed_auction_up

        # A range is a balance condition, not merely low volatility. Require
        # bounded price location, weak directional efficiency and no accepted
        # breakout. This prevents the common novice error of calling the middle
        # of a drifting market a range-rotation opportunity.
        balanced_market = (
            abs(ema_gap) < 0.55
            and abs(slope20) < 0.65
            and efficiency < 0.30
            and position40 > 0.15
            and position40 < 0.85
            and not (accepted_up or accepted_down)
            and width40 / atr < 8.0
        )
        range_edge = position40 <= 0.20 or position40 >= 0.80

        # Hierarchy mirrors discretionary trading: accepted repricing first,
        # established trend second, failed auction third, true balance fourth.
        if breakout_up and breakout_down:
            regime, direction = "TRANSITION", "NEUTRAL"
        elif breakout_up:
            regime, direction = "BREAKOUT", "UP"
        elif breakout_down:
            regime, direction = "BREAKOUT", "DOWN"
        elif trend_up_score >= 4 and trend_up_score > trend_down_score:
            regime, direction = "TREND", "UP"
        elif trend_down_score >= 4 and trend_down_score > trend_up_score:
            regime, direction = "TREND", "DOWN"
        elif reversion_up and not reversion_down:
            regime, direction = "MEAN_REVERSION", "UP"
        elif reversion_down and not reversion_up:
            regime, direction = "MEAN_REVERSION", "DOWN"
        elif balanced_market:
            regime, direction = "RANGE", "NEUTRAL"
        elif compressed and abs(slope20) < 0.80 and abs(ema_gap) < 0.75 and efficiency < 0.40:
            regime, direction = "RANGE", "NEUTRAL"
        elif abs(ema_gap) < 0.35 or abs(trend_up_score - trend_down_score) <= 1:
            regime, direction = "TRANSITION", "NEUTRAL"
        else:
            regime, direction = "RANGE", "NEUTRAL"

        if accepted_up and not accepted_down:
            auction_state = "ACCEPTING_UP"
        elif accepted_down and not accepted_up:
            auction_state = "ACCEPTING_DOWN"
        elif failed_auction_up and not failed_auction_down:
            auction_state = "FAILED_AUCTION_UP"
        elif failed_auction_down and not failed_auction_up:
            auction_state = "FAILED_AUCTION_DOWN"
        elif regime == "TRANSITION":
            auction_state = "REPRICING"
        elif regime == "RANGE":
            auction_state = "BALANCED"
        elif direction == "UP":
            auction_state = "REPRICING_UP"
        elif direction == "DOWN":
            auction_state = "REPRICING_DOWN"
        else:
            auction_state = "UNKNOWN"

        if position40 <= 0.20:
            location_context = "EDGE_LOW"
        elif position40 >= 0.80:
            location_context = "EDGE_HIGH"
        else:
            location_context = "MID_RANGE"

        if regime == "BREAKOUT":
            phase = "EXPANSION" if expansion or accepted_up or accepted_down else "BREAKOUT_DEVELOPING"
            opportunity = "BREAKOUT_CONTINUATION"
        elif regime == "TREND":
            phase = "EXPANSION" if expansion and efficiency >= 0.30 else "COMPRESSION" if compressed else "BALANCED"
            opportunity = "TREND_CONTINUATION"
        elif regime == "MEAN_REVERSION":
            phase, opportunity = "REJECTION", "MEAN_REVERSION"
        elif regime == "RANGE":
            phase = "COMPRESSION" if compressed else "BALANCED"
            opportunity = "RANGE_ROTATION" if range_edge or failed_auction_up or failed_auction_down else "WAIT_FOR_RANGE_EDGE"
        else:
            phase, opportunity = "TRANSITION", "WAIT_FOR_REPRICING"

        e1 = self._e1_context(d)
        e1_direction = self._direction(e1.get("directional_pressure") or e1.get("direction"))
        e1_state = str(e1.get("market_state") or e1.get("state") or "UNRESOLVED").upper()
        e1_structure = str(e1.get("structure") or "UNRESOLVED").upper()
        alignment = (
            "ALIGNED" if direction != "NEUTRAL" and direction == e1_direction
            else "CONFLICT" if direction != "NEUTRAL" and e1_direction != "NEUTRAL"
            else "INCONCLUSIVE"
        )

        counter: list[str] = []
        missing: list[str] = []
        if regime == "TREND" and efficiency < 0.30:
            counter.append("directional movement lacks efficient follow-through")
        if regime == "TREND" and not (bull_structure if direction == "UP" else bear_structure):
            counter.append("swing structure does not fully confirm trend")
        if regime == "BREAKOUT" and not expansion:
            counter.append("breakout lacks clear volatility expansion")
        if regime == "BREAKOUT" and not (accepted_up or accepted_down):
            missing.append("acceptance beyond the broken level")
        if regime == "MEAN_REVERSION" and not (failed_auction_up or failed_auction_down):
            counter.append("rejection is not objectively proven")
        if regime == "RANGE" and not range_edge and not (failed_auction_up or failed_auction_down):
            missing.append("range edge or rejection")
            counter.append("price is in the middle of balance; rotation has poor location")
        if regime == "TRANSITION":
            missing.append("stable regime commitment")
        if alignment == "CONFLICT":
            counter.append(f"E1 conflicts with independent E2 direction={direction}")

        directional_strength = max(trend_up_score, trend_down_score) / 5.0
        structure_strength = 1.0 if bull_structure or bear_structure else 0.0
        regime_clarity = {"BREAKOUT": 1.0, "TREND": 0.85, "MEAN_REVERSION": 0.70,
                          "RANGE": 0.60, "TRANSITION": 0.25}[regime]
        confirmation_quality = (
            0.20 * min(efficiency / 0.50, 1.0)
            + 0.20 * structure_strength
            + 0.25 * regime_clarity
            + 0.20 * (1.0 if expansion else 0.0)
            + 0.15 * (1.0 if (accepted_up or accepted_down or failed_auction_up or failed_auction_down) else 0.0)
            + (0.10 if alignment == "ALIGNED" else -0.10 if alignment == "CONFLICT" else 0.0)
        )
        confidence = max(0.20, min(0.95, 0.20 + confirmation_quality))

        if regime == "TRANSITION":
            opportunity_state, quality = "WAIT", "LOW"
        elif opportunity == "WAIT_FOR_RANGE_EDGE":
            opportunity_state, quality = "WAIT", "LOW"
        elif counter:
            opportunity_state = "DEVELOPING"
            quality = "MEDIUM" if confidence >= 0.55 else "LOW"
        elif regime in {"BREAKOUT", "TREND"} and confidence >= 0.68:
            opportunity_state, quality = "ACTIONABLE_CONTEXT", "HIGH"
        else:
            opportunity_state = "DEVELOPING"
            quality = "MEDIUM" if confidence >= 0.55 else "LOW"

        decision_factors = [
            f"regime={regime}",
            f"auction={auction_state}",
            f"location={location_context}",
            f"efficiency={efficiency:.3f}",
            f"volatility_ratio={range_ratio:.3f}",
        ]
        if opportunity == "WAIT_FOR_RANGE_EDGE":
            decision_factors.insert(0, "Range edge required before rotation becomes attractive")
        elif regime == "TRANSITION":
            decision_factors.insert(0, "Stable repricing commitment required before directional opportunity")
        elif regime == "TREND":
            decision_factors.insert(0, f"Trend continuation has directional evidence={direction}")
        elif regime == "BREAKOUT":
            decision_factors.insert(0, "Accepted repricing is the primary opportunity")
        elif regime == "MEAN_REVERSION":
            decision_factors.insert(0, "Failed auction plus extreme location creates the reversal opportunity")

        evidence = [
            f"ema_gap_atr={ema_gap:.3f}", f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}",
            f"trend_up_score={trend_up_score}/5", f"trend_down_score={trend_down_score}/5",
            f"range_ratio={range_ratio:.3f}", f"efficiency={efficiency:.3f}",
            f"structure={'BULLISH' if bull_structure else 'BEARISH' if bear_structure else 'MIXED'}",
            f"position40={position40:.3f}", f"range_width_atr={width40 / atr:.3f}",
            f"expansion={expansion}", f"balanced_market={balanced_market}",
            f"breakout_up={breakout_up}", f"breakout_down={breakout_down}",
            f"accepted_up={accepted_up}", f"accepted_down={accepted_down}",
            f"failed_auction_up={failed_auction_up}", f"failed_auction_down={failed_auction_down}",
            f"e1_direction={e1_direction}", f"e1_state={e1_state}", f"e1_structure={e1_structure}",
            f"e1_e2_alignment={alignment}", f"directional_strength={directional_strength:.3f}",
        ]
        observations = [
            f"independent_regime={regime}", f"independent_direction={direction}", f"phase={phase}",
            f"auction_state={auction_state}", f"location_context={location_context}",
            f"opportunity={opportunity}", f"opportunity_state={opportunity_state}", f"quality={quality}",
            f"e1_cross_check={alignment}",
        ]
        thesis = (f"E2 independently classifies {regime} with direction={direction}. "
                  f"Auction={auction_state}, location={location_context}, phase={phase}. "
                  f"The market offers {opportunity}; opportunity_state={opportunity_state}.")
        output = {
            "state": f"{regime}_{direction}" if direction != "NEUTRAL" else regime,
            "question": self.QUESTION, "thesis": thesis, "regime": regime, "direction": direction,
            "phase": phase, "opportunity": opportunity, "opportunity_state": opportunity_state,
            "quality": quality, "alignment_with_e1": alignment,
            "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": auction_state,
            "location_context": location_context, "regime_confidence": confidence,
            "decision_factors": decision_factors, "observations": observations,
            "evidence": evidence, "counter_evidence": counter, "missing_evidence": missing,
            "confidence": confidence, "decision": None, "entry": None, "trigger": None,
            "risk": None, "gate": None,
        }
        return output, confidence, tuple()

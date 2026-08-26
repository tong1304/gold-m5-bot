from __future__ import annotations

from statistics import mean
from typing import Any

from ...core.subengine import SubEngine as _Base


class ProfessionalE2Brain(_Base):
    """E2 professional opportunity/regime analyst.

    E2 answers: what opportunity is the market currently offering?
    It does not issue an entry, execution, risk, or final trade decision.
    """

    def _e1_context(self, d: dict[str, Any]) -> dict[str, Any]:
        raw = d.get("E1_result") or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    @staticmethod
    def _num(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _analyse(self, d: dict[str, Any]):
        bs = self._bars(d)
        if len(bs) < 50:
            return ({
                "state": "UNAVAILABLE",
                "thesis": "E2 cannot classify opportunity without sufficient closed-candle history.",
                "regime": "UNRESOLVED",
                "direction": "NEUTRAL",
                "phase": "UNRESOLVED",
                "opportunity": "NONE",
                "quality": "UNPROVEN",
                "observations": [],
                "evidence": [],
                "counter_evidence": ["insufficient closed-candle history"],
                "missing_evidence": ["at least 50 valid candles"],
                "confidence": 0.0,
            }, 0.0, ["INSUFFICIENT_MARKET_DATA"])

        h = [float(b["high"]) for b in bs]
        l = [float(b["low"]) for b in bs]
        c = [float(b["close"]) for b in bs]
        o = [float(b["open"]) for b in bs]
        last = c[-1]
        atr = max(self._atr(bs), 1e-12)
        ema20 = self._ema(c, 20)
        ema50 = self._ema(c, 50)
        slope5 = c[-1] - c[-6]
        slope20 = c[-1] - c[-21]
        slope5_atr = slope5 / atr
        slope20_atr = slope20 / atr
        ema_gap_atr = (ema20 - ema50) / atr

        ranges = [h[i] - l[i] for i in range(len(bs))]
        avg20 = max(mean(ranges[-20:]), 1e-12)
        avg6 = mean(ranges[-6:])
        range_ratio = avg6 / avg20
        current_range = max(h[-1] - l[-1], 1e-12)
        body_ratio = abs(c[-1] - o[-1]) / current_range

        hi20 = max(h[-21:-1])
        lo20 = min(l[-21:-1])
        hi40 = max(h[-41:-1])
        lo40 = min(l[-41:-1])
        broke_up = last > hi20
        broke_down = last < lo20
        false_up = h[-1] > hi20 and last <= hi20
        false_down = l[-1] < lo20 and last >= lo20

        pos40 = (last - lo40) / max(hi40 - lo40, 1e-12)
        pos40 = max(0.0, min(1.0, pos40))

        # Recent directional efficiency: net displacement divided by travelled range.
        travelled = max(sum(ranges[-12:]), 1e-12)
        efficiency = abs(c[-1] - c[-13]) / travelled

        # Swing structure is deliberately independent from EMA direction.
        ph, pl = self._pivots(bs)
        hh = len(ph) > 1 and ph[-1] > ph[-2]
        lh = len(ph) > 1 and ph[-1] < ph[-2]
        hl = len(pl) > 1 and pl[-1] > pl[-2]
        ll = len(pl) > 1 and pl[-1] < pl[-2]
        bullish_structure = hh and hl
        bearish_structure = lh and ll

        # Regime evidence. No single indicator is allowed to manufacture a regime.
        trend_up = ema_gap_atr > 0.35 and slope5_atr > 0.20 and slope20_atr > 0.50 and bullish_structure
        trend_down = ema_gap_atr < -0.35 and slope5_atr < -0.20 and slope20_atr < -0.50 and bearish_structure
        compressed = range_ratio < 0.70
        expansion = range_ratio > 1.30 or (current_range > 1.35 * avg20 and body_ratio >= 0.60)
        breakout_up = broke_up and expansion and last > ema20
        breakout_down = broke_down and expansion and last < ema20
        failed_up = false_up or (broke_up and last < hi20)
        failed_down = false_down or (broke_down and last > lo20)
        extreme_low = pos40 < 0.20
        extreme_high = pos40 > 0.80

        # Transition is a state of conflicting/decaying evidence, not a trade setup.
        transition = (
            not (trend_up or trend_down)
            and (compressed or failed_up or failed_down or abs(ema_gap_atr) < 0.35)
        )

        if breakout_up:
            regime, direction = "BREAKOUT", "UP"
        elif breakout_down:
            regime, direction = "BREAKOUT", "DOWN"
        elif trend_up:
            regime, direction = "TREND", "UP"
        elif trend_down:
            regime, direction = "TREND", "DOWN"
        elif compressed and abs(slope20_atr) < 0.80:
            regime, direction = "RANGE", "NEUTRAL"
        elif (extreme_low or extreme_high) and (failed_up or failed_down):
            regime = "MEAN_REVERSION"
            direction = "UP" if extreme_low and failed_down else "DOWN" if extreme_high and failed_up else "NEUTRAL"
        elif transition:
            regime, direction = "TRANSITION", "NEUTRAL"
        else:
            regime = "RANGE" if abs(slope20_atr) < 0.80 else "TRANSITION"
            direction = "NEUTRAL"

        if regime == "TREND":
            if expansion and efficiency >= 0.30:
                phase = "EXPANSION"
            elif compressed:
                phase = "COMPRESSION"
            else:
                phase = "BALANCED"
            opportunity = "TREND_CONTINUATION"
        elif regime == "BREAKOUT":
            phase = "EXPANSION" if expansion else "BREAKOUT_DEVELOPING"
            opportunity = "BREAKOUT_CONTINUATION"
        elif regime == "RANGE":
            phase = "BALANCED" if not compressed else "COMPRESSION"
            opportunity = "RANGE_ROTATION"
        elif regime == "MEAN_REVERSION":
            phase = "REJECTION" if (failed_up or failed_down) else "EXTREME"
            opportunity = "MEAN_REVERSION"
        else:
            phase = "TRANSITION"
            opportunity = "WAIT_FOR_REPRICING"

        # E1 is context, never a command. Compare it and explicitly report disagreement.
        e1_direction = str(self._e1_context(d).get("directional_pressure") or self._e1_context(d).get("direction") or "NEUTRAL").upper()
        if e1_direction in {"BULLISH", "UP", "BUY", "LONG"}:
            e1_direction = "UP"
        elif e1_direction in {"BEARISH", "DOWN", "SELL", "SHORT"}:
            e1_direction = "DOWN"
        else:
            e1_direction = "NEUTRAL"
        alignment = "ALIGNED" if direction == e1_direction and direction != "NEUTRAL" else "CONFLICT" if direction != "NEUTRAL" and e1_direction != "NEUTRAL" and direction != e1_direction else "INCONCLUSIVE"

        counter = []
        if regime == "TREND" and efficiency < 0.25:
            counter.append("directional movement lacks efficiency")
        if regime == "TREND" and not (bullish_structure if direction == "UP" else bearish_structure):
            counter.append("structure does not fully confirm trend")
        if regime == "BREAKOUT" and not expansion:
            counter.append("breakout lacks volatility expansion")
        if regime == "RANGE" and not compressed:
            counter.append("range compression is not strong")
        if alignment == "CONFLICT":
            counter.append(f"E1 context conflicts with independent E2 direction={direction}")

        missing = []
        if regime in {"TREND", "BREAKOUT"} and efficiency < 0.30:
            missing.append("clean directional follow-through")
        if regime == "BREAKOUT" and not expansion:
            missing.append("confirmed expansion")
        if regime == "TRANSITION":
            missing.append("stable regime commitment")

        evidence = [
            f"ema_gap_atr={ema_gap_atr:.3f}",
            f"slope5_atr={slope5_atr:.3f}",
            f"slope20_atr={slope20_atr:.3f}",
            f"range_ratio={range_ratio:.3f}",
            f"efficiency={efficiency:.3f}",
            f"structure={'BULLISH' if bullish_structure else 'BEARISH' if bearish_structure else 'MIXED'}",
            f"position40={pos40:.3f}",
            f"breakout_up={breakout_up}",
            f"breakout_down={breakout_down}",
            f"failed_up={failed_up}",
            f"failed_down={failed_down}",
            f"e1_direction={e1_direction}",
            f"e1_e2_alignment={alignment}",
        ]

        # Confidence describes evidence quality, not probability of profit.
        evidence_count = 0
        if regime in {"TREND", "BREAKOUT"}: evidence_count += 2
        if efficiency >= 0.30: evidence_count += 1
        if expansion and regime in {"TREND", "BREAKOUT"}: evidence_count += 1
        if alignment == "ALIGNED": evidence_count += 1
        if alignment == "CONFLICT": evidence_count -= 2
        if counter: evidence_count -= min(2, len(counter))
        confidence = max(0.20, min(0.95, 0.50 + 0.08 * evidence_count))
        quality = "HIGH" if confidence >= 0.78 and not counter else "MEDIUM" if confidence >= 0.60 else "LOW"

        state = f"{regime}_{direction}" if direction != "NEUTRAL" else regime
        thesis = (
            f"Market offers {opportunity} in {regime} regime; direction={direction}; "
            f"phase={phase}; evidence_quality={quality}."
        )
        observations = [
            f"independent_regime={regime}",
            f"independent_direction={direction}
",
            f"phase={phase}",
            f"opportunity={opportunity}",
            f"alignment_with_e1={alignment}",
        ]
        output = {
            "state": state,
            "thesis": thesis,
            "regime": regime,
            "direction": direction,
            "phase": phase,
            "opportunity": opportunity,
            "quality": quality,
            "alignment_with_e1": alignment,
            "observations": observations,
            "evidence": evidence,
            "counter_evidence": counter,
            "missing_evidence": missing,
            "confidence": confidence,
            "decision": None,
            "entry": None,
            "trigger": None,
            "risk": None,
            "gate": None,
        }
        return output, confidence, ()

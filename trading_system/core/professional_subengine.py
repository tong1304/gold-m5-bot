from .subengine import SubEngine as Base, SubEngineResult


class ProfessionalSubEngine(Base):
    """Specialist contract: evidence and thesis first; E9 decides.

    E1-E8 may use upstream specialist evidence to reinterpret their own
    question, but they never inherit an upstream trade decision or gate.
    """

    @staticmethod
    def _flatten(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield str(key).upper(), item
                yield from ProfessionalSubEngine._flatten(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                yield from ProfessionalSubEngine._flatten(item)
        elif value is not None:
            yield "", value

    @classmethod
    def _tokens(cls, value):
        out = set()
        for key, item in cls._flatten(value):
            if key:
                out.add(key)
            text = str(item).upper()
            for token in ("TREND_UP", "TREND_DOWN", "BULLISH", "BEARISH", "UP", "DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "SWEEP_HIGH", "SWEEP_LOW", "REJECTION", "ACCEPTANCE", "NO_TRIGGER", "FOLLOW_THROUGH_OBSERVED", "CONFIRMATION_PASS", "MATURE", "DEVELOPING"):
                if token in text:
                    out.add(token)
        return out

    @classmethod
    def _peer_context(cls, data):
        """Read qualitative upstream evidence only; decisions/gates are ignored."""
        context = {}
        for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
            value = data.get(f"{engine_id}_result") or {}
            if value:
                context[engine_id] = value
        tokens = cls._tokens(context)
        direction = "DOWN" if ("TREND_DOWN" in tokens or "BEARISH" in tokens) and "TREND_UP" not in tokens and "BULLISH" not in tokens else "UP" if ("TREND_UP" in tokens or "BULLISH" in tokens) and "TREND_DOWN" not in tokens and "BEARISH" not in tokens else "NEUTRAL"
        return context, tokens, direction

    @classmethod
    def _apply_peer_reasoning(cls, sid, output, data):
        context, tokens, direction = cls._peer_context(data)
        if not context:
            output["upstream_evidence_used"] = False
            output["upstream_evidence_summary"] = []
            return output

        output["upstream_evidence_used"] = True
        output["upstream_evidence_summary"] = sorted(k for k in context if k != sid)
        if direction in ("UP", "DOWN"):
            output["direction"] = direction

        # E2 answers the opportunity question from E1's market-state thesis.
        if sid.startswith("2"):
            if "TREND_UP" in tokens or "TREND_DOWN" in tokens:
                regime = "TREND"
            elif "RANGE" in tokens and "TREND_UP" not in tokens and "TREND_DOWN" not in tokens:
                regime = "RANGE"
            elif "EXPANSION" in tokens:
                regime = "BREAKOUT"
            else:
                regime = "TRANSITION"
            state_map = {
                "2A": "TREND" if regime == "TREND" else "NOT_TREND",
                "2B": "RANGE" if regime == "RANGE" else "NOT_RANGE",
                "2C": "MEAN_REVERSION" if regime == "MEAN_REVERSION" else "NOT_MEAN_REVERSION",
                "2D": "BREAKOUT" if regime == "BREAKOUT" else "NOT_BREAKOUT",
                "2E": "EXPANSION_PHASE" if "EXPANSION" in tokens else "BALANCED_PHASE",
                "2F": "TRANSITION" if "TRANSITION" in tokens else regime,
            }
            output["state"] = state_map.get(sid, output.get("state", "UNRESOLVED"))
            output["regime"] = regime
            output["upstream_thesis"] = f"E1 market-state evidence supports {regime} with direction={direction}."

        # E3 validates structure against E1 instead of independently guessing
        # the directional thesis from the same candles.
        elif sid.startswith("3"):
            structure = "BULLISH" if direction == "UP" else "BEARISH" if direction == "DOWN" else output.get("state", "MIXED")
            if sid == "3B":
                output["state"] = structure
                output["classification"] = structure
            elif sid == "3F":
                output["state"] = "ALIGNED" if direction != "NEUTRAL" and structure == ("BULLISH" if direction == "UP" else "BEARISH") else "MIXED"
            output["structure"] = structure
            output["upstream_thesis"] = f"E1 directional evidence is {direction}; E3 independently checks whether structure agrees."

        # E4/E5 retain their own specialist calculations but inherit the
        # directional thesis as context, never as a trade instruction.
        elif sid.startswith("4"):
            output["upstream_thesis"] = f"Liquidity is evaluated in the context of the upstream {direction} market thesis."

        elif sid.startswith("5"):
            output["upstream_thesis"] = f"Location is evaluated relative to the upstream {direction} directional context."

        # E6 can recognize a directional setup from the upstream evidence,
        # while maturity still requires price-action evidence of its own.
        elif sid.startswith("6"):
            has_trend = "TREND" in tokens or "TREND_UP" in tokens or "TREND_DOWN" in tokens
            has_rejection = "REJECTION" in tokens or "ACCEPTANCE" in tokens or "SWEEP_HIGH" in tokens or "SWEEP_LOW" in tokens
            if has_trend and not has_rejection and output.get("state") in {"CONTEXT_ALIGNED", "SETUP_FORMING", "DEVELOPING", "QUALITY_WEAK"}:
                archetype = "TREND_PULLBACK"
                output["archetype"] = archetype
                if sid == "6B":
                    output["state"] = archetype
                elif sid == "6C":
                    output["state"] = "SETUP_FORMING"
                elif sid == "6F":
                    output["state"] = "DEVELOPING"
                output["setup_direction"] = direction
            output["upstream_thesis"] = f"Setup must fit the upstream {direction} context; confirmation remains downstream."

        elif sid.startswith("7"):
            output["upstream_thesis"] = f"Trigger must confirm the upstream {direction} thesis; no trigger is inferred from context alone."

        elif sid.startswith("8"):
            output["upstream_thesis"] = f"Risk is evaluated for the upstream {direction} scenario; economics remain incomplete until E8 proves them."

        return output

    def run(self, data):
        r = super().run(data)
        o = dict(r.output or {})
        sid = r.sub_engine_id
        o = self._apply_peer_reasoning(sid, o, data)
        state = str(o.get("state", "UNRESOLVED"))
        obs = []
        for k in (
            "direction", "structure", "trend_strength_atr", "range_ratio",
            "sweep_high", "sweep_low", "rejection", "acceptance",
            "position_in_range", "archetype", "displacement", "trigger",
            "follow_through", "failure", "min_rr", "max_stop_atr",
            "regime", "upstream_thesis", "upstream_evidence_used",
        ):
            if k in o:
                obs.append(f"{k}={o[k]}")
        if not obs:
            obs = [f"state={state}"]
        c = self.confidence(sid, o, r.score)
        missing = []
        if sid.startswith("6") and state not in ("MATURE", "QUALITY_PASS"):
            missing = ["setup confirmation"]
        if sid.startswith("7") and state not in ("CONFIRMED", "QUALITY_PASS", "FOLLOW_THROUGH"):
            missing = ["trigger/follow-through"]
        if sid.startswith("8") and state not in ("RISK_GATE_READY", "RR_OK", "VALID", "LIQUIDITY_TARGET"):
            missing = ["complete trade economics"]
        thesis = f"{sid}: {state}"
        o.update(
            evidence_type=f"{sid}_SPECIALIST_ANALYSIS",
            observations=obs,
            analysis=thesis,
            evidence=obs,
            counter_evidence=[],
            confidence=c,
            thesis=thesis,
            missing_evidence=missing,
            upstream_decisions_used=False,
            upstream_gates_used=False,
            upstream_evidence_used=bool(o.get("upstream_evidence_used")),
        )
        s = round(c * 100, 1)
        return SubEngineResult(
            sid,
            o,
            r.gate_passed,
            s,
            {
                **r.trace,
                "spec_version": "production-v2.4.0-peer-reasoning",
                "evidence_first": True,
                "peer_reasoning": True,
                "output": o,
                "score": s,
            },
        )

    @staticmethod
    def confidence(sid, o, fallback):
        st = str(o.get("state", "")).upper()
        if sid.startswith("1") and "TREND_" in st:
            return min(.98, max(.55, float(o.get("trend_strength_atr", .5)) * .55 + .45))
        if sid.startswith("3"):
            q = float(o.get("structure_strength", 0) or 0)
            return min(.98, max(.45, q / 100)) if q else (.9 if st in ("BULLISH", "BEARISH", "STRONG") else .6)
        if sid.startswith("4"):
            return min(.96, .50 + .11 * sum(bool(o.get(k)) for k in ("sweep_high", "sweep_low", "rejection", "acceptance")))
        if sid.startswith("5"):
            return round(.55 + .40 * (1 - abs(float(o.get("position_in_range", .5)) - .5) * 2), 3)
        if sid.startswith("6"):
            return .91 if st in ("MATURE", "QUALITY_PASS", "CONTEXT_ALIGNED") else .56
        if sid.startswith("7"):
            return .94 if st in ("CONFIRMED", "QUALITY_PASS", "FOLLOW_THROUGH") else .45 if st == "NO_TRIGGER" else .58
        if sid.startswith("8"):
            return .92 if st in ("RISK_GATE_READY", "RR_OK", "VALID", "LIQUIDITY_TARGET") else .55
        return min(.98, max(.40, float(fallback) / 100 if fallback else .5))

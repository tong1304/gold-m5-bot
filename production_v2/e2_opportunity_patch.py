from __future__ import annotations

from typing import Any

from . import e2_brain as _e2_brain


_SETUP_FLAGS = (
    "accepted_up=True",
    "accepted_down=True",
    "displacement_up=True",
    "displacement_down=True",
    "pullback_up=True",
    "pullback_down=True",
)


def _has_real_setup(observations: list[Any]) -> bool:
    text = " ".join(str(x) for x in observations)
    return any(flag in text for flag in _SETUP_FLAGS)


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep E2 directional context separate from an actual opportunity.

    A trend is not itself a tradable opportunity.  E2 may name a trend
    continuation only when the base brain has observed a concrete setup path:
    controlled pullback, range acceptance, or displacement.  Entry/trigger/risk
    authority remains E9-only.
    """
    out = _e2_brain._ORIGINAL_ANALYZE_E2(snapshot) if hasattr(_e2_brain, "_ORIGINAL_ANALYZE_E2") else _e2_brain.analyze_e2(snapshot)
    opportunity = str(out.get("opportunity") or "")
    if opportunity not in {"TREND_PULLBACK_CONTINUATION", "TREND_CONTINUATION"}:
        return out
    if _has_real_setup(list(out.get("observations") or [])):
        return out

    out = dict(out)
    out["opportunity"] = "WAIT_FOR_REPRICING"
    out["phase"] = "TRANSITION"
    out["opportunity_state"] = "WAIT"
    out["opportunity_maturity"] = "WAITING"
    out["quality"] = "UNPROVEN"
    out["opportunity_quality"] = "LOW"
    out["opportunity_score"] = 0.0
    out["opportunity_decision"] = "WAIT"
    out["edge_assessment"] = "NO_EDGE"
    out["timing_state"] = "WAIT"
    out["missing_evidence"] = ["clear directional commitment / repricing"]
    out["counter_evidence"] = list(out.get("counter_evidence") or [])
    out["counter_evidence"].append("trend context exists, but no concrete opportunity setup is present")
    out["counter_evidence_severity"] = "MATERIAL"
    out["why_not_trade"] = [
        "directional trend alone is context, not an opportunity",
        "missing: clear directional commitment / repricing",
    ]
    out["professional_reasoning"] = dict(out.get("professional_reasoning") or {})
    out["professional_reasoning"].update({
        "conclusion": "Trend context detected, but no concrete opportunity setup is present; wait for repricing.",
        "timing": "WAIT",
        "opportunity_quality": "LOW",
        "opportunity_decision": "WAIT",
        "edge_assessment": "NO_EDGE",
        "required_evidence": ["clear directional commitment / repricing"],
        "entry_authorized": False,
    })
    codes = [c for c in list(out.get("reason_codes") or []) if c != "OPPORTUNITY_THESIS_ESTABLISHED"]
    if "MISSING_OPPORTUNITY_CONFIRMATION" not in codes:
        codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    out["reason_codes"] = codes
    return out


# Keep the original core intact; install this guard before production_v2.engines
# imports analyze_e2.  E2 remains a single professional core, not a new sub-engine.
_ORIGINAL_ANALYZE_E2 = _e2_brain.analyze_e2
_e2_brain._ORIGINAL_ANALYZE_E2 = _ORIGINAL_ANALYZE_E2
_e2_brain.analyze_e2 = analyze_e2

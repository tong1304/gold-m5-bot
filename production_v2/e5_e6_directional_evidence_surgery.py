from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E5_E6_DIRECTIONAL_EVIDENCE_SURGERY_V2"
MIN_DIRECTIONAL_SPACE_ATR = 0.75
OPPOSING_ADVANTAGE_RATIO = 1.20


def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _float(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def _directional_space(e5: dict[str, Any], direction: str) -> tuple[float | None, float | None]:
    long_space = _float(e5.get("available_space_atr_long"))
    short_space = _float(e5.get("available_space_atr_short"))
    return (long_space, short_space) if direction == "BUY" else (short_space, long_space)


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E5_E6_DIRECTIONAL_EVIDENCE_SURGERY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e6

    def patched(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        result = original(snapshot, upstream)
        if not isinstance(result, EngineResult):
            return result
        out = _out(result)
        e5_result = upstream.get("E5") or upstream.get("e5")
        e5 = _out(e5_result) if e5_result is not None else {}
        direction = _text(out.get("direction") or out.get("candidate_direction") or out.get("direction_thesis") or out.get("thesis_direction"))
        if not direction:
            finding = _text(out.get("finding"))
            direction = "BUY" if finding.startswith("BUY") else "SELL" if finding.startswith("SELL") else ""

        reasons = [str(x) for x in list(out.get("reason_codes") or out.get("reasons") or []) if str(x)]
        observations = [str(x) for x in list(out.get("observations") or []) if str(x)]
        preferred = _text(e5.get("preferred_location") or e5.get("location_direction") or e5.get("directional_location"))

        if direction in {"BUY", "SELL"}:
            directional, opposing = _directional_space(e5, direction)
            out["e5_directional_space_atr"] = directional
            out["e5_opposing_space_atr"] = opposing

            # Location evidence may support a direction only when that side has
            # usable structural space. Merely being above/below value is not
            # directional support when the path to the next opposing level is
            # too short for a professional trade.
            if directional is not None and directional < MIN_DIRECTIONAL_SPACE_ATR:
                observations = [x for x in observations if x != "E5_LOCATION_VALUE_SUPPORT"]
                reasons = [x for x in reasons if x != "E5_LOCATION_VALUE_SUPPORT"]
                if "E5_DIRECTIONAL_SPACE_CONSTRAINED" not in observations:
                    observations.append("E5_DIRECTIONAL_SPACE_CONSTRAINED")
                if "E5_DIRECTIONAL_SPACE_CONSTRAINED" not in reasons:
                    reasons.append("E5_DIRECTIONAL_SPACE_CONSTRAINED")
                out["e5_directional_alignment"] = "CONSTRAINED"

            preferred_dir = None
            if preferred in {"LONG", "BUY"}:
                preferred_dir = "BUY"
            elif preferred in {"SHORT", "SELL"}:
                preferred_dir = "SELL"

            if preferred_dir is not None and preferred_dir != direction:
                observations = [x for x in observations if x != "E5_LOCATION_VALUE_SUPPORT"]
                if "E5_OPPOSITE_DIRECTIONAL_LOCATION" not in observations:
                    observations.append("E5_OPPOSITE_DIRECTIONAL_LOCATION")
                if "E5_DIRECTIONAL_LOCATION_CONFLICT" not in observations:
                    observations.append("E5_DIRECTIONAL_LOCATION_CONFLICT")
                reasons = [x for x in reasons if x != "E5_LOCATION_VALUE_SUPPORT"]
                if "E5_DIRECTIONAL_LOCATION_CONFLICT" not in reasons:
                    reasons.append("E5_DIRECTIONAL_LOCATION_CONFLICT")
                out["e5_directional_alignment"] = "CONFLICT"
            elif directional is not None and opposing is not None and directional > 0 and opposing >= directional * OPPOSING_ADVANTAGE_RATIO and opposing >= MIN_DIRECTIONAL_SPACE_ATR:
                observations = [x for x in observations if x != "E5_LOCATION_VALUE_SUPPORT"]
                if "E5_OPPOSITE_DIRECTIONAL_LOCATION" not in observations:
                    observations.append("E5_OPPOSITE_DIRECTIONAL_LOCATION")
                if "E5_DIRECTIONAL_LOCATION_CONFLICT" not in reasons:
                    reasons.append("E5_DIRECTIONAL_LOCATION_CONFLICT")
                out["e5_directional_alignment"] = "CONFLICT"
            elif out.get("e5_directional_alignment") is None:
                out["e5_directional_alignment"] = "ALIGNED" if preferred_dir == direction else "UNSPECIFIED"

        out["observations"] = observations
        out["reason_codes"] = list(dict.fromkeys(reasons))
        out["reasons"] = list(dict.fromkeys(reasons))
        out["e5_e6_directional_evidence_surgery"] = VERSION
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, tuple(out["reason_codes"]))

    pipeline_module.analyze_e6 = patched
    pipeline_module._E5_E6_DIRECTIONAL_EVIDENCE_SURGERY_INSTALLED = True

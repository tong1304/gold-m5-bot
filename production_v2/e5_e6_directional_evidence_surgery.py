from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E5_E6_DIRECTIONAL_EVIDENCE_SURGERY_V1"


def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _directional_space(e5: dict[str, Any], direction: str) -> tuple[float | None, float | None]:
    long_space = e5.get("available_space_atr_long")
    short_space = e5.get("available_space_atr_short")
    try:
        long_space = float(long_space) if long_space is not None else None
    except (TypeError, ValueError):
        long_space = None
    try:
        short_space = float(short_space) if short_space is not None else None
    except (TypeError, ValueError):
        short_space = None
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
        direction = _text(out.get("direction") or out.get("candidate_direction") or out.get("thesis_direction"))
        preferred = _text(e5.get("preferred_location") or e5.get("location_direction") or e5.get("directional_location"))
        if not direction:
            direction = "BUY" if _text(out.get("finding")).startswith("BUY") else "SELL" if _text(out.get("finding")).startswith("SELL") else ""

        reasons = [str(x) for x in list(out.get("reason_codes") or out.get("reasons") or []) if str(x)]
        observations = [str(x) for x in list(out.get("observations") or []) if str(x)]

        if direction in {"BUY", "SELL"}:
            directional, opposing = _directional_space(e5, direction)
            if preferred in {"LONG", "SHORT", "BUY", "SELL"}:
                preferred_dir = "BUY" if preferred in {"LONG", "BUY"} else "SELL"
                if preferred_dir != direction:
                    if "E5_LOCATION_VALUE_SUPPORT" in observations:
                        observations = [x for x in observations if x != "E5_LOCATION_VALUE_SUPPORT"]
                    for item in ("E5_OPPOSITE_DIRECTIONAL_LOCATION", "E5_DIRECTIONAL_LOCATION_CONFLICT"):
                        if item not in observations:
                            observations.append(item)
                    if "E5_LOCATION_VALUE_SUPPORT" in reasons:
                        reasons = [x for x in reasons if x != "E5_LOCATION_VALUE_SUPPORT"]
                    if "E5_DIRECTIONAL_LOCATION_CONFLICT" not in reasons:
                        reasons.append("E5_DIRECTIONAL_LOCATION_CONFLICT")
                    out["e5_directional_alignment"] = "CONFLICT"
                else:
                    out["e5_directional_alignment"] = "ALIGNED"
            else:
                out["e5_directional_alignment"] = "UNSPECIFIED"
            out["e5_directional_space_atr"] = directional
            out["e5_opposing_space_atr"] = opposing

        out["observations"] = observations
        out["reason_codes"] = reasons
        out["reasons"] = reasons
        out["e5_e6_directional_evidence_surgery"] = VERSION
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, reasons)

    pipeline_module.analyze_e6 = patched
    pipeline_module._E5_E6_DIRECTIONAL_EVIDENCE_SURGERY_INSTALLED = True

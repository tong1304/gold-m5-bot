from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .e6_opportunity_guard import _direction, _fallback_opportunity, _watch


WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _has_no_setup(result: EngineResult) -> bool:
    out = _out(result)
    setup = str(out.get("setup") or out.get("setup_family") or "").upper().strip()
    finding = str(out.get("finding") or "").upper().strip()
    reasons = {
        str(code).upper().strip()
        for code in (
            *(out.get("reason_codes") or []),
            *(out.get("reasons") or []),
            *(result.reason_codes or ()),
        )
    }
    return (
        setup in {"", "NO_SETUP", "UNKNOWN", "NONE"}
        and (
            "NO_CAUSAL_OPPORTUNITY" in reasons
            or "NO CAUSAL SETUP HYPOTHESIS" in finding
            or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding
        )
    )


def install(e6_module) -> None:
    if getattr(e6_module, "_E6_RUNTIME_AUTHORITY_INSTALLED", False):
        return

    original = e6_module.analyze_e6

    def runtime_authority(market_data, upstream):
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result

        out = _out(result)
        setup = str(out.get("setup") or "").upper().strip()
        if setup in WATCH_SETUPS and out.get("watch_only") is True and out.get("trade_ready") is not True:
            return result

        if not _has_no_setup(result):
            return result

        candidate = _fallback_opportunity(upstream)
        if candidate is None:
            return result

        watch = _watch(result, candidate)
        watch_out = dict(watch.output or {})
        watch_out["runtime_authority"] = "E6_FINAL_OPPORTUNITY_MEMBRANE"
        watch_out["runtime_rescue_reason"] = "CAUSAL_E1_E5_EVIDENCE_SURVIVES_LEGACY_NO_SETUP"
        watch_out["runtime_direction_source"] = _direction(
            candidate.get("direction"),
        )
        return EngineResult(
            watch.engine_id,
            watch.name,
            False,
            watch.score,
            watch_out,
            watch.reason_codes,
        )

    e6_module.analyze_e6 = runtime_authority
    e6_module._E6_RUNTIME_AUTHORITY_INSTALLED = True

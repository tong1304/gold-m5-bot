from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E6_SPACE_CONSISTENCY_SURGERY_V1"
MIN_SPACE_ATR = 0.75
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP"} or text.startswith(("BUY ", "BUY_", "BUY:")):
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_", "SELL:")):
        return "SELL"
    return "NEUTRAL"


def _out(result: EngineResult) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _e5_space(upstream: dict[str, EngineResult], direction: str) -> float:
    e5_result = upstream.get("E5")
    e5 = _out(e5_result) if e5_result else {}
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        value = float(e5.get(key) or 0.0)
        return value if value == value else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalize(result: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    out = _out(result)
    setup = _text(out.get("setup") or out.get("setup_family"))
    direction = _direction(out.get("direction") or out.get("direction_thesis") or out.get("thesis_direction"))
    if direction not in {"BUY", "SELL"} or setup not in WATCH_SETUPS:
        return result

    space = _e5_space(upstream, direction)
    missing = list(dict.fromkeys(str(x).strip().upper() for x in (out.get("missing_proof") or out.get("missing_evidence") or []) if str(x).strip()))
    reasons = list(dict.fromkeys(str(x).strip().upper() for x in (out.get("reason_codes") or out.get("reasons") or []) if str(x).strip()))

    if space >= MIN_SPACE_ATR:
        missing = [x for x in missing if x != "STRUCTURAL_SPACE_INSUFFICIENT"]
        reasons = [x for x in reasons if x != "STRUCTURAL_SPACE_INSUFFICIENT"]
    elif "STRUCTURAL_SPACE_INSUFFICIENT" not in missing:
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
        if "STRUCTURAL_SPACE_INSUFFICIENT" not in reasons:
            reasons.append("STRUCTURAL_SPACE_INSUFFICIENT")

    wait_for = [x for x in str(out.get("wait_for") or "").split(",") if x.strip()]
    if space >= MIN_SPACE_ATR:
        wait_for = [x.strip().upper() for x in wait_for if x.strip().upper() != "STRUCTURAL_SPACE_INSUFFICIENT"]
    elif not any(x.strip().upper() == "STRUCTURAL_SPACE_INSUFFICIENT" for x in wait_for):
        wait_for.append("STRUCTURAL_SPACE_INSUFFICIENT")
    wait_for = list(dict.fromkeys(x for x in wait_for if x.strip()))

    out["available_space_atr"] = round(space, 4)
    out["missing_proof"] = missing
    out["missing_evidence"] = missing
    out["reason_codes"] = reasons
    out["reasons"] = reasons
    out["wait_for"] = ",".join(wait_for)
    out["space_consistency_authority"] = "E5"
    out["space_consistency_version"] = VERSION

    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, tuple(reasons))


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E6_SPACE_CONSISTENCY_SURGERY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e6

    def patched_analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result
        return _normalize(result, upstream)

    pipeline_module.analyze_e6 = patched_analyze_e6
    pipeline_module._E6_SPACE_CONSISTENCY_SURGERY_INSTALLED = True
    module_name = getattr(pipeline_module, "__name__", type(pipeline_module).__name__)
    print(f"[PRODUCTION V2] E6_SPACE_CONSISTENCY_SURGERY_BINDING version={VERSION} module={module_name}", flush=True)

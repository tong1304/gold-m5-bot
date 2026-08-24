from __future__ import annotations

# Explicit V12.1 setup priority. Lower number wins regardless of setup score.
ENGINE_PRIORITY = {
    "E7": 0,
    "E4": 1,
    "E1": 2,
    "E2": 3,
    "E5": 4,
    "E3": 5,
    "E6": 6,
    "E8": 7,
}


def choose_priority_setup(candidates):
    if not candidates:
        return None

    def key(candidate):
        engine = str(candidate.get("engine", "")).upper()
        return (ENGINE_PRIORITY.get(engine, 999), -float(candidate.get("quality", 0) or 0))

    return min(candidates, key=key)


def signal_reason(result):
    signal = str(result.get("signal", "")).upper()
    if signal == "NO_TRADE" or signal in ("", "NONE"):
        reasons = result.get("rejection_reasons") or result.get("reason") or []
        if isinstance(reasons, str):
            return reasons or "NO_TRADE"
        for reason in reasons:
            if reason:
                return str(reason)
        return "NO_TRADE"

    engine = str(result.get("engine", "NONE")).upper()
    strategy = str(result.get("strategy", "NONE")).upper()
    return f"{engine}_{strategy}_PASS"

from __future__ import annotations


def is_actionable_signal(result) -> bool:
    """Return True only when E9 has authorized a BUY/SELL signal for notification.

    This boundary deliberately does not represent broker execution. The user
    creates the order manually after receiving the alert.
    """
    decision = getattr(result, "decision", None)
    if decision not in {"BUY", "SELL"} or not bool(getattr(result, "gate_passed", False)):
        return False

    e9 = next((engine for engine in getattr(result, "engines", ()) if getattr(engine, "engine_id", None) == "E9"), None)
    if e9 is None:
        return False

    e9_output = getattr(e9, "output", {}) or {}
    return e9_output.get("decision") == decision

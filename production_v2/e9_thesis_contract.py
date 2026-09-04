from __future__ import annotations


def install(e9_module) -> None:
    """Make concrete E6 setup-thesis states visible to E9 without authorizing a trade."""
    original_thesis_state = e9_module._thesis_state
    original_has_surviving = e9_module._has_surviving_thesis

    def thesis_state(e6):
        state = str(e6.get("state") or e6.get("setup_state") or e6.get("opportunity_stage") or "").upper().strip()
        if state in {"SETUP_THESIS", "THESIS_CONTESTED"}:
            return "HYPOTHESIS"
        return original_thesis_state(e6)

    def has_surviving_thesis(e6, identity):
        direction, setup, _ = identity
        if direction not in e9_module.DIRECTIONS or setup in e9_module.NO_THESIS_SETUP:
            return False
        return thesis_state(e6) in {"HYPOTHESIS", "VALIDATING", "MATURE"}

    e9_module._thesis_state = thesis_state
    e9_module._has_surviving_thesis = has_surviving_thesis

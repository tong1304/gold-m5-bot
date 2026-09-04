from __future__ import annotations

from typing import Any

from .evidence_ledger import build_evidence_ledger, ledger_for_e9


def _install_once(module: Any, marker: str, function_name: str, wrapper_factory) -> None:
    if getattr(module, marker, False):
        return
    original = getattr(module, function_name)
    setattr(module, function_name, wrapper_factory(original))
    setattr(module, marker, True)


def install(e6_module: Any, e9_module: Any) -> None:
    """Make the same specialist evidence ledger available to thesis and governance.

    E1-E5 evidence is frozen into the snapshot immediately before E6. The
    final E1-E8 ledger is refreshed immediately before E9. Neither ledger can
    make a decision; it is collaboration context only.
    """

    def e6_wrapper(original):
        def wrapped(market_data, upstream):
            market_data["evidence_ledger"] = build_evidence_ledger(upstream)
            market_data["evidence_ledger"]["phase"] = "PRE_THESIS_E1_E5"
            return original(market_data, upstream)
        return wrapped

    def e9_wrapper(original):
        def wrapped(snapshot, upstream):
            snapshot["evidence_ledger"] = ledger_for_e9(upstream)
            snapshot["evidence_ledger"]["phase"] = "FINAL_GOVERNANCE_E1_E8"
            return original(snapshot, upstream)
        return wrapped

    _install_once(e6_module, "_EVIDENCE_COLLABORATION_E6_INSTALLED", "analyze_e6", e6_wrapper)
    _install_once(e9_module, "_EVIDENCE_COLLABORATION_E9_INSTALLED", "analyze_e9", e9_wrapper)

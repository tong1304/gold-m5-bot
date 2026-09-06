from __future__ import annotations

from typing import Any

from .e2_opportunity_surgery import enrich_directional_opportunity_book


def _score(output: dict[str, Any], side: str) -> float:
    tree = output.get("market_tree")
    if isinstance(tree, dict):
        evidence = tree.get("directional_evidence")
        if isinstance(evidence, dict):
            try:
                raw = float(evidence.get(side, 0.0) or 0.0)
                return max(0.0, min(raw / 7.0, 1.0))
            except (TypeError, ValueError):
                pass
    try:
        score = float(output.get("opportunity_score", 0.0) or 0.0) / 100.0
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(score, 1.0))


def install(pipeline_module, e2_module) -> None:
    """Bind the non-executing directional Opportunity Book to runtime E2."""
    if getattr(pipeline_module, "_E2_OPPORTUNITY_BOOK_BOUND", False):
        return
    original = pipeline_module.analyze_e2

    def wrapped(snapshot: dict[str, Any]):
        output = original(snapshot)
        if not isinstance(output, dict):
            return output
        candle = snapshot.get("candle_close_timestamp") or snapshot.get("candle") or {}
        previous_book = snapshot.get("previous_opportunity_book")
        return enrich_directional_opportunity_book(
            output,
            candle=candle,
            buy_score=_score(output, "up"),
            sell_score=_score(output, "down"),
            previous_book=previous_book if isinstance(previous_book, dict) else None,
        )

    pipeline_module.analyze_e2 = wrapped
    e2_module.analyze_e2 = wrapped
    pipeline_module._E2_OPPORTUNITY_BOOK_BOUND = True

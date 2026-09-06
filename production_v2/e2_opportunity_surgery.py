from __future__ import annotations

from typing import Any

from .opportunity_book import build_directional_watches, update_book


def enrich_directional_opportunity_book(
    output: dict[str, Any],
    *,
    candle: Any,
    buy_score: Any,
    sell_score: Any,
    previous_book: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach a non-executing BUY/SELL opportunity book to E2 output.

    E2's existing primary direction remains authoritative for its own directional
    classification. The book separately preserves the counter-directional path so
    a temporary lead does not erase a still-valid conditional opportunity.
    """
    out = dict(output or {})
    buy = float(buy_score or 0.0)
    sell = float(sell_score or 0.0)
    watches = build_directional_watches(
        candle,
        buy_score=buy,
        sell_score=sell,
        buy_wait_for=out.get("buy_confirmation_required") or ["BUY_CONFIRMATION"],
        sell_wait_for=out.get("sell_confirmation_required") or ["SELL_CONFIRMATION"],
    )
    book = update_book(previous_book, watches)
    out["opportunity_book"] = book
    out["opportunity_competition"] = book["competition"]
    out["opportunity_leader"] = book["leader"]
    out["directional_watches"] = book["candidates"]
    out["opportunity_selection"] = {
        "leader": book["leader"],
        "competition": book["competition"],
        "selection_authority": "E6_THESIS_E7_CONFIRMATION_E8_ECONOMICS_E9_GOVERNANCE",
        "counter_direction_preserved": len(book["candidates"]) == 2,
    }
    return out

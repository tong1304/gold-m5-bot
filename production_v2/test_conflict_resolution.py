from .conflict_resolution import build_conflict_ledger


def _engine(engine_id, **output):
    from .contracts import EngineResult
    return EngineResult(engine_id, engine_id, None, 0.0, output, tuple(output.get("reason_codes", ())))


def test_detects_direction_vs_location_conflict_without_changing_evidence():
    results = {
        "E1": _engine("E1", market_state="TREND_UP", trend_state="UP", pressure="UP"),
        "E3": _engine("E3", finding="BULLISH_STRUCTURE", structure_direction="UP"),
        "E5": _engine("E5", direction="BUY", structural_location="AT_RESISTANCE", available_space_atr_long=0.19),
        "E6": _engine("E6", direction="BUY", setup="AUCTION_ACCEPTANCE_CONTINUATION"),
        "E7": _engine("E7", confirmation_state="PENDING"),
        "E8": _engine("E8", risk_state="UNRESOLVED"),
    }
    ledger = build_conflict_ledger(results)
    codes = {item["code"] for item in ledger["conflicts"]}
    assert "DIRECTION_LOCATION_CONFLICT" in codes
    assert ledger["summary"]["blocking_conflicts"] >= 1
    assert ledger["conflicts"][0]["authority"] in {"E5", "E7", "E8", "CROSS_BRAIN"}


def test_agreement_is_not_reported_as_conflict():
    results = {
        "E1": _engine("E1", market_state="TREND_UP", trend_state="UP", pressure="UP"),
        "E3": _engine("E3", finding="BULLISH_STRUCTURE", structure_direction="UP"),
        "E5": _engine("E5", direction="BUY", structural_location="INSIDE_STRUCTURE", available_space_atr_long=3.0),
        "E6": _engine("E6", direction="BUY", setup="TREND_CONTINUATION"),
        "E7": _engine("E7", confirmation_state="PROVEN"),
        "E8": _engine("E8", risk_state="READY"),
    }
    ledger = build_conflict_ledger(results)
    assert ledger["summary"]["blocking_conflicts"] == 0

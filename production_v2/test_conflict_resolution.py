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


def test_e2_direction_disagreement_is_a_cross_brain_conflict():
    results = {
        "E1": _engine("E1", market_state="TREND_UP", trend_state="UP", pressure="UP"),
        "E2": _engine("E2", direction="SELL", opportunity_state="WAIT"),
        "E3": _engine("E3", finding="BULLISH_STRUCTURE", structure_direction="UP"),
        "E5": _engine("E5", direction="BUY", structural_location="INSIDE_STRUCTURE", available_space_atr_long=3.0),
        "E6": _engine("E6", direction="BUY", setup="TREND_CONTINUATION", setup_state="VALIDATING"),
        "E7": _engine("E7", confirmation_state="INCOMPLETE"),
        "E8": _engine("E8", risk_state="READY"),
    }
    ledger = build_conflict_ledger(results)
    item = next(x for x in ledger["conflicts"] if x["code"] == "DIRECTION_EVIDENCE_CONFLICT")
    assert "E2" in item["brains"]
    assert item["evidence"]["E2"] == "SELL"
    assert ledger["summary"]["has_conflict"] is True


def test_neutral_e2_does_not_create_direction_conflict():
    results = {
        "E1": _engine("E1", trend_state="UP"),
        "E2": _engine("E2", direction="NEUTRAL"),
        "E3": _engine("E3", structure_direction="UP"),
        "E5": _engine("E5", direction="BUY", structural_location="INSIDE_STRUCTURE", available_space_atr_long=3.0),
        "E6": _engine("E6", direction="BUY", setup_state="VALIDATING"),
        "E7": _engine("E7", confirmation_state="INCOMPLETE"),
        "E8": _engine("E8", risk_state="READY"),
    }
    ledger = build_conflict_ledger(results)
    assert not any(x["code"] == "DIRECTION_EVIDENCE_CONFLICT" for x in ledger["conflicts"])


def test_supportive_value_is_not_a_conflict():
    results = {
        "E1": _engine("E1", trend_state="UP"),
        "E2": _engine("E2", direction="NEUTRAL"),
        "E3": _engine("E3", structure_direction="UP"),
        "E5": _engine("E5", direction="BUY", value_state="DISCOUNT", structural_location="INSIDE_STRUCTURE", available_space_atr_long=3.0),
        "E6": _engine("E6", direction="BUY", setup_state="VALIDATING"),
        "E7": _engine("E7", confirmation_state="PROVEN"),
        "E8": _engine("E8", risk_state="READY"),
    }
    ledger = build_conflict_ledger(results)
    assert any(x["code"] == "VALUE_SUPPORTS_BUY" for x in ledger["conflicts"])
    assert ledger["summary"]["blocking_conflicts"] == 0

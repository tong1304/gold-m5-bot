from production_v2.contracts import EngineResult
from production_v2.evidence_ledger import build_evidence_ledger, classify_conflict


def result(engine_id, output):
    return EngineResult(engine_id, engine_id, output.get("gate_passed"), 0.0, output, tuple(output.get("reason_codes", ())))


def test_ledger_keeps_specialist_roles_and_does_not_make_a_decision():
    results = {
        "E1": result("E1", {"direction": "SELL", "finding": "BEARISH REGIME"}),
        "E3": result("E3", {"direction": "BUY", "finding": "BULLISH STRUCTURE"}),
        "E6": result("E6", {"direction": "SELL", "setup": "OPPORTUNITY_WATCH", "watch_only": True}),
    }
    ledger = build_evidence_ledger(results)
    assert ledger["authority"] == "NON_AUTHORITATIVE"
    assert ledger["decision_authority"] == "E9_ONLY"
    assert ledger["brains"]["E1"]["role"] == "MARKET_STATE"
    assert ledger["brains"]["E3"]["role"] == "MARKET_STRUCTURE"
    assert ledger["brains"]["E6"]["role"] == "SETUP_FORMATION"
    assert "decision" not in ledger


def test_soft_disagreement_is_not_a_blocking_conflict():
    assert classify_conflict("COUNTER_EVIDENCE", confirmed=False, invalidating=False) == "SOFT"


def test_confirmed_invalidation_is_hard():
    assert classify_conflict("THESIS_INVALIDATION", confirmed=True, invalidating=True) == "HARD"

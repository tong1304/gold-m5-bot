from datetime import datetime

from production_v2.contracts import DecisionResult, EngineResult
from production_v2.notifications.no_trade import format_no_trade
from production_v2.notifications.telegram import format_decision


def _engines():
    return tuple(
        EngineResult(eid, eid, False, 50.0, output, tuple(reasons))
        for eid, output, reasons in (
            ("E1", {"finding": "MARKET_STATE=TRANSITION", "observations": ["ema20_vs_ema50=DOWN"]}, ["DATA_INTEGRITY_VALIDATED"]),
            ("E2", {"finding": "UNRESOLVED", "observations": ["missing_evidence=follow-through"]}, ["OPPORTUNITY_MATURITY"]),
            ("E3", {"finding": "BEARISH_STRUCTURE", "observations": ["protected_high=78931.49"]}, ["CAUSAL_STRUCTURE_ANALYSIS"]),
            ("E4", {"finding": "LOW_SWEEP_REJECTION", "observations": ["event=LOW_SWEEP_REJECTION", "liquidity_taker=SELLERS"]}, ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]),
            ("E5", {"finding": "FAVORABLE_LOCATION", "observations": ["available_space_atr_short=0.34"]}, ["SHORT_SPACE_CONSTRAINED"]),
            ("E6", {"finding": "SELL AUCTION_ACCEPTANCE_CONTINUATION is validating"}, ["SETUP_NOT_TRADE_READY"]),
            ("E7", {"finding": "The thesis remains a hypothesis", "observations": ["valid_closed_candle_trigger_missing"]}, ["PROOF_GATES_INCOMPLETE"]),
            ("E8", {"finding": "UNRESOLVED", "observations": ["REAL_RR_BELOW_MINIMUM"]}, ["INVALID_TRADE_GEOMETRY"]),
            ("E9", {"decision": "NO_TRADE", "decision_reasons": ["INVALID_TRADE_GEOMETRY"]}, ["INVALID_TRADE_GEOMETRY"]),
        )
    )


def test_no_trade_uses_actual_engine_findings_and_evidence():
    result = DecisionResult("BTC", "M5", "NO_TRADE", False, 0.0, _engines(), {"decision_reasons": ["INVALID_TRADE_GEOMETRY"]})
    text = format_no_trade({"BTC": result}, datetime(2026, 8, 31, 0, 10))
    assert "MARKET_STATE=TRANSITION" in text
    assert "LOW_SWEEP_REJECTION" in text
    assert "liquidity_taker=SELLERS" in text
    assert "SELL AUCTION_ACCEPTANCE_CONTINUATION" in text
    assert "INVALID_TRADE_GEOMETRY" in text
    assert "E1 — สภาวะตลาด" in text
    assert "E9 — การตัดสินใจ" in text


def test_trade_alert_preserves_all_engine_findings():
    engines = list(_engines())
    engines[-1] = EngineResult("E9", "E9", True, 90.0, {"decision": "SELL"}, ("APPROVED",))
    plan = {"valid": True, "entry": 100.0, "stop_loss": 101.0, "take_profit_1": 98.0, "take_profit_2": 97.0, "rr_tp2": 3.0}
    result = DecisionResult("BTC", "M5", "SELL", True, 90.0, tuple(engines), {"trade_plan": plan})
    text = format_decision(result)
    assert "MARKET_STATE=TRANSITION" in text
    assert "LOW_SWEEP_REJECTION" in text
    assert "SELL AUCTION_ACCEPTANCE_CONTINUATION" in text
    assert "SELL" in text

from production_v2.trade_alert_boundary import ALERT_NONE, ALERT_READY, USER_ACTION_REQUIRED, build_trade_alert, should_alert


class Result:
    def __init__(self, decision="NO_TRADE", gate_passed=False):
        self.decision = decision
        self.gate_passed = gate_passed


def lifecycle(stage="TRADE"):
    return {
        "lifecycle_stage": stage,
        "opportunity_id": "BUY|SETUP|EVENT-1",
        "origin_event_id": "EVENT-1",
        "event_id": "EVENT-2",
    }


def test_trade_stage_creates_alert_for_user_not_broker():
    alert = build_trade_alert(Result("BUY", True), lifecycle())
    assert alert["state"] == ALERT_READY
    assert alert["user_action"] == USER_ACTION_REQUIRED
    assert alert["direction"] == "BUY"
    assert alert["alert_authorized_by"] == "E9"
    assert alert["broker_execution"] is False
    assert alert["position_open"] is False


def test_no_trade_never_creates_alert():
    alert = build_trade_alert(Result("NO_TRADE", False), lifecycle())
    assert alert["state"] == ALERT_NONE
    assert alert["user_action"] is None


def test_alert_requires_trade_lifecycle_even_if_e9_says_buy():
    alert = build_trade_alert(Result("BUY", True), lifecycle("E8_READY"))
    assert alert["state"] == ALERT_NONE


def test_alert_emits_only_on_transition():
    current = build_trade_alert(Result("SELL", True), lifecycle())
    assert should_alert(None, current) is True
    assert should_alert({"state": ALERT_READY}, current) is False

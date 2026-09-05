from production_v2.contracts import DecisionResult, EngineResult
from production_v2.execution_state import authorize_order, transition
from production_v2.opportunity_lifecycle import advance_opportunity
from production_v2.statistics import StatisticsStore


def _result(decision="NO_TRADE", gate=False):
    e9=EngineResult("E9","Master Decision Brain",gate,90,{"decision":decision},())
    return DecisionResult(decision=decision,gate_passed=gate,engines=(e9,))


def test_e9_authorization_is_not_execution():
    result=_result("BUY",True)
    assert authorize_order(result)["state"]=="ORDER_INTENT"
    assert authorize_order(result)["state"]!="POSITION_OPEN"


def test_execution_requires_explicit_position_open():
    result=_result("BUY",True)
    execution=transition(authorize_order(result),"ORDER_SUBMITTED",order_id="o1")
    assert execution["state"]=="ORDER_SUBMITTED"
    execution=transition(execution,"ACCEPTED",order_id="o1")
    assert execution["state"]=="ACCEPTED"
    execution=transition(execution,"POSITION_OPEN",order_id="o1",position_id="p1")
    assert execution["state"]=="POSITION_OPEN"


def test_watch_promotes_without_claiming_execution():
    previous={"state":"WATCHING","opportunity_id":"BUY|OPPORTUNITY_WATCH","direction":"BUY","setup":"OPPORTUNITY_WATCH","bars_waited":0}
    current={"candidate":True,"direction":"BUY","setup":"AUCTION_ACCEPTANCE_CONTINUATION","ready":True,"candle":"2026-09-05T12:25:00Z","wait_for":["E7_CONFIRMATION"]}
    lifecycle=advance_opportunity(previous,current)
    assert lifecycle["state"]=="READY"
    assert lifecycle["trade_authorized"] is False


def test_statistics_distinguish_authorization_and_execution():
    store=StatisticsStore(); result=_result("BUY",True)
    store.record(result)
    snapshot=store.snapshot()
    assert snapshot["e9_authorizations"]==1
    assert snapshot["executed_positions"]==0
    result=DecisionResult(decision="BUY",gate_passed=True,engines=result.engines,execution_state={"state":"POSITION_OPEN","order_id":"o1","position_id":"p1","error":None})
    store.record(result)
    assert store.snapshot()["executed_positions"]==1

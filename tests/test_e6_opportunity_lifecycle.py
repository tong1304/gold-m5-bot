from production_v2.e6_lifecycle_runtime import advance_lifecycle


def test_watch_survives_one_new_closed_candle_when_identity_and_evidence_persist():
    previous={"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","age_bars":0}
    current={"opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","causal_opportunity":True,"invalidated":False}
    result=advance_lifecycle(previous,current,bar_id="101")
    assert result["lifecycle_state"]=="OPPORTUNITY_WATCH"
    assert result["age_bars"]==1
    assert result["opportunity_id"]==previous["opportunity_id"]


def test_matching_watch_matures_to_setup_thesis_only_when_current_causal_thesis_exists():
    previous={"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","age_bars":1}
    current={"opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","causal_opportunity":True,"thesis_proven":True,"invalidated":False}
    result=advance_lifecycle(previous,current,bar_id="102")
    assert result["lifecycle_state"]=="SETUP_THESIS"
    assert result["age_bars"]==2
    assert result["thesis_bar_id"]=="102"


def test_direction_change_replaces_old_opportunity_instead_of_mutating_it():
    previous={"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","age_bars":2}
    current={"opportunity_id":"SELL|LIQUIDITY_RESPONSE|event-103","direction":"SELL","setup_family":"LIQUIDITY_RESPONSE","causal_opportunity":True}
    result=advance_lifecycle(previous,current,bar_id="103")
    assert result["lifecycle_state"]=="REPLACED"
    assert result["previous_opportunity_id"]==previous["opportunity_id"]
    assert result["opportunity_id"]==current["opportunity_id"]


def test_invalidated_watch_does_not_carry_forward_even_if_same_identity_returns():
    previous={"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","age_bars":2}
    current={"opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","causal_opportunity":True,"invalidated":True}
    result=advance_lifecycle(previous,current,bar_id="103")
    assert result["lifecycle_state"]=="INVALIDATED"
    assert result["wait_for"]=="NEW_CAUSAL_OPPORTUNITY"


def test_watch_expires_after_bounded_age_without_proof():
    previous={"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","age_bars":5}
    current={"opportunity_id":"BUY|LIQUIDITY_RESPONSE|event-100","direction":"BUY","setup_family":"LIQUIDITY_RESPONSE","causal_opportunity":True,"thesis_proven":False,"invalidated":False}
    result=advance_lifecycle(previous,current,bar_id="106",max_watch_bars=5)
    assert result["lifecycle_state"]=="EXPIRED"
    assert result["age_bars"]==6
    assert result["wait_for"]=="NEW_CAUSAL_OPPORTUNITY"

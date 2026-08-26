# ENGINE 06 — TRADE SETUP BRAIN v2.0

## PURPOSE
Determine whether the market evidence has formed a recognizable, tradable setup archetype and describe its current maturity. It does not authorize entry.

## SUB-ENGINES
6A Setup Context · 6B Setup Archetype · 6C Setup Formation State Machine · 6D Setup Invalidation · 6E Setup Quality · 6F Setup Maturity

## INPUT
E1–E5 evidence, closed-candle price behavior, structure/liquidity/location references, approved setup definitions and formation history.

## PROCESSING
Generate candidate setup archetypes from context; track formation state (forming, mature, failed, expired); test invalidation; distinguish thesis from executable setup; compare competing setups and preserve the strongest explanation.

## OUTPUT
candidate_setups[], selected_setup, setup_state, formation_stage, direction, invalidation, setup_quality, maturity, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. NO_SETUP, FORMING and FAILED are valid analytical conclusions. They are not execution gates.

## SCORE
Setup quality and maturity are evidence. Confidence measures certainty of the setup interpretation.

## TRACEABILITY
Record setup definition/version, state transitions, triggering evidence, invalidation evidence, candle references and upstream conclusions.

## DECISION BOUNDARY
Setup identification and evaluation only.

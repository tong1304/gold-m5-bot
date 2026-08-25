# ENGINE 06 — TRADE SETUP ENGINE v1.0

## PURPOSE
Identify and evaluate whether a defined setup archetype is forming and remains valid.

## SUB-ENGINES
6A Setup Context · 6B Setup Archetype · 6C Setup Formation State Machine · 6D Setup Invalidation · 6E Setup Quality · 6F Setup Maturity

## INPUT
ENGINE 01–05 outputs, permitted price/structure/liquidity/location evidence, setup definitions.

## PROCESSING
Evaluate context, identify archetype, track formation state, invalidation, quality, maturity.

## OUTPUT
Setup identity/state, formation stage, validity/invalidation status, quality/maturity, confidence, reason codes.

## GATE
Reject/hold setup processing when required context is invalid or invalidation conditions are met.

## SCORE
Setup quality/maturity is evidence only and cannot independently authorize entry.

## TRACEABILITY
Record setup definition/version, source evidence, state transitions, invalidation reason, timestamp, scores, confidence, upstream versions.

## DECISION BOUNDARY
Setup state only; no execution or independent BUY/SELL decision.
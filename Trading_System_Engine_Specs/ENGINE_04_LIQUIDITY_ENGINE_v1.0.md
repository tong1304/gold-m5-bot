# ENGINE 04 — LIQUIDITY ENGINE v1.0

## PURPOSE
Identify relevant liquidity locations and price interaction with them.

## SUB-ENGINES
4A Liquidity Zone Detection · 4B Sweep Detection · 4C Reaction/Rejection · 4D Acceptance · 4E Reclaim/Failed Break · 4F Liquidity Strength/Quality

## INPUT
Market state, regime, structure outputs, OHLCV, permitted liquidity evidence.

## PROCESSING
Detect zones, sweeps, reactions, acceptance, reclaim/failed-break behavior, liquidity quality.

## OUTPUT
Liquidity zones/events, interaction state, quality/confidence, reason codes.

## GATE
Block conclusions when required price/structure evidence is invalid or insufficient.

## SCORE
Liquidity quality is analytical evidence only; it cannot create an entry decision.

## TRACEABILITY
Record source candles, zone/event IDs, upstream versions, timestamps, gate status, scores, confidence, reason codes.

## DECISION BOUNDARY
Liquidity analysis only; no trade decision.
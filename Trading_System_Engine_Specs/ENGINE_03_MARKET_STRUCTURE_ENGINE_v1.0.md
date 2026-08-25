# ENGINE 03 — MARKET STRUCTURE ENGINE v1.0

## PURPOSE
Describe structural price behavior and validity for downstream engines.

## SUB-ENGINES
3A Swing Detection · 3B Structure Classification · 3C Break of Structure · 3D Structural Failure · 3E Structure Strength · 3F Internal vs External Structure

## INPUT
ENGINE 01–02 outputs, OHLCV candles, permitted swing/structure history, timestamps.

## PROCESSING
Detect swings, classify structure, evaluate breaks/failures, distinguish internal/external structure, estimate strength.

## OUTPUT
Structural state, swing references, BOS/failure evidence, classification, quality/confidence, reason codes.

## GATE
Block conclusions when insufficient history or invalid upstream state prevents reliable structure identification.

## SCORE
Structure quality/strength is evidence only and cannot authorize a trade.

## TRACEABILITY
Record candle references, lookback/version, upstream inputs, events, gate results, scores, confidence, reason codes.

## DECISION BOUNDARY
Structure analysis only; no entry, BUY/SELL, or execution decision.
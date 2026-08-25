# ENGINE 02 — MARKET REGIME ENGINE v1.0

## PURPOSE
Interpret market state into behavioral regime for downstream analysis.

## SUB-ENGINES
2A Trend Regime · 2B Range Regime · 2C Mean-Reversion Behavior · 2D Breakout Regime · 2E Regime Phase · 2F Regime Transition

## INPUT
ENGINE 01 outputs, permitted OHLCV/volatility evidence, regime metadata.

## PROCESSING
Classify regime behavior, phase, and transitions without making an entry decision.

## OUTPUT
Regime classification, phase, transition status, evidence, quality/confidence, reason codes.

## GATE
Block interpretation when required state evidence is invalid or unavailable.

## SCORE
Regime quality/confidence is analytical evidence and cannot override gates or authorize a trade.

## TRACEABILITY
Record upstream versions, symbol/timeframe, timestamp, outputs, gate results, scores, confidence, reason codes.

## DECISION BOUNDARY
Regime classification only; no BUY/SELL or execution instruction.
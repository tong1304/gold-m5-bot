# ENGINE 7 — CONFIRMATION

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 7A — TRIGGER
**INPUT**
- Armed setup, price, structure, liquidity, candle data.
**PROCESSING**
- Detect entry trigger, direction and timing.
**OUTPUT**
- `TRIGGER_BUY`, `TRIGGER_SELL`, `NO_TRIGGER`, `TRIGGER_STRENGTH`.
**GATE**
- No valid trigger => STOP.
**SCORE**
- Measures trigger strength.
**FILTER**
- Premature, counter-direction, weak trigger.
**EVIDENCE**
- Price event, setup state, structure/liquidity confirmation.
**DEPENDENCY**
- 6C, 6D.
**CONSUMER**
- 7B–7E, Engine 9.

## 7B — CANDLE QUALITY
**INPUT**
- Trigger candle, prior candles, OHLC, ATR/volatility, volume when available.
**PROCESSING**
- Assess body, wick, close location, relative range and direction.
**OUTPUT**
- `CANDLE_VALID`, `CANDLE_INVALID`, `CANDLE_QUALITY`.
**GATE**
- Candle does not support trigger => STOP.
**SCORE**
- Measures trigger-candle quality.
**FILTER**
- Indecision when unsuitable, excessive wick, abnormal candle.
**EVIDENCE**
- OHLC, body/range, wick, close position.
**DEPENDENCY**
- 7A, 1B.
**CONSUMER**
- 7E, Engine 9.

## 7C — FOLLOW-THROUGH
**INPUT**
- Trigger, subsequent candles, price, volume when available, structure.
**PROCESSING**
- Assess continuation, immediate failure and momentum persistence.
**OUTPUT**
- `FOLLOW_THROUGH`, `NO_FOLLOW_THROUGH`, `FOLLOW_THROUGH_STRENGTH`.
**GATE**
- If the setup policy requires follow-through and it is absent => STOP.
**SCORE**
- Measures persistence after trigger.
**FILTER**
- Immediate reversal, weak continuation.
**EVIDENCE**
- Subsequent closes, range, momentum, structure.
**DEPENDENCY**
- 7A, 7B, 4D.
**CONSUMER**
- 7E, Engine 9.

## 7D — SPREAD / EXECUTION QUALITY
**INPUT**
- Bid/ask or spread estimate, current price, slippage estimate, liquidity, entry distance.
**PROCESSING**
- Measure spread, estimate slippage, assess execution feasibility.
**OUTPUT**
- `EXECUTION_GOOD`, `EXECUTION_ACCEPTABLE`, `EXECUTION_BAD`, `EXECUTION_COST`.
**GATE**
- Execution cost above policy => STOP.
**SCORE**
- Measures execution quality.
**FILTER**
- Excessive spread, abnormal slippage, illiquid condition.
**EVIDENCE**
- Spread, slippage, market condition.
**DEPENDENCY**
- 1A and execution data.
**CONSUMER**
- Engine 8, Engine 9F.

Boundary: 7D measures execution quality; 9F owns the final Execution Gate.

## 7E — CONFIRMATION QUALITY
**INPUT**
- Trigger, candle quality, follow-through, execution quality, setup quality.
**PROCESSING**
- Combine confirmation evidence and resolve contradictions.
**OUTPUT**
- `CONFIRMATION_SCORE`, `CONFIRMATION_VALID`, `CONFIRMATION_CONFIDENCE`.
**GATE**
- Insufficient confirmation => STOP.
**SCORE**
- Measures overall confirmation quality.
**FILTER**
- Conflicting confirmation, weak trigger, bad execution.
**EVIDENCE**
- 7A–7D.
**DEPENDENCY**
- 7A–7D.
**CONSUMER**
- Engine 8, Engine 9.

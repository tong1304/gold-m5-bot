# 7A Trigger Detection

## 1. INPUT
- Valid setup from Engine 6, closed OHLC candles and approved trigger definitions.

## 2. PROCESSING
- Detect whether a defined entry trigger has occurred using only information available at the evaluation candle close.

## 3. OUTPUT
- Trigger event, trigger type, timestamp, evidence and confidence.

## 4. GATE
- FAIL when setup is invalid or trigger requirements are incomplete.
- Trigger detection alone is not final authorization.

## 5. SCORE
- 0-100 trigger-quality score based on rule completeness and confirmation.

## 6. TRACEABILITY
- Record setup ID, trigger rule/version, candle IDs, event and reason codes.
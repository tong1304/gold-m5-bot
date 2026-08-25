# 4B Sweep Detection

## 1. INPUT
- Liquidity zones, closed OHLC candles and confirmed structural levels.

## 2. PROCESSING
- Detect price penetration beyond a liquidity zone and record whether price returned/closed back within the reference area.

## 3. OUTPUT
- Sweep event, swept zone, penetration evidence, close behavior and confidence.

## 4. GATE
- FAIL when the liquidity reference is invalid or event confirmation is incomplete.

## 5. SCORE
- 0-100 sweep-quality score based on zone quality, penetration and rejection evidence.

## 6. TRACEABILITY
- Record zone ID, candle IDs, event state, rule version and reason codes.
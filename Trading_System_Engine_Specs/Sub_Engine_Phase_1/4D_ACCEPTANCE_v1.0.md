# 4D Acceptance

## 1. INPUT
- Liquidity/structure levels and subsequent closed-candle closes relative to those levels.

## 2. PROCESSING
- Determine whether price is accepted beyond a reference level rather than merely wicking through it.

## 3. OUTPUT
- Acceptance state, supporting closes, persistence and confidence.

## 4. GATE
- FAIL when level identity or required confirmation history is unavailable.

## 5. SCORE
- 0-100 acceptance-quality score from close persistence and level significance.

## 6. TRACEABILITY
- Store level ID, confirmation candles, ruleset, score and reason codes.
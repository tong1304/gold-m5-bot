# 3C Break of Structure

## 1. INPUT
- Confirmed structural levels, closed candle prices and structure classification.

## 2. PROCESSING
- Detect a confirmed close through a relevant structural level; distinguish wick-only events from structural breaks.

## 3. OUTPUT
- BOS event, broken level, direction-neutral event metadata, quality and confidence.

## 4. GATE
- FAIL when the referenced structural level is unconfirmed or stale under policy.

## 5. SCORE
- 0-100 BOS-quality score from close strength, level quality and confirmation.

## 6. TRACEABILITY
- Record level ID, candle ID, confirmation rule/version, event and reason codes.
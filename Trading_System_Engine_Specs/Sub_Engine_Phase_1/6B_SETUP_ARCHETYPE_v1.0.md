# 6B Setup Archetype

## 1. INPUT
- Validated context from 6A and upstream structure/liquidity/location evidence.

## 2. PROCESSING
- Classify the observed setup family, such as continuation, breakout, reversal or mean-reversion, only when its defining evidence exists.

## 3. OUTPUT
- Archetype label, supporting evidence, compatibility flags and confidence.

## 4. GATE
- FAIL when archetype requirements are incomplete or mutually contradictory.
- Does not issue BUY/SELL.

## 5. SCORE
- 0-100 archetype-quality score from evidence completeness and consistency.

## 6. TRACEABILITY
- Store evidence IDs, archetype ruleset/version, timestamp, output and reason codes.
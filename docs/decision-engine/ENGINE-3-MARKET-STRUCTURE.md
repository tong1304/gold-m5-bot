# ENGINE 3 — MARKET STRUCTURE

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 3A — SWING DETECTION
**INPUT**
- OHLC, ATR/volatility, candle sequence.
**PROCESSING**
- Detect swing highs/lows, significance, strength.
**OUTPUT**
- Swing High, Swing Low, Swing Strength, Swing ID.
**GATE**
- Unconfirmed swing => no structural point.
**SCORE**
- Measures swing clarity/significance.
**FILTER**
- Micro-noise, insignificant swings.
**EVIDENCE**
- Price reversal, range, ATR-relative movement.
**DEPENDENCY**
- 1A, 1B.
**CONSUMER**
- 3B–3E, Engine 4, Engine 5.

## 3B — STRUCTURE CLASSIFICATION
**INPUT**
- Swing points, price sequence, previous structure.
**PROCESSING**
- Classify HH/HL/LH/LL and structural sequence.
**OUTPUT**
- `BULLISH_STRUCTURE`, `BEARISH_STRUCTURE`, `RANGE_STRUCTURE`, `STRUCTURE_NEUTRAL`.
**GATE**
- Insufficient swing sequence => Neutral.
**SCORE**
- Measures structure clarity.
**FILTER**
- Conflicting swings, excessive noise.
**EVIDENCE**
- HH/HL/LH/LL sequence.
**DEPENDENCY**
- 3A.
**CONSUMER**
- 3C–3E, Engine 5, Engine 6.

## 3C — BOS
**INPUT**
- Swing levels, structure classification, current close, volatility.
**PROCESSING**
- Detect structural break, close confirmation, direction.
**OUTPUT**
- `BOS_UP`, `BOS_DOWN`, `NO_BOS`, `BOS_STRENGTH`.
**GATE**
- No structural reference => not a BOS.
**SCORE**
- Measures BOS strength.
**FILTER**
- Wick-only break, weak break, immediate rejection.
**EVIDENCE**
- Broken swing, closing price, follow-through.
**DEPENDENCY**
- 3A, 3B.
**CONSUMER**
- 3D, Engine 4, Engine 6, Engine 7.

## 3D — STRUCTURAL FAILURE
**INPUT**
- Structure, BOS, swing levels, closing price.
**PROCESSING**
- Detect failed BOS, structural invalidation and reversal.
**OUTPUT**
- `STRUCTURE_FAILED`, `STRUCTURE_VALID`, `FAILURE_DIRECTION`.
**GATE**
- No failure => structure remains valid.
**SCORE**
- Measures severity of structural failure.
**FILTER**
- Minor/wick-only violations.
**EVIDENCE**
- Failed BOS, close relative to structure, subsequent structure.
**DEPENDENCY**
- 3B, 3C.
**CONSUMER**
- Engine 4, Engine 6, Engine 9.

## 3E — STRUCTURE STRENGTH
**INPUT**
- Swing quality, structure sequence, BOS, structural failure, volatility.
**PROCESSING**
- Assess consistency, persistence and structural displacement.
**OUTPUT**
- `STRUCTURE_STRENGTH`, `STRUCTURE_CONFIDENCE`.
**GATE**
- No valid structure => strength invalid.
**SCORE**
- Measures overall structure quality.
**FILTER**
- Conflicting structure, excessive noise.
**EVIDENCE**
- Swing sequence, BOS, persistence.
**DEPENDENCY**
- 3A–3D.
**CONSUMER**
- Engines 5, 6, 7, 8, 9.

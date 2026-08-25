# ENGINE 1 — MARKET STATE

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 1A — DATA QUALITY
**INPUT**
- OHLCV, timestamp, symbol, timeframe, data-source status, candle sequence.
**PROCESSING**
- Validate candle completeness, OHLC relationships, timestamps, duplicates, missing candles, stale data, timeframe consistency.
**OUTPUT**
- `DATA_VALID`, `DATA_INVALID`, `QUALITY_SCORE`, `REJECTION_REASON`.
**GATE**
- Invalid/incomplete/stale/inconsistent data => STOP.
**SCORE**
- Measures completeness and reliability of market data.
**FILTER**
- Missing/duplicate candles, invalid OHLC, future timestamps, stale data.
**EVIDENCE**
- Candle sequence, timestamps, OHLC relationships, provider status.
**DEPENDENCY**
- Raw market data.
**CONSUMER**
- Engines 1–9.

## 1B — VOLATILITY
**INPUT**
- OHLC, ATR/true range features, historical volatility.
**PROCESSING**
- Measure current volatility, historical-relative volatility, percentile, contraction and expansion.
**OUTPUT**
- `VOL_LOW`, `VOL_NORMAL`, `VOL_HIGH`, `VOLATILITY_LEVEL`, `VOLATILITY_DIRECTION`.
**GATE**
- Insufficient volatility history => no valid volatility state.
**SCORE**
- Measures volatility level and abnormality.
**FILTER**
- Volatility too low for valid movement; volatility abnormally high for acceptable risk.
**EVIDENCE**
- ATR, true range, historical percentile.
**DEPENDENCY**
- 1A.
**CONSUMER**
- 1E, 1F, 1G, Engines 2, 5, 6, 7, 8.

## 1C — TREND STATE
**INPUT**
- Price, trend features, directional-strength features, swing structure, volatility.
**PROCESSING**
- Evaluate direction, alignment, slope, persistence, deterioration.
**OUTPUT**
- `TREND_UP`, `TREND_DOWN`, `NO_TREND`, `TREND_STRENGTH`.
**GATE**
- Insufficient directional evidence => do not declare a trend.
**SCORE**
- Measures trend strength and persistence.
**FILTER**
- Flat market, contradictory direction, weak persistence.
**EVIDENCE**
- Trend alignment, slope, directional strength, structure.
**DEPENDENCY**
- 1A, 1B.
**CONSUMER**
- Engine 2, Engine 3, Engine 5, Engine 6.

## 1D — RANGE STATE
**INPUT**
- Price, swing highs/lows, ATR/volatility, structure.
**PROCESSING**
- Identify range boundaries, width, containment, boundary stability, persistence.
**OUTPUT**
- `RANGE`, `RANGE_HIGH`, `RANGE_LOW`, `RANGE_MID`, `RANGE_STRENGTH`.
**GATE**
- Unclear boundaries => do not declare a range.
**SCORE**
- Measures clarity and persistence of the range.
**FILTER**
- Unstable boundaries, excessive range width, confirmed directional breakout.
**EVIDENCE**
- Repeated highs/lows, containment, range width.
**DEPENDENCY**
- 1A, 1B.
**CONSUMER**
- Engine 2, 3, 4, 5, 6.

## 1E — COMPRESSION
**INPUT**
- ATR/true range, candle ranges, volatility, range width, historical volatility.
**PROCESSING**
- Detect volatility contraction, range contraction, duration, intensity.
**OUTPUT**
- `COMPRESSED`, `NOT_COMPRESSED`, `COMPRESSION_SCORE`, `COMPRESSION_DURATION`.
**GATE**
- Insufficient evidence => no compression state.
**SCORE**
- Measures degree and duration of compression.
**FILTER**
- Unstable data or false/isolated compression.
**EVIDENCE**
- ATR contraction, candle-range contraction, volatility percentile.
**DEPENDENCY**
- 1A, 1B, 1D.
**CONSUMER**
- 1F, 1G, Engine 2, Engine 6.

## 1F — EXPANSION
**INPUT**
- ATR/range, candle range, volume when available, previous volatility, compression state.
**PROCESSING**
- Detect range/ATR/volume/momentum expansion and persistence.
**OUTPUT**
- `EXPANSION`, `NO_EXPANSION`, `EXPANSION_DIRECTION`, `EXPANSION_STRENGTH`.
**GATE**
- Insufficient expansion evidence => no expansion state.
**SCORE**
- Measures expansion strength and persistence.
**FILTER**
- Single-candle spike, no follow-through, abnormal data.
**EVIDENCE**
- Range, ATR, volume, momentum.
**DEPENDENCY**
- 1B, 1E.
**CONSUMER**
- 1G, Engine 2, Engine 4, Engine 6, Engine 7.

## 1G — TRANSITION
**INPUT**
- Previous/current market states, volatility, structure, compression/expansion.
**PROCESSING**
- Detect state change, identify FROM/TO, assess stability, detect false transition.
**OUTPUT**
- `TRANSITION`, `TRANSITION_FROM`, `TRANSITION_TO`, `TRANSITION_CONFIDENCE`.
**GATE**
- Unclear state change => no transition.
**SCORE**
- Measures confidence of state transition.
**FILTER**
- Single-candle state flip, conflicting evidence, low confidence.
**EVIDENCE**
- State history, structure change, volatility change.
**DEPENDENCY**
- 1A–1F.
**CONSUMER**
- Engine 2, Engine 3, Engine 6, Engine 9.

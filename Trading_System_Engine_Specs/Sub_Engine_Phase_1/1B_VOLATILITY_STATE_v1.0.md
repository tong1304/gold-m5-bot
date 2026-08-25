# 1B Volatility State

## 1. INPUT
- Closed OHLC candles and ATR/true-range series from the permitted lookback.

## 2. PROCESSING
- Measure current volatility relative to its historical baseline.
- Classify NORMAL, LOW, HIGH or UNSTABLE without forecasting future values.

## 3. OUTPUT
- Volatility state, normalized volatility evidence and quality/confidence metadata.

## 4. GATE
- FAIL only when volatility inputs are unavailable or structurally invalid.
- Does not authorize or reject BUY/SELL by itself.

## 5. SCORE
- Optional 0-100 state-quality score reflecting measurement stability and sample sufficiency.

## 6. TRACEABILITY
- Store ATR method, lookback, reference baseline, candle timestamp, state, score and reason codes.
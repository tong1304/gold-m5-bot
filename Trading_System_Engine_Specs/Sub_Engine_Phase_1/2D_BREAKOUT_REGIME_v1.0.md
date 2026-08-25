# 2D Breakout Regime

## 1. INPUT
- Range boundaries, volatility state, closed-candle prices and structure evidence.

## 2. PROCESSING
- Determine whether the market environment supports a breakout regime based on boundary escape and expansion context.

## 3. OUTPUT
- Breakout-regime state, boundary evidence, expansion evidence and confidence.

## 4. GATE
- FAIL when boundary or volatility evidence is invalid.
- Does not itself approve a breakout trade.

## 5. SCORE
- 0-100 regime-quality score based on boundary clarity and expansion support.

## 6. TRACEABILITY
- Record boundary source, candle timestamp, inputs, result, score and reason codes.
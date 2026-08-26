# ENGINE 01 — MARKET STATE BRAIN v2.0

## PURPOSE
Determine what the market is doing now before asking whether a trade exists. This engine describes state; it never authorizes or rejects a trade.

## SUB-ENGINES
1A Data Quality · 1B Volatility State · 1C Trend State · 1D Range State · 1E Compression · 1F Expansion · 1G Transition

## INPUT
M5 OHLCV, timestamps, symbol/timeframe, permitted higher-timeframe context (M15/H1), provider metadata, and prior-candle history.

## PROCESSING
Each sub-engine independently analyzes its domain. E1 reconciles the evidence into a market-state thesis: TREND_UP, TREND_DOWN, RANGE, COMPRESSION, EXPANSION, TRANSITION, or UNCLEAR. Conflicting evidence is preserved rather than hidden.

## OUTPUT
market_state, trend_state, volatility_state, range_state, compression_state, expansion_state, transition_state, evidence[], conflicts[], confidence 0–100, observations[], reasoning_trace.

## GATE
NONE. E1 never blocks E2 and never decides BUY/SELL. Data problems are reported as evidence and confidence degradation; only genuinely incomplete analysis is marked INCOMPLETE.

## SCORE
Confidence expresses how strongly the evidence supports the state. It is not a trading score and cannot authorize execution.

## TRACEABILITY
Record all sub-engine observations, candle-close timestamp, lookbacks, input versions, conflicts, confidence and conclusion.

## DECISION BOUNDARY
Market-state analysis only.

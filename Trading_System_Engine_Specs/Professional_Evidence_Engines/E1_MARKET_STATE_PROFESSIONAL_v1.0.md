# E1 — MARKET STATE BRAIN — Professional Evidence Specification v1.0

## Role
E1 is the first reasoning brain. It does not search for BUY/SELL and does not decide whether a trade is allowed. Its only job is to determine what the market is doing now and describe the opportunity environment for E2.

## Core Question
> What state is the market currently in, what is changing, and what type of opportunity environment does that create?

## Inputs
- M5 OHLCV closed candles — primary execution-state data.
- M15 OHLCV closed candles — immediate context.
- H1 OHLCV closed candles — higher-timeframe context.
- ATR(14) on M5/M15/H1.
- EMA20/EMA50 on M5/M15/H1.
- Recent swing highs/lows.
- Candle body/range and volatility history.
- No cross-asset signal or strategy is permitted as an input.

## Processing
E1 evaluates five independent dimensions:

1. **Trend State** — directional alignment, slope, persistence and structural progression.
2. **Range State** — balance, repeated rejection and absence of directional expansion.
3. **Compression** — contraction of realized range/ATR relative to recent baseline.
4. **Expansion** — abnormal range/ATR expansion relative to recent baseline.
5. **Transition** — evidence that the market is moving from one state to another; transition takes precedence over blindly labeling the market as trend/range.

Higher timeframes provide context, not an automatic directional command. M5 remains the current execution-state timeframe.

## State Vocabulary
- TREND_UP
- TREND_DOWN
- RANGE
- COMPRESSION
- EXPANSION
- TRANSITION
- UNCLEAR

Exactly one primary state is returned, with secondary observations when useful.

## Professional Reasoning Rules
- Do not equate EMA alignment with a trend by itself.
- Do not label a breakout merely because one candle is large.
- Do not label compression solely from one ATR reading.
- A state must be supported by multiple observations over a lookback window.
- Conflicting evidence is reported explicitly rather than forced into PASS/FAIL.
- E1 may conclude that the state is UNCLEAR. This is a valid analytical conclusion.
- E1 never emits BUY, SELL, ENTRY, or execution authorization.

## Output
```text
engine: E1
question: What state is the market currently in?
conclusion: <state>
confidence: 0-100
observations: [...]
evidence:
  trend:
  range:
  compression:
  expansion:
  transition:
  mtf_context:
  volatility:
  structure:
opportunity_environment: <description>
uncertainties: [...]
```

## Confidence
Confidence represents confidence in the market-state classification only. It is not probability of a profitable trade and must not be used as a direct entry score.

## Handoff to E2
E2 receives the complete E1 evidence record and asks:
> Given this market state, what opportunity/playbook is actually available?

E1 must not tell E2 which trade to take. It provides the market-state evidence from which E2 reasons independently.

## Asset Separation
GOLD and BTC use the same reasoning framework but their market data remain isolated. No asset may borrow another asset's signal, setup, fallback, or directional conclusion.

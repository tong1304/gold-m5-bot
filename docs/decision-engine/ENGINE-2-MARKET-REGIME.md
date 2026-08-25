# ENGINE 2 — MARKET REGIME

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 2A — TREND REGIME
**INPUT**
- Trend State, trend strength, structure, volatility, transition.
**PROCESSING**
- Translate Trend State into a trading regime; assess persistence and maturity.
**OUTPUT**
- `TREND_REGIME`, `TREND_DIRECTION`, `REGIME_STRENGTH`.
**GATE**
- Insufficient trend evidence => no Trend Regime.
**SCORE**
- Measures Trend Regime strength.
**FILTER**
- Late/weak trend, conflicting structure.
**EVIDENCE**
- 1C, structure, volatility, transition.
**DEPENDENCY**
- 1C, 1B, 1G.
**CONSUMER**
- Engine 6, Engine 9.

## 2B — RANGE REGIME
**INPUT**
- Range State, range strength, volatility, structure, location.
**PROCESSING**
- Determine whether the range supports mean-reversion; assess boundary persistence.
**OUTPUT**
- `RANGE_REGIME`, `RANGE_DIRECTIONAL_BIAS`, `REGIME_STRENGTH`.
**GATE**
- Unclear range => no Range Regime.
**SCORE**
- Measures range quality.
**FILTER**
- Breakout conditions, volatility expansion, unstable boundaries.
**EVIDENCE**
- Range boundaries, containment, volatility.
**DEPENDENCY**
- 1D, 1B, 1G.
**CONSUMER**
- Engine 6, Engine 9.

## 2C — MEAN-REVERSION
**INPUT**
- Range Regime, value/equilibrium, location, volatility, liquidity.
**PROCESSING**
- Measure deviation from equilibrium, return-to-mean potential, rejection/acceptance.
**OUTPUT**
- `MR_FAVORABLE`, `MR_UNFAVORABLE`, `MR_DIRECTION`, `MR_QUALITY`.
**GATE**
- No reliable range/equilibrium => STOP.
**SCORE**
- Measures suitability for mean-reversion.
**FILTER**
- Strong trend, breakout expansion, extreme volatility.
**EVIDENCE**
- Mean distance, range boundaries, rejection.
**DEPENDENCY**
- 2B, Engine 5, Engine 4.
**CONSUMER**
- Engine 6.

## 2D — BREAKOUT REGIME
**INPUT**
- Compression, expansion, range, structure, volatility, liquidity.
**PROCESSING**
- Assess breakout environment, expansion after compression, breakout persistence.
**OUTPUT**
- `BREAKOUT_REGIME`, `BREAKOUT_DIRECTION`, `BREAKOUT_QUALITY`.
**GATE**
- No valid expansion/breakout context => STOP.
**SCORE**
- Measures breakout-environment quality.
**FILTER**
- Fake expansion, weak liquidity, immediate rejection.
**EVIDENCE**
- Compression, expansion, range boundary, structure.
**DEPENDENCY**
- 1D, 1E, 1F, Engine 3, Engine 4.
**CONSUMER**
- Engine 6.

## 2E — REGIME PHASE
**INPUT**
- Trend, range, mean-reversion, breakout regimes, transition.
**PROCESSING**
- Classify regime phase as early/mature/late/transition and assess stability.
**OUTPUT**
- `EARLY`, `MATURE`, `LATE`, `TRANSITION`, `REGIME_PHASE_CONFIDENCE`.
**GATE**
- High regime conflict => `NO_REGIME`.
**SCORE**
- Measures regime-phase clarity.
**FILTER**
- Late regime, conflicting regimes.
**EVIDENCE**
- Regime history, transition, structure.
**DEPENDENCY**
- 2A–2D, 1G.
**CONSUMER**
- Engine 5, Engine 6, Engine 9.

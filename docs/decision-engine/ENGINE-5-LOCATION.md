# ENGINE 5 — LOCATION

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 5A — VALUE / EQUILIBRIUM
**INPUT**
- Price, range, VWAP/mean features, historical distribution.
**PROCESSING**
- Determine equilibrium and price deviation; classify above/at/below value.
**OUTPUT**
- `ABOVE_VALUE`, `AT_VALUE`, `BELOW_VALUE`, `VALUE_DISTANCE`.
**GATE**
- Unreliable equilibrium => Neutral.
**SCORE**
- Measures location clarity.
**FILTER**
- Unstable mean, extreme volatility.
**EVIDENCE**
- Mean/VWAP, range midpoint, price distribution.
**DEPENDENCY**
- 1B, 1D.
**CONSUMER**
- Engine 2C, Engine 6, Engine 8.

## 5B — STRUCTURAL LOCATION
**INPUT**
- Structure, swing levels, BOS, current price.
**PROCESSING**
- Determine price position relative to structural support/resistance/middle.
**OUTPUT**
- `STRUCTURAL_SUPPORT`, `STRUCTURAL_RESISTANCE`, `STRUCTURAL_MIDDLE`, `STRUCTURAL_DISTANCE`.
**GATE**
- Unclear structure => Neutral.
**SCORE**
- Measures structural-location significance.
**FILTER**
- Mid-structure congestion, no structural edge.
**EVIDENCE**
- Swing, BOS, structure level.
**DEPENDENCY**
- Engine 3.
**CONSUMER**
- Engine 6, Engine 8, Engine 9.

## 5C — LIQUIDITY LOCATION
**INPUT**
- Liquidity zones, current price, sweep/reclaim state.
**PROCESSING**
- Measure distance to liquidity; classify near/far and target availability.
**OUTPUT**
- `NEAR_LIQUIDITY`, `FAR_LIQUIDITY`, `NO_CLEAR_LIQUIDITY`, `LIQUIDITY_DISTANCE`.
**GATE**
- No liquidity reference => target confidence is low.
**SCORE**
- Measures liquidity-location quality.
**FILTER**
- Consumed liquidity, target too close.
**EVIDENCE**
- Liquidity zone and price distance.
**DEPENDENCY**
- Engine 4.
**CONSUMER**
- Engine 6, Engine 8.

## 5D — EXTENSION
**INPUT**
- Price, equilibrium, ATR/volatility, range, structure.
**PROCESSING**
- Measure mean/structure distance relative to volatility and classify extension.
**OUTPUT**
- `NORMAL`, `EXTENDED`, `EXTREME_EXTENSION`, `EXTENSION_LEVEL`.
**GATE**
- Missing reference => no valid extension assessment.
**SCORE**
- Measures price extension.
**FILTER**
- Extreme extension for continuation without confirmation.
**EVIDENCE**
- ATR distance, mean distance, structure distance.
**DEPENDENCY**
- 1B, Engine 3, 5A.
**CONSUMER**
- Engine 6, Engine 7, Engine 8, Engine 9.

## 5E — CONGESTION / SPACE
**INPUT**
- Price, structure, liquidity, range, ATR/volatility.
**PROCESSING**
- Measure free space to target and density of opposing levels.
**OUTPUT**
- `OPEN_SPACE`, `LIMITED_SPACE`, `CONGESTED`, `SPACE_SCORE`.
**GATE**
- No sufficient space for valid risk/reward => STOP.
**SCORE**
- Measures usable price space.
**FILTER**
- Nearby opposing level, tight congestion.
**EVIDENCE**
- Structural levels, liquidity, ATR distance.
**DEPENDENCY**
- Engine 3, Engine 4, 5B, 5C.
**CONSUMER**
- Engine 6, Engine 8, Engine 9.

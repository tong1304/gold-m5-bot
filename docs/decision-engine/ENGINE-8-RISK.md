# ENGINE 8 — RISK

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 8A — INVALIDATION
**INPUT**
- Setup invalidation, structure, entry, market context, price.
**PROCESSING**
- Define risk premise, distinguish structural invalidation from setup invalidation, test stop feasibility.
**OUTPUT**
- `RISK_INVALIDATION_LEVEL`, `RISK_VALID`, `RISK_INVALID`.
**GATE**
- No logical invalidation level => STOP.
**SCORE**
- Measures quality of risk premise.
**FILTER**
- Stop without structural basis, excessive risk distance.
**EVIDENCE**
- Structure, setup premise, liquidity.
**DEPENDENCY**
- 6D, Engines 3–5.
**CONSUMER**
- 8B, 8D, Engine 9E.

Boundary: 8A defines the risk boundary; 6D owns setup validity.

## 8B — STOP PLACEMENT
**INPUT**
- Risk invalidation, entry, ATR/volatility, structure, liquidity.
**PROCESSING**
- Determine logical stop, buffer, stop distance and volatility compatibility.
**OUTPUT**
- `STOP_PRICE`, `STOP_DISTANCE`, `STOP_VALID`.
**GATE**
- Stop cannot protect the premise or exceeds policy => STOP.
**SCORE**
- Measures stop-placement quality.
**FILTER**
- Too tight, too wide, inside noise.
**EVIDENCE**
- Structural level, ATR, liquidity.
**DEPENDENCY**
- 8A, 1B, Engine 3, Engine 4.
**CONSUMER**
- 8D, 8E, Engine 9E.

## 8C — TARGET / LIQUIDITY
**INPUT**
- Entry, liquidity zones, structure, location, space, stop.
**PROCESSING**
- Generate target candidates, prioritize liquidity targets, measure distance and space.
**OUTPUT**
- `TARGET_PRICE`, `TARGET_TYPE`, `TARGET_DISTANCE`, `TARGET_VALID`.
**GATE**
- No valid target => STOP.
**SCORE**
- Measures target quality.
**FILTER**
- Target too close, opposing liquidity before target, insufficient space.
**EVIDENCE**
- Liquidity, structure, space.
**DEPENDENCY**
- Engine 4, Engine 5, 8B.
**CONSUMER**
- 8D, Engine 9E.

## 8D — R-MULTIPLE
**INPUT**
- Entry, stop, target.
**PROCESSING**
- Calculate potential R/R and compare with policy.
**OUTPUT**
- `R_MULTIPLE`, `RR_VALID`, `RR_REJECTION_REASON`.
**GATE**
- R/R below policy minimum => STOP.
**SCORE**
- Measures risk/reward attractiveness.
**FILTER**
- Poor R/R, unrealistic target.
**EVIDENCE**
- Entry, SL, TP.
**DEPENDENCY**
- 8B, 8C.
**CONSUMER**
- 8E, Engine 9E.

## 8E — POSITION SIZE
**INPUT**
- Account risk budget, entry, stop distance, instrument specification, contract/point value.
**PROCESSING**
- Calculate monetary risk and position size; validate rounding and instrument constraints.
**OUTPUT**
- `POSITION_SIZE`, `EXPECTED_RISK`, `SIZE_VALID`.
**GATE**
- Size cannot respect risk policy => STOP.
**SCORE**
- Deterministic calculation; quality score not required.
**FILTER**
- Excessive size, invalid contract size, minimum-lot violation.
**EVIDENCE**
- Risk budget, stop distance, instrument specification.
**DEPENDENCY**
- 8B and account/risk configuration.
**CONSUMER**
- 8F, Engine 9E.

## 8F — EXPOSURE LIMITS
**INPUT**
- Position size, existing exposure, symbol exposure, portfolio exposure, risk budget.
**PROCESSING**
- Check aggregate exposure, concurrent positions, daily/session risk usage.
**OUTPUT**
- `EXPOSURE_VALID`, `EXPOSURE_LIMITED`, `EXPOSURE_REJECTED`.
**GATE**
- Exposure above policy => STOP.
**SCORE**
- Hard constraint; no quality score required.
**FILTER**
- Overexposure, duplicate risk, exhausted risk budget.
**EVIDENCE**
- Current positions, risk usage, exposure limits.
**DEPENDENCY**
- 8E and account/portfolio state.
**CONSUMER**
- Engine 9E.

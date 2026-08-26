# E9 Adaptive Professional Learning Design

## Goal
Turn E9 into an evidence-based decision brain that records each decision snapshot, evaluates the realized M5 outcome after a fixed horizon, and learns statistics about evidence combinations without changing live rules automatically.

## Architecture
E1-E8 remain parallel specialist analysts. E9 consumes their evidence package and produces a decision snapshot containing asset, timestamp, direction, thesis quality, evidence dimensions, conflict state, and risk/economics metadata. A delayed outcome evaluator examines future closed candles and records MFE, MAE, R outcome, and terminal outcome. A learning store aggregates results by asset, regime, direction, setup archetype, and evidence signature. Calibration is read-only for live execution: it produces evidence-quality statistics that E9 can consume on later decisions, while never mutating thresholds autonomously.

## Learning contract
1. Every E9 decision is immutable once recorded.
2. Outcome evaluation begins only after the required future M5 candles exist.
3. No look-ahead data may enter the original decision snapshot.
4. GOLD and BTC statistics are isolated; no cross-asset learning is mixed.
5. Statistics are segmented by regime and direction when enough samples exist.
6. Small samples are reported as low confidence and cannot override core evidence.
7. Learning is advisory/calibration evidence, not an E1-E8 gate.
8. Live order execution remains unchanged by this feature.

## Outcome model
For a decision with entry, invalidation and target:
- WIN: target reached before invalidation.
- LOSS: invalidation reached before target.
- TIMEOUT: neither reached within the configured horizon.
- UNRESOLVED: insufficient future candles or invalid trade geometry.

Record MFE, MAE, realized R, bars-to-resolution, and outcome. When both target and invalidation occur inside the same candle and intrabar ordering is unavailable, mark the sample AMBIGUOUS rather than inventing ordering.

## Evidence signature
The signature is a deterministic, compact representation of the E9 evidence dimensions: market state, opportunity/regime, structure, liquidity, location, setup archetype/maturity, confirmation, direction, and economics quality. It is used for aggregation only and does not become a hard-coded trigger.

## Calibration
For each segment/signature with a minimum sample count, calculate sample count, win rate, average R, expectancy R, average MFE, average MAE, timeout rate, and Wilson-style confidence bounds for win rate. E9 may use these as contextual historical evidence, weighted down when sample count is small. Calibration data must never be trained on outcomes occurring after the current decision timestamp.

## Safety
The feature is passive by default. No automatic strategy mutation, threshold rewriting, position sizing mutation, or live-order enablement is allowed. All learning records are auditable and versioned with the E9 architecture version.

## Success criteria
- Decisions can be persisted without blocking the live scanner.
- Outcomes are evaluated only when future data is available.
- GOLD/BTC learning remains isolated.
- Duplicate decisions do not create duplicate learning samples.
- E9 receives historical calibration evidence but remains the sole final decision authority.

# Multi-Strategy Regime Filters Design

**Date:** 2026-08-24  
**Repository:** `tong1304/gold-m5-bot`  
**Engine:** V11.1-HARDENED

## Goal

Improve the live/replay quality of each independent strategy by making entry conditions strategy-specific and regime-aware, while preserving the existing structure-first risk engine and avoiding weighted confluence.

## Current Findings

- BTC and GOLD both currently use the same `v11/strategies/multi_strategy.py` registry through their symbol-specific `__init__.py` files.
- `TREND_PULLBACK` already requires M15 direction alignment, EMA structure, a recent EMA touch, and a confirming candle.
- `LIQUIDITY_SWEEP` currently checks only a 20-bar swing sweep/reclaim and candle body direction; it does not reject strong continuation regimes.
- `OPENING_RANGE_BREAKOUT` currently uses the first six bars of the available UTC day and a body threshold, but has no compression, breakout-extension, or post-breakout quality filter.
- `VWAP_MEAN_REVERSION` rejects non-neutral M15 trend and uses a fixed 1.8 ATR deviation, but does not distinguish weak/strong range conditions or require a meaningful rejection wick.
- `TREND_PULLBACK` and `VWAP_MEAN_REVERSION` were both poor in the supplied 2026-08-23 replay sample, while `LIQUIDITY_SWEEP` and `TREND_PULLBACK` showed different behavior in the earlier sample. The sample is too small to optimize thresholds directly.
- `v11/engine.py` evaluates every registry strategy, then `selection.py` ranks passing candidates by quality/freshness/RR. This ranking is retained; no weighted confluence is introduced.
- The latest risk commits enforce structure-first SL and nearest-structure RR validation. That risk contract must remain unchanged.

## Design

### 1. Regime context

Add a small deterministic market-regime context derived from existing M5/M15 OHLC data. It must expose descriptive fields rather than a weighted score:

- M15 trend direction and trend strength proxy
- M5 ATR and normalized recent range
- M5 compression/expansion proxy
- distance from VWAP in ATR units
- recent candle body/wick quality
- nearby opposing structure distance in ATR units

The context is diagnostic and gating only. It must not produce a composite confluence score.

### 2. Strategy-specific gates

#### LIQUIDITY_SWEEP

Require:
- actual sweep beyond a prior swing level;
- reclaim back through the swept level;
- rejection/close quality in the reversal direction;
- no immediate strong continuation condition against the reversal;
- sufficient space for the risk engine's first structure target.

#### TREND_PULLBACK

Require:
- M15 and M5 direction agreement;
- ordered EMA trend structure;
- recent pullback into/near EMA20 or equivalent trend value area;
- continuation candle with meaningful body;
- no nearby opposing structure that makes the trade structurally unattractive.

#### VWAP_MEAN_REVERSION

Require:
- neutral/range M15 regime;
- sufficiently large VWAP deviation relative to ATR;
- rejection back toward VWAP, not merely a directional candle far from VWAP;
- no strong trend continuation signature;
- reject if the entry is too close to an adverse structural level.

#### OPENING_RANGE_BREAKOUT

Require:
- a valid opening range with measurable compression;
- close outside the range in the intended direction;
- breakout body/close quality rather than wick-only penetration;
- avoid entries after excessive extension from the breakout level;
- enough structural room for the risk engine's first target.

#### MSS_PULLBACK / other registered strategies

Keep their independent contracts intact initially. Add only shared regime diagnostics needed by the selection/risk path; do not silently convert them into confluence strategies.

### 3. Selection behavior

Keep `selection.select()` deterministic and non-weighted. A candidate passes or fails its own strategy contract. Among passing candidates in an eligible direction, the existing quality/freshness/RR ordering remains the final selector.

### 4. Risk behavior

Do not change `v11/risk.py` in this feature. Preserve:

- structure-first stop loss;
- nearest valid structure TP1;
- minimum RR validation;
- no synthetic skipping of the first structure target.

### 5. Replay/statistics

Replay output must retain strategy identity and expose enough evidence to compare before/after behavior. The statistics page should continue showing only actual BUY/SELL trades and existing strategy statistics. No fake trades should be generated to increase sample size.

## Anti-overfitting rules

- Do not tune thresholds against only 2026-08-23.
- Prefer normalized ATR/structure measures over absolute BTC/GOLD price values.
- Do not optimize for win rate alone; evaluate Net R, expectancy, profit factor, max drawdown, trade count, and strategy-level consistency.
- A strategy may remain disabled/NO_TRADE in regimes where its edge is unsupported.
- No guarantee of profitability is claimed.

## Testing / Acceptance

Unit tests must cover every new gate with positive and negative fixtures. Existing V11 tests must continue to pass. Replay/regression checks must verify that:

1. weighted confluence is still absent;
2. risk/SL/TP logic is unchanged;
3. strategy names and trade-history schema remain compatible;
4. poor-quality trend/reversion/breakout/sweep setups are rejected;
5. valid examples still pass;
6. output remains JSON-safe and deployable under the existing Flask/Gunicorn service.

# Structure V6 Trading Engine Design

## Goal
Replace the pattern-score entry model with a structure/location/liquidity/confirmation/pullback model for BTC and GOLD, while preserving the statistics UI and historical replay workflow.

## Core decision flow
1. H1 establishes directional structure: bullish, bearish, or neutral.
2. M15 identifies actionable location: demand/discount for BUY or supply/premium for SELL, with nearby liquidity.
3. M5 must first show a liquidity sweep in the intended direction.
4. M5 must then confirm with a market-structure shift (MSS/BOS) in the intended direction.
5. Entry is only allowed on a pullback/retest after confirmation; chasing the displacement candle is rejected.
6. SL is placed beyond the invalidating swing/liquidity point plus a small volatility buffer.
7. TP targets the next opposing liquidity/structure level and must provide at least 2.0 effective R after execution costs.
8. One active setup produces one signal; duplicate signals from the same structure are suppressed.
9. Any contradictory H1/M15 structure, missing sweep, missing MSS/BOS, invalid pullback, insufficient RR, or excessive volatility produces NO_TRADE.

## Important anti-lookahead rule
Historical replay may only use candles that were closed at the decision timestamp. Pivot/structure confirmation must never inspect future candles. Future candles are used only after the signal to resolve WIN/LOSS/OPEN.

## Outputs
Each signal records: structure bias, M15 location, liquidity event, M5 trigger, entry reason, invalidation level, target liquidity, entry/SL/TP, RR, and rejection reasons when no trade is produced. The existing statistics page continues to expose pattern/evidence fields for backward compatibility, but V6 fields are added to payloads.

## Safety
Live orders remain disabled. The engine only emits signals and records outcomes. The replay uses real LSE historical OHLCV and does not send Telegram alerts in dry-run mode.

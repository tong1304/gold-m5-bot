# V11 Strategy Architecture Design

## Goal
Replace the V10.3 monolithic multi-strategy decision path with a V11 pipeline where each asset has its own approved strategy set and each strategy owns the M5 setup rules it actually needs.

## Decision pipeline
1. **M5 setup detection** — evaluate closed M5 data with strategy-specific lookbacks. BTC and GOLD use separate strategy registries.
2. **Strategy-specific validation** — only the selected strategy's required filters are evaluated. The global Candle Confirmation filter is removed. Available validators include Body/Wick, Momentum, ATR, Structure Break, Retest, Liquidity/SR and other strategy-specific conditions.
3. **M15 trend** — determine the higher-timeframe BUY/SELL direction. M15 is context, not an entry trigger.
4. **Alignment + levels** — require M5 strategy direction to match M15 trend, then calculate SL/TP with target RR 1:2. Reject invalid/inverted/unsafe levels.
5. **Signal** — only a fully valid setup is persisted and sent to Telegram. NO_TRADE remains persisted for replay/statistics diagnostics.

## Strategy separation
BTC retains the high-rated set from V10.3: TREND_PULLBACK, BREAKOUT_RETEST, RANGE_BREAKOUT, MOMENTUM, VOLATILITY_BREAKOUT.
GOLD retains the high-rated set: TREND_PULLBACK, BREAKOUT_RETEST, EMA_PULLBACK, LIQUIDITY_SWEEP, SR_REVERSAL, VOLATILITY_BREAKOUT.

Each strategy module exposes one deterministic `evaluate(m5, direction, context)` interface and returns a structured result containing status, direction, reasons, and evidence. No strategy may silently inherit filters from another strategy.

## Timeframes and history
M5 is the entry/setup timeframe. M15 is the trend timeframe. Replay continues to accept Bangkok calendar dates, obtains real historical LSE OHLCV, applies warm-up before the selected dates, and evaluates every closed M5 candle in the requested date range. The engine used by replay and live scanning is the same V11 engine.

## Risk
The default V11 target is RR 1:2. A signal is not valid if SL/TP direction is inverted, risk is zero, or effective RR is below 2.0. Existing spread/slippage/risk guards remain active after strategy validation.

## Compatibility
V11 keeps the existing `/signal`, `/scheduler/status`, `/replay`, `/statistics` surfaces. Responses gain `engine_version=11.0-M5-M15-STRATEGY-SPLIT`, strategy evidence, M5 direction, M15 trend, entry, SL, TP and RR fields. Existing history records remain readable.

## Safety
Live orders remain disabled. Telegram is notification-only. Replay must never send Telegram alerts.

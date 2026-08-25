# 9-Engine Telegram and Statistics Implementation Plan

**Goal:** Make production-v2 Telegram notifications Thai-first, limited to startup/status/trade/critical events, add 15-minute status reporting, and replace the legacy statistics endpoint with 9-Engine statistics.

**Architecture:** `production_v2` remains the only production runtime. Telegram is a presentation layer fed by E9 decisions and system status; it never emits NO_TRADE/internal engine progress. Statistics are derived from production-v2 state only.

**Global constraints:**
- V11/V12 are archive-only and must not be imported, executed, used as fallback, or used as Telegram/statistics sources.
- Telegram prose is Thai except technical/proper terms such as BUY, SELL, BTC, GOLD, M5, E1-E9, LSE, API, RSI, ATR, EMA, VWAP, RR, Telegram.
- Notifications are STARTUP once, STATUS every 15 minutes, TRADE only for actionable E9 BUY/SELL, and CRITICAL for serious failures.
- No NO_TRADE, WAIT, setup/gate/score failure, engine debug, or per-candle internal notifications.
- E9 is the sole decision authority.

## Tasks

1. **Tests first:** Extend `tests/test_production_v2_telegram.py` and runtime/API tests for Thai-first text, startup/status/critical formatters, actionable-only trades, 15-minute status cadence, and `/api/statistics` plus `/statistics`.
2. **Telegram:** Update `production_v2/notifications/telegram.py` with Thai-first `format_startup`, `format_decision`, `format_status`, `format_critical`; preserve technical terms; reject legacy V11/V12 strings; suppress non-actionable decisions.
3. **Scheduler:** Update `production_v2/service.py` with 900-second status cadence independent of candle scanning, startup once, actionable trade notifications only, and throttled critical notifications.
4. **Statistics:** Add `production_v2/statistics.py` and endpoints in `production_v2/app.py` for 9-Engine-only statistics. `/api/statistics` must stop returning 404 and `/statistics` must not depend on legacy APIs.
5. **Verification:** Run production-v2 tests, verify no V11/V12 runtime imports, commit, wait for CI PASS, then verify Render `/health`, `/api/statistics`, and Telegram behavior before declaring deployment complete.

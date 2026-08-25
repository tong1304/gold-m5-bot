# No Cross-Asset Strategy Architecture Design

## Goal
Make GOLD and BTC strategy selection fully asset-local. A signal for one asset must never be created by evaluating another asset's strategy, regime compatibility, score, or fallback path.

## Current issue
The V12 engine explicitly imports and calls `evaluate_cross_asset_fallback()`. When the target asset has no native regime-compatible strategy, the engine evaluates the other asset's strategies against the target asset's M5 data. The response also exposes `CROSS_ASSET` mode and source-asset metadata.

## Design

### Asset isolation
- GOLD analysis may evaluate only G1/G2/G3.
- BTC analysis may evaluate only B1/B2/B3.
- Native strategy selection remains regime-aware within the target asset.
- `PASS/GATE`, `SCORE`, `FILTER`, setup state, RR validation, and signal emission remain inside the target asset pipeline.
- No target-asset decision may depend on the other asset.

### Fallback policy
Cross-asset fallback is removed from the live decision path. If no native strategy passes, the result is `NO_TRADE`; the system does not borrow a strategy from the other asset.

### Shared infrastructure
Common utilities such as regime classification, scoring primitives, risk validation, notifications, statistics, and data-quality validation may remain shared because they operate on the target asset's own input. Shared code must not fetch or inspect the other asset to make a strategy decision.

### Observability
Responses use `strategy_mode="NATIVE"` when a native candidate is selected and `NONE` when no native candidate is selected. `source_asset` is the analyzed asset only; it is not an alternate strategy source. Cross-asset fallback metadata is removed from decision payloads.

### Compatibility
The old `v11/cross_asset_fallback.py` module is no longer part of the active architecture. Existing tests that assert cross-asset fallback behavior are replaced with isolation tests that prove only target-asset strategy IDs are eligible.

## Acceptance criteria
1. `engine.py` contains no import or call to cross-asset fallback.
2. `engine_gold.py` contains no import or call to cross-asset fallback.
3. BTC can never select G1/G2/G3.
4. GOLD can never select B1/B2/B3.
5. A regime with no native strategy returns `NO_TRADE`, not a cross-asset signal.
6. Payloads never report `strategy_mode="CROSS_ASSET"`.
7. Regression tests cover both assets and the no-native-strategy path.
8. Existing MTF H1→M15→M5, scoring, filters, setup-state, risk/RR, Telegram, and statistics behavior remains intact.

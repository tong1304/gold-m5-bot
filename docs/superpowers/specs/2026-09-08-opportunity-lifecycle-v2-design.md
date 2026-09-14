# Opportunity Lifecycle V2 Design

**Date:** 2026-09-08  
**Base:** `production-v2` at merge `215b6c3927a9a171c6d049721f753586085aa7d0`  
**Scope:** Opportunity continuity and downstream state semantics only.

## Goal

Make a detected opportunity behave as one persistent causal object across closed M5 candles, while preserving E9 as the only trade authority and preventing stale/late opportunities from becoming chase entries.

## Non-negotiable invariants

1. The same causal event keeps the same `opportunity_id` across candles.
2. E4 is the causal-event clock anchor. E2/E6 wording cannot re-anchor an existing event.
3. `PENDING`/repair is not failure. E4 follow-through can promote the same event later.
4. E6 thesis state persists independently from entry timing.
5. E7 confirmation state persists independently from thesis and can only become failed through explicit failed proof/invalidation.
6. Timing is price-relative as well as age-relative; elapsed bars alone cannot make an opportunity actionable or late.
7. E8 evaluates remaining economic edge only when its applicability contract is satisfied.
8. E9 may choose `WAIT`, `TRADE`, `TOO_LATE`, or `INVALID`, but may not erase upstream direction/setup/event evidence.
9. `WAIT` means a live opportunity exists but proof/economics/timing is incomplete. `NO_TRADE` means no live actionable opportunity is being presented.
10. No gate is bypassed and no new signal is created solely to increase trade count.

## Canonical lifecycle

```text
E4 EVENT
  -> WATCH
  -> THESIS
  -> CONFIRMING
  -> ACTIONABLE
  -> TRADE

Any live stage -> TOO_LATE when timing/edge decays without thesis invalidation.
Any live stage -> INVALIDATED when causal thesis/proof is explicitly broken.
Any live stage -> EXPIRED when lifecycle age policy expires it without a valid continuation.
```

`WAIT` is an E9 decision overlay, not a replacement for lifecycle stage. A `WATCH`, `THESIS`, or `CONFIRMING` opportunity can therefore produce `E9=WAIT` while retaining its canonical stage.

## Opportunity identity contract

Identity is derived from the stable tuple `(symbol, timeframe, direction, causal_event_id)` when a causal event exists. Setup wording may change as the event develops and must not alone create a new opportunity. A same-direction, genuinely new E4 event creates a successor with `previous_opportunity_id` pointing to the predecessor.

An active opportunity with a missing event field on a later observation must retain its previous event anchor rather than being recreated. Terminal states (`TRADE`, `INVALIDATED`, `EXPIRED`, `TOO_LATE`) cannot silently revive.

## E4 repair -> confirmation

E4 may expose `auction_state=PENDING` and a repair action when follow-through is absent. The repair layer must preserve `event_id`, `event_candle_id`, frozen event ATR, and causal anchor. On a later closed candle, explicit follow-through may promote the same event to confirmed/accepted without resetting opportunity age or identity.

No confirmation may be inferred merely from elapsed time.

## E6 thesis persistence

E6 owns causal thesis semantics. The record carries a meaningful thesis state such as `CONTESTED`, `VALIDATING`, or `PROVEN`, plus `missing_proof`. Placeholder values (`NONE`, `UNKNOWN`, `NO_SETUP`, empty strings) must not overwrite an existing meaningful thesis state. A new candle may add evidence or satisfy proof but must not erase the prior thesis solely because the current trigger is absent.

## E7 confirmation persistence

E7 owns setup-specific confirmation semantics. Confirmation follows `PENDING/DEVELOPING -> CONFIRMING -> CONFIRMED` only when closed-candle proof is present. Lack of a new trigger keeps the current pending/confirming state; explicit failed proof or invalidation moves the opportunity to `INVALIDATED` rather than silently resetting it.

## Price-relative timing

Timing consumes E4 anchor, opportunity age, current candle/price, execution zone, ATR/volatility, and confirmation timing. It produces:

- `timing_state`: `EARLY`, `ACTIVE`, `WARNING`, `TOO_LATE`, or `EXPIRED`
- `age_bars`
- `entry_window`
- `confirmation_lateness`
- `chase_prohibited`
- `edge_decay` / `edge_remaining`

The timing layer must compare current price to the valid execution zone and event-relative displacement. A young opportunity that has already traveled beyond its economic entry zone can be `TOO_LATE`; an older opportunity still inside a valid zone can remain `ACTIVE` subject to other gates.

The existing `OPPORTUNITY_TIMING_MEMBRANE_V5` remains the runtime integration point during migration; this work strengthens its contract rather than creating a competing timing brain.

## Edge remaining

E8 separates raw RR from remaining edge. Remaining edge must account for current entry location, valid stop/target geometry, available opposing space, execution cost, and the opportunity's timing/price displacement. The economic state vocabulary is:

- `NOT_READY` — economics cannot yet be trusted/evaluated.
- `VALID` — economic structure is valid but not necessarily immediately executable.
- `ACTIONABLE` — economics remain sufficiently favorable at current price.
- `DETERIORATING` — edge remains but is materially decaying.
- `TOO_LATE` — original thesis may remain valid but current price no longer offers sufficient edge.

`edge_remaining` is a normalized diagnostic value, not a replacement for hard risk gates.

## E9 authority and decision semantics

E9 consumes the canonical opportunity plus timing and economics. It is the sole authorization boundary. It must expose upstream `direction`, `setup`, `opportunity_id`, `event_id`, and lifecycle stage when available, even for `WAIT` or `TOO_LATE`.

Decision semantics:

- `TRADE`: all required hard gates and economics are satisfied.
- `WAIT`: a live opportunity exists, but confirmation/thesis/timing/economics is incomplete.
- `TOO_LATE`: the opportunity remains causally identifiable but current edge is gone or chase is prohibited.
- `INVALID`: the opportunity's causal thesis is explicitly broken.
- `NO_TRADE`: no live opportunity is available for action; it is not a synonym for every blocked setup.

E9 must not mutate upstream evidence to force a decision.

## Continuity test scenarios

The implementation must prove at minimum:

1. `08:40 E4 event -> 08:45 watch -> 08:50 watch/confirming -> 08:55 confirming` preserves one opportunity ID.
2. E4 `PENDING/REPAIR` at `08:45` followed by valid follow-through at `08:50` preserves the `08:40` event anchor and age.
3. E6 `CONTESTED/VALIDATING` persists when E7 has no new trigger.
4. E7 `CONFIRMING` persists until explicit confirmation or invalidation.
5. Price moves outside the execution zone while age remains low -> `TOO_LATE`/`chase_prohibited`, not `TRADE`.
6. An older opportunity remains eligible for `ACTIVE` timing when price remains inside the valid zone and other gates are satisfied.
7. E8 does not run as actionable economics while E6 thesis is unresolved.
8. E9 reports a known setup/event for `WAIT` instead of `UNKNOWN`.
9. `WAIT` and `NO_TRADE` are distinguishable in pipeline state/log output.
10. A genuinely new causal E4 event creates a new opportunity ID and links the predecessor.
11. Terminal opportunities do not silently revive.
12. BUY and SELL opportunities can be tracked independently; leadership does not destroy the counter-direction watch.

## Regression constraints

Existing Opportunity Core V1, Opportunity Book, E6 lifecycle authority, watch semantics, service reasoning, and production-v2 test contracts must remain green. The change should prefer additive boundary contracts and focused compatibility wrappers over rewriting the large legacy lifecycle module.

## Out of scope

- Automatic broker order execution.
- Strategy proliferation or lowering signal thresholds.
- Replacing E1-E8 specialist roles.
- Removing existing surgery layers before replay/regression proves a replacement is safe.
- Changing the closed-candle-only rule.

# Opportunity Lifecycle V2 Implementation Plan

**Date:** 2026-09-08  
**Base:** `production-v2` merge `215b6c3927a9a171c6d049721f753586085aa7d0`  
**Working branch:** `architecture/opportunity-lifecycle-v2`  
**Design:** `docs/superpowers/specs/2026-09-08-opportunity-lifecycle-v2-design.md`

## Objective

Implement the approved Opportunity Lifecycle V2 design using TDD. Preserve the existing E1-E9 role boundaries, closed-candle-only behavior, manual execution boundary, E9-only authorization, and existing surgery/compatibility layers unless a focused replacement is proven by regression.

## Working rules

- RED before production code: each behavior starts with a failing focused test.
- GREEN: implement the smallest boundary change that satisfies the test.
- REFACTOR only after the relevant tests are green.
- Do not lower signal gates or create signals solely to increase trade count.
- Do not bypass E8 economics or E9 authority.
- Do not rewrite `opportunity_lifecycle.py` wholesale.
- Preserve compatibility fields while adding canonical fields.

## Task 1 — Opportunity identity continuity

**Tests first:** add focused tests for:
- same E4 event across multiple closed M5 candles keeps the same `opportunity_id`;
- setup wording changing from `OPPORTUNITY_WATCH` to a concrete setup does not create a new ID;
- missing event fields on a later observation preserve the prior causal anchor and ID;
- a genuinely new E4 event creates a successor ID with `previous_opportunity_id`;
- terminal opportunity does not silently revive.

**Implementation:** strengthen the lifecycle identity boundary around `advance_opportunity` / directional lifecycle mapping. Identity should prefer `(symbol, timeframe, direction, causal_event_id)` and preserve the prior event anchor through wording/data gaps.

**Acceptance:** replayed 08:40→08:45→08:50→08:55 lifecycle contains one ID until a genuinely new event occurs.

## Task 2 — E4 repair to confirmation

**Tests first:**
- `PENDING + REPAIR + FOLLOW_THROUGH_ABSENT` preserves event ID, event candle, frozen ATR, and anchor;
- later explicit follow-through promotes the same event without resetting age;
- elapsed time alone never confirms the event.

**Implementation:** add a narrow E4 lifecycle contract/compatibility layer if required. Keep `OPPORTUNITY_TIMING_MEMBRANE_V5` as the integration point and avoid a second timing system.

**Acceptance:** E4 event at 08:40 remains the causal anchor through repair at 08:45 and confirmation at 08:50.

## Task 3 — E6 thesis persistence

**Tests first:**
- meaningful `CONTESTED`/`VALIDATING` thesis survives a later candle with no trigger;
- placeholder `NONE`, `UNKNOWN`, empty, or `NO_SETUP` cannot overwrite a meaningful state;
- missing proof is retained/merged rather than discarded;
- concrete E6 setup can seed lifecycle state when the E2 opportunity book is empty.

**Implementation:** normalize thesis fields at the lifecycle boundary; merge evidence and missing proof without changing E9 authority.

**Acceptance:** E6 thesis state survives multiple candles until proof or explicit invalidation changes it.

## Task 4 — E7 confirmation persistence

**Tests first:**
- `PENDING/DEVELOPING -> CONFIRMING` persists when no new trigger appears;
- `CONFIRMING -> CONFIRMED` requires closed-candle proof;
- explicit failed proof/invalidation produces invalidation rather than reset to a fresh watch;
- E7 does not create a new opportunity ID.

**Implementation:** strengthen E7 boundary state propagation and merge it into the canonical opportunity record.

**Acceptance:** confirmation lifecycle is monotonic except explicit invalidation/terminal transitions.

## Task 5 — Price-relative timing

**Tests first:**
- young opportunity inside valid entry zone can remain `EARLY`/`ACTIVE`;
- young opportunity already displaced beyond valid economic entry zone becomes `TOO_LATE` with `chase_prohibited=true`;
- older opportunity inside valid zone can remain `ACTIVE` when other timing constraints are satisfied;
- timing uses E4 anchor plus current price, execution zone, ATR/volatility, age, and confirmation timing;
- timing does not independently authorize a trade.

**Implementation:** extend the existing timing membrane contract rather than creating another runtime brain. Add normalized timing fields: `timing_state`, `age_bars`, `entry_window`, `confirmation_lateness`, `chase_prohibited`, `edge_decay`/`edge_remaining`.

**Acceptance:** timing decisions change with price displacement, not age alone.

## Task 6 — E8 remaining edge

**Tests first:**
- unresolved E6 thesis keeps E8 non-actionable;
- valid setup with sufficient current edge becomes `ACTIONABLE` when hard economics permit;
- valid thesis whose current entry has materially decayed becomes `DETERIORATING` or `TOO_LATE`;
- raw RR can remain above minimum while remaining edge is too low due to current price/location/cost/space;
- `edge_remaining` is diagnostic and cannot bypass hard risk gates.

**Implementation:** extend the existing `profit_edge` / `_attach_profit_edge` boundary. Incorporate current entry location, stop/target geometry, opposing space, execution cost, and timing displacement. Keep historical probability separate from current edge.

**Acceptance:** E8 distinguishes `VALID`, `ACTIONABLE`, `DETERIORATING`, and `TOO_LATE` without turning economics into a soft score override.

## Task 7 — E9 known-state output

**Tests first:**
- live WATCH/THESIS/CONFIRMING opportunity produces `WAIT` with known direction/setup/event/ID;
- `TOO_LATE` retains opportunity identity and setup;
- explicit invalidation produces `INVALID`/canonical invalid state;
- no live opportunity remains `NO_TRADE`;
- E9 never mutates upstream evidence to manufacture a decision.

**Implementation:** update the E9 governance compatibility boundary to consume canonical opportunity state and expose upstream evidence. Preserve E9 as sole authorization boundary.

**Acceptance:** logs no longer collapse live opportunities into `setup=UNKNOWN` / `thesis=UNRESOLVED` when upstream data is available.

## Task 8 — WAIT vs NO_TRADE pipeline semantics

**Tests first:**
- live but incomplete opportunity => pipeline decision `WAIT` (or normalized equivalent) and lifecycle state remains active;
- no live opportunity => `NO_TRADE`;
- `WAIT` does not trigger Telegram trade alert;
- `TRADE` remains the only alert-authorized state under manual execution boundary;
- `TOO_LATE` does not trigger a trade alert.

**Implementation:** change only the decision/state presentation boundary necessary to distinguish these states. Do not alter trade authorization gates.

**Acceptance:** production logs clearly distinguish opportunity waiting from absence of opportunity.

## Task 9 — End-to-end lifecycle regression

**Tests first:** create a deterministic multi-candle fixture representing:
- E4 event at 08:40;
- E4 pending/repair at 08:45;
- follow-through/confirmation at 08:50;
- E6 thesis persistence;
- E7 confirmation persistence;
- timing and price displacement;
- E8 edge evaluation;
- E9 WAIT, ACTIONABLE/TRADE, TOO_LATE, and INVALID paths.

Also cover independent BUY/SELL tracking and successor event identity.

**Implementation:** wire the smallest required boundary changes and run the complete production-v2 test suite.

**Acceptance:** all existing tests plus new lifecycle tests pass; no regression to closed-candle-only or E9 authority contracts.

## Task 10 — Cleanup and review

After green regression:
- remove only dead compatibility code proven unnecessary;
- keep surgery layers that still provide active contracts;
- document runtime bindings and authoritative ownership;
- inspect diff for accidental strategy/gate changes;
- request code review;
- verify CI before claiming completion.

## Verification matrix

| Area | Required proof |
|---|---|
| Identity | Same event = same opportunity ID |
| E4 | Repair preserves anchor and age |
| E6 | Thesis survives missing trigger |
| E7 | Confirmation persists until proof/failure |
| Timing | Price-relative, not age-only |
| E8 | Remaining edge is explicit |
| E9 | Upstream evidence retained |
| Decision | WAIT distinct from NO_TRADE |
| Safety | No gate bypass / no auto execution |
| Regression | Existing production-v2 contracts remain green |

## Rollout boundary

Nothing in this plan changes automatic broker execution. The existing manual execution and Telegram alert boundary remains intact. Production deployment occurs only after the implementation branch passes focused tests, full regression, CI, and final review.

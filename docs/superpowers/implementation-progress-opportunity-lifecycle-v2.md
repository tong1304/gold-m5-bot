# Opportunity Lifecycle V2 Implementation Progress

- TDD RED boundaries added for identity continuity, E6/E7 persistence, explicit E9 WAIT semantics, and price-relative timing.
- GREEN implementation added for meaningful evidence preservation, E7 confirmation persistence, explicit WAIT metadata at the E9 watch boundary, and execution-zone-aware timing.
- E9 legacy `decision=NO_TRADE` remains backward-compatible while `decision_semantics=WAIT` and `pipeline_decision=WAIT` expose the live-opportunity state explicitly.
- Full regression remains required before merge; unrelated durable-opportunity-memory baseline failures are tracked separately from this lifecycle work.

# 8F Exposure Limits

## 1. INPUT
- Proposed position, existing exposure, portfolio limits and asset-specific constraints.

## 2. PROCESSING
- Compare proposed exposure against configured per-trade, symbol and portfolio limits.

## 3. OUTPUT
- Exposure status, utilized limits, remaining capacity and blocking flags.

## 4. GATE
- FAIL when any hard exposure limit would be exceeded.

## 5. SCORE
- 0-100 headroom-quality score may describe remaining capacity; it never overrides a hard limit.

## 6. TRACEABILITY
- Record exposure snapshot, limit policy/version, timestamp and all blocking reason codes.
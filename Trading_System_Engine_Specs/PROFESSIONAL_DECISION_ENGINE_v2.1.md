# PROFESSIONAL DECISION ENGINE v2.1

## Core objective

The system is no longer a signal detector whose primary question is `มีสัญญาณไหม?`.

The primary decision question is:

> `ตลาดกำลังให้โอกาสแบบไหน และหลักฐานทั้ง 8 ชั้นสอดคล้องกันมากพอที่จะยอมเสี่ยงเงินจริงหรือไม่?`

## Decision hierarchy

`Market Data -> E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9`

E1-E8 are specialist evidence layers. E9 is the only system-level decision authority.

## Evidence rule

A specialist must distinguish:

- `SUPPORT` — evidence supports the current opportunity.
- `UNKNOWN` — evidence is unavailable; it is not a PASS.
- `CONFLICT` — evidence contradicts the opportunity.
- `INVALID` — required data or calculation is unusable.

For a live BUY/SELL decision, missing mandatory E1-E8 evidence is not silently treated as approval. E9 must return `NO_TRADE` until the missing specialist evidence is available.

## Professional questions

| Engine | Question |
|---|---|
| E1 | Market State คืออะไร? |
| E2 | Regime / Playbook ที่เหมาะคืออะไร? |
| E3 | Structure กำลังบอกอะไร? |
| E4 | Liquidity อยู่ที่ไหนและ Price Action ทำอะไรกับมัน? |
| E5 | ราคาปัจจุบันอยู่ใน Location ที่ได้เปรียบหรือไม่? |
| E6 | มี Trade Setup อะไรและอยู่ระยะไหน? |
| E7 | Setup ได้รับ Trigger / Confirmation แล้วหรือยัง? |
| E8 | ถ้าเสี่ยงเงินจริง ณ จุดนี้ Trade Economics คุ้มไหม? |
| E9 | จากหลักฐานทั้งหมด ควรทำอะไร? |

## E9 authorization

E9 may emit only:

- `BUY`
- `SELL`
- `NO_TRADE`

No specialist engine may authorize execution.

A legacy strategy result of BUY/SELL is only a candidate. E9 may downgrade it to `NO_TRADE` when any mandatory evidence layer is missing or invalid.

## Risk principle

Setup quality or score can never override missing evidence, invalidation, confirmation failure, or risk/economics failure.

`Score` is evidence quality. It is not a trade permission.

## Cycle principle

Every closed M5 candle starts a fresh decision cycle. Previous cycles may be logged for statistics but cannot force the next decision.

## Current implementation

`v11/professional_decision.py` is the decision overlay. It preserves the existing specialist calculations, converts their available output into an explicit E1-E8 evidence ledger, and gives E9 final decision authority.

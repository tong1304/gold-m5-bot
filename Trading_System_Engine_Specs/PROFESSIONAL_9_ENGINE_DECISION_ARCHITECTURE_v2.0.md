# Professional 9-Engine Decision Architecture v2.0

## Core rule

E1-E8 are specialist analysts. They do not decide BUY or SELL. Each engine must answer its own professional question using the market data plus every conclusion already produced upstream.

Only E9 has trade-decision authority and may emit `BUY`, `SELL`, or `NO_TRADE`.

## Engine responsibilities

| Engine | Professional question | Output role |
|---|---|---|
| E1 | Market State คืออะไร? | Market State + Market Bias |
| E2 | Regime/Playbook ที่เหมาะคืออะไร? | Regime + Playbook + contextual bias |
| E3 | Structure กำลังบอกอะไร? | Structure + alignment + structural evidence |
| E4 | Liquidity อยู่ที่ไหนและ Price Action ทำอะไรกับมัน? | Liquidity evidence |
| E5 | ราคาปัจจุบันอยู่ใน Location ที่ได้เปรียบหรือไม่? | Location + extension + space |
| E6 | มี Trade Setup อะไรและอยู่ระยะไหน? | Setup archetype + formation + invalidation + quality |
| E7 | Setup ได้รับ Trigger/Confirmation แล้วหรือยัง? | Trigger + follow-through + confirmation |
| E8 | ถ้าเสี่ยงเงิน ณ จุดนี้ Trade Economics คุ้มไหม? | Invalidation + stop + target + RR + economics |
| E9 | จากหลักฐานทั้งหมด ควรทำอะไร? | BUY / SELL / NO_TRADE |

## Evidence flow

Every closed M5 candle starts a new complete cycle:

`Market Data -> E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9`

Each engine receives all upstream engine results through the pipeline context. A weak or negative specialist conclusion is still an answer and must be handed forward unless it represents true data invalidation or structural/setup invalidation that makes the evidence unusable.

## Gate semantics

`gate_passed` for E1-E8 means **analysis can continue**, not **trade approved**.

Examples:

- `NO_SWEEP` is evidence, not an engine failure.
- `UNKNOWN_REGIME` is a conclusion, not permission to skip the remaining specialists.
- `SETUP_FORMING` is a setup state, not a failed pipeline.
- `NO_TRIGGER` means Entry is not proven yet; E8/E9 still receive the evidence.
- `TRADE_ECONOMICS_UNAVAILABLE` is E8's answer; E9 decides the final action.

## Decision authority

E1-E8 must not emit a trade action. In E8 a price plan uses `orientation=UP|DOWN`; only E9 maps that orientation to `BUY|SELL` after evaluating confirmation, economics, conflicts and total evidence.

## Telegram

Notifications show the specialist conclusion from every engine. They do not describe E1-E8 as "passed for forwarding". The final BUY/SELL statement appears only in E9. When there is no trade, Telegram reports the complete E1-E9 reasoning and the main reason for `NO_TRADE`.

## Cycle behavior

There is no WAIT state and no cross-candle resume state. Every closed M5 candle is a fresh decision cycle. A previous cycle may be logged for statistics, but it cannot force or suppress the next cycle.

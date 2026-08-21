# v5 Real-Data Validation

`validate_v5.py` is a **paper-validation-only** runner. It never places orders.

## Run

```bash
export TWELVE_DATA_API_KEY=YOUR_KEY
python validate_v5.py --symbol XAU/USD --bars 1000
```

Windows PowerShell:

```powershell
$env:TWELVE_DATA_API_KEY="YOUR_KEY"
python validate_v5.py --symbol XAU/USD --bars 1000
```

The report includes:

- WIN / LOSS / BREAKEVEN / TIMEOUT counts
- net expectancy in R with TIMEOUT included
- resolved-trade win rate separately labelled
- profit factor and maximum drawdown in R
- MFE / MAE
- BUY vs SELL breakdown
- number of possible walk-forward windows
- execution assumptions (spread, slippage, conservative STOP_FIRST policy)

## Recommended validation sequence

1. `--bars 1000`
2. `--bars 2000`
3. `--bars 4000`
4. Compare BUY and SELL independently.
5. Compare expectancy after increasing spread/slippage assumptions.
6. Reject the strategy if the edge disappears under realistic costs or in out-of-sample periods.

A positive backtest does **not** authorize live trading. Broker-specific bid/ask, spread, slippage, order-fill behavior and data-feed differences must be validated first.

# XM MT5 Data Feed Setup

The signal engine now uses **XM MetaTrader 5** as its only market-data source for BTC and GOLD. Binance/Kraken are not used as a fallback.

## Architecture

`XM MT5 terminal (Windows/VPS) -> mt5_bridge.py -> Render/cloud bot -> signal engine -> Telegram`

The bridge exposes market data only. It has **no order endpoint** and the bot keeps `live_orders_allowed=false`.

## 1. On the Windows machine/VPS with XM MT5

1. Install and log in to XM MetaTrader 5.
2. Open Market Watch and make sure the two symbols are visible.
3. Confirm the exact XM symbol names. Defaults are:
   - BTC: `BTCUSD`
   - GOLD: `XAUUSD`
4. Install the bridge dependencies:

```text
pip install -r mt5_bridge_requirements.txt
```

5. Set these environment variables on the Windows machine if the defaults do not match your account:

```text
MT5_BTC_SYMBOL=BTCUSD
MT5_GOLD_SYMBOL=XAUUSD
MT5_BRIDGE_TOKEN=<long-random-secret>
MT5_BRIDGE_PORT=8787
```

If the MT5 terminal is already logged into XM, the bridge can use that terminal session. Otherwise also set `MT5_PATH`, `MT5_LOGIN`, `MT5_PASSWORD`, and `MT5_SERVER`.

6. Start:

```text
python mt5_bridge.py
```

## 2. On Render/cloud

Set these environment variables:

```text
MT5_BRIDGE_URL=https://<your-public-mt5-bridge-host>
MT5_BRIDGE_TOKEN=<same-token-as-Windows>
MT5_BTC_SYMBOL=BTCUSD
MT5_GOLD_SYMBOL=XAUUSD
```

Do **not** put the XM password or bridge token in GitHub files.

## 3. Candle source

The bridge reads bars directly from the XM MT5 terminal using MT5 M5/H1/M15 data. The cloud adapter converts MT5 timestamps to UTC and removes the currently forming candle before indicator/pattern analysis.

## 4. Important

Render normally runs Linux and cannot host the Windows XM MT5 terminal itself. Therefore a Windows PC/VPS running XM MT5 must remain online and reachable by the cloud bot. The bridge should be protected by `MT5_BRIDGE_TOKEN` and HTTPS/reverse proxy in production.

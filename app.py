"""
XAUUSD M5 STATISTICAL TRADING SIGNAL ENGINE
============================================

Architecture
------------
MT5 Terminal
    |
    | M5 candles via HTTP
    v
Render
    |
    +-- Historical Pattern Matching
    +-- Top-N Similarity
    +-- Historical Statistics
    +-- EMA20 / EMA50
    +-- RSI
    +-- ATR
    +-- Momentum
    +-- Market Structure
    +-- Score
    +-- Entry / SL / TP
    +-- Backtest
    |
    v
Telegram

Render Environment Variables
----------------------------

TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID

MT5_DATA_URL
MT5_DATA_TOKEN

PORT

Optional:
CANDLE_COUNT=1500
PATTERN_LENGTH=12
TOP_MATCHES=40
MIN_SCORE=68
MIN_PROBABILITY=62
MIN_RR=1.5
SIGNAL_INTERVAL=60

Expected MT5_DATA_URL response
------------------------------

{
    "symbol": "XAUUSD",
    "timeframe": "M5",
    "candles": [
        {
            "time": "2026-08-21T13:55:00+00:00",
            "open": 4640.2,
            "high": 4643.1,
            "low": 4639.7,
            "close": 4642.0,
            "volume": 1234
        }
    ]
}

IMPORTANT
---------

The Render service does NOT connect directly to the MT5 Desktop
terminal. MT5_DATA_URL must provide the M5 candle data from the
MT5 side.

For testing without MT5_DATA_URL, the program can use Yahoo Finance
as a fallback if DATA_SOURCE_FALLBACK=YAHOO.
"""

import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"

PORT = int(
    os.environ.get(
        "PORT",
        "10000"
    )
)

MT5_DATA_URL = os.environ.get(
    "MT5_DATA_URL",
    ""
).strip()

MT5_DATA_TOKEN = os.environ.get(
    "MT5_DATA_TOKEN",
    ""
).strip()

DATA_SOURCE_FALLBACK = os.environ.get(
    "DATA_SOURCE_FALLBACK",
    "YAHOO"
).upper()

CANDLE_COUNT = int(
    os.environ.get(
        "CANDLE_COUNT",
        "1500"
    )
)

PATTERN_LENGTH = int(
    os.environ.get(
        "PATTERN_LENGTH",
        "12"
    )
)

TOP_MATCHES = int(
    os.environ.get(
        "TOP_MATCHES",
        "40"
    )
)

MIN_SCORE = float(
    os.environ.get(
        "MIN_SCORE",
        "68"
    )
)

MIN_PROBABILITY = float(
    os.environ.get(
        "MIN_PROBABILITY",
        "62"
    )
)

MIN_RR = float(
    os.environ.get(
        "MIN_RR",
        "1.5"
    )
)

SIGNAL_INTERVAL = int(
    os.environ.get(
        "SIGNAL_INTERVAL",
        "60"
    )
)

EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14
ATR_PERIOD = 14

FORWARD_BARS = 12

SL_ATR_MULTIPLIER = 1.25
SL_BUFFER_ATR = 0.15

MAX_SCAN = 1200


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    ""
).strip()


# ============================================================
# GLOBAL STATE
# ============================================================

LAST_SIGNAL_KEY = None

LAST_CANDLE_TIME = None

STATE_LOCK = threading.Lock()


# ============================================================
# HTTP
# ============================================================

def http_get(
    url,
    headers=None,
    timeout=25
):

    headers = headers or {}

    request = Request(
        url,
        headers=headers
    )

    with urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read().decode(
            "utf-8"
        )


def http_post_json(
    url,
    payload,
    headers=None,
    timeout=25
):

    headers = headers or {}

    body = json.dumps(
        payload
    ).encode(
        "utf-8"
    )

    request_headers = {
        "Content-Type":
            "application/json"
    }

    request_headers.update(
        headers
    )

    request = Request(
        url,
        data=body,
        headers=request_headers,
        method="POST"
    )

    with urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read().decode(
            "utf-8"
        )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_enabled():

    return bool(
        TELEGRAM_BOT_TOKEN
        and
        TELEGRAM_CHAT_ID
    )


def send_telegram(
    message
):

    if not telegram_enabled():

        print(
            "Telegram is not configured."
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    payload = urlencode({

        "chat_id":
            TELEGRAM_CHAT_ID,

        "text":
            message,

        "parse_mode":
            "HTML"

    }).encode(
        "utf-8"
    )

    request = Request(
        url,
        data=payload,
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        method="POST"
    )

    try:

        with urlopen(
            request,
            timeout=20
        ) as response:

            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        if result.get("ok"):

            print(
                "Telegram: SENT"
            )

            return True

        print(
            "Telegram error:",
            result
        )

        return False

    except Exception as error:

        print(
            "Telegram exception:",
            error
        )

        return False


# ============================================================
# FORMAT TELEGRAM SIGNAL
# ============================================================

def format_signal(
    result
):

    signal = result["signal"]

    if signal == "BUY":

        icon = "🟢"

    else:

        icon = "🔴"

    stats = result[
        "historical_statistics"
    ]

    return f"""
{icon} <b>XAUUSD M5 SIGNAL</b>

<b>Signal:</b> {signal}

<b>Entry:</b> {result["entry"]}

<b>T/P:</b> {result["take_profit"]}

<b>S/L:</b> {result["stop_loss"]}

<b>Risk/Reward:</b> {result["risk_reward"]}

<b>Score:</b> {result["score"]}

<b>BUY Probability:</b> {stats["buy_probability"]}%

<b>SELL Probability:</b> {stats["sell_probability"]}%

<b>Historical Matches:</b> {stats["sample_size"]}

<b>Average Up:</b> {stats["expected_up_atr"]} ATR

<b>Average Down:</b> {stats["expected_down_atr"]} ATR

<b>RSI:</b> {result["rsi"]}

<b>ATR:</b> {result["atr"]}

<b>EMA20:</b> {result["ema20"]}

<b>EMA50:</b> {result["ema50"]}

<b>Trend:</b> {result["trend"]}

<b>Time:</b> {result["timestamp"]}
""".strip()


# ============================================================
# DATA NORMALIZATION
# ============================================================

def normalize_candles(
    candles
):

    normalized = []

    for item in candles:

        try:

            timestamp = item.get(
                "time",
                item.get(
                    "timestamp"
                )
            )

            if timestamp is None:

                continue

            if isinstance(
                timestamp,
                (int, float)
            ):

                dt = datetime.fromtimestamp(
                    timestamp,
                    timezone.utc
                )

                timestamp_text = dt.isoformat()

            else:

                timestamp_text = str(
                    timestamp
                )

            open_price = float(
                item["open"]
            )

            high_price = float(
                item["high"]
            )

            low_price = float(
                item["low"]
            )

            close_price = float(
                item["close"]
            )

            volume = float(
                item.get(
                    "volume",
                    0
                )
                or 0
            )

            if not (
                high_price >=
                max(
                    open_price,
                    close_price
                )
            ):

                continue

            if not (
                low_price <=
                min(
                    open_price,
                    close_price
                )
            ):

                continue

            normalized.append({

                "time":
                    timestamp_text,

                "open":
                    open_price,

                "high":
                    high_price,

                "low":
                    low_price,

                "close":
                    close_price,

                "volume":
                    volume
            })

        except Exception:

            continue

    normalized.sort(
        key=lambda x:
            x["time"]
    )

    return normalized[
        -CANDLE_COUNT:
    ]


# ============================================================
# MT5 DATA SOURCE
# ============================================================

def get_mt5_data():

    if not MT5_DATA_URL:

        return None

    headers = {}

    if MT5_DATA_TOKEN:

        headers[
            "Authorization"
        ] = (
            "Bearer "
            + MT5_DATA_TOKEN
        )

    raw = http_get(
        MT5_DATA_URL,
        headers=headers,
        timeout=25
    )

    payload = json.loads(
        raw
    )

    if isinstance(
        payload,
        list
    ):

        candles = payload

    else:

        candles = payload.get(
            "candles",
            payload.get(
                "data",
                []
            )
        )

    candles = normalize_candles(
        candles
    )

    if len(candles) < 200:

        raise Exception(
            "MT5 source returned fewer than 200 candles"
        )

    return candles


# ============================================================
# YAHOO FALLBACK
# ============================================================

def get_yahoo_data():

    params = urlencode({

        "range":
            "7d",

        "interval":
            "5m",

        "includePrePost":
            "true",

        "events":
            "div,splits"
    })

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        "XAUUSD=X?"
        + params
    )

    raw = http_get(
        url,
        timeout=25
    )

    payload = json.loads(
        raw
    )

    result = payload[
        "chart"
    ][
        "result"
    ][0]

    timestamps = result[
        "timestamp"
    ]

    quote = result[
        "indicators"
    ][
        "quote"
    ][0]

    candles = []

    for i, timestamp in enumerate(
        timestamps
    ):

        try:

            o = quote["open"][i]
            h = quote["high"][i]
            l = quote["low"][i]
            c = quote["close"][i]

            if None in (
                o,
                h,
                l,
                c
            ):

                continue

            volume = 0

            if i < len(
                quote.get(
                    "volume",
                    []
                )
            ):

                volume = (
                    quote[
                        "volume"
                    ][i]
                    or 0
                )

            candles.append({

                "time":
                    datetime.fromtimestamp(
                        timestamp,
                        timezone.utc
                    ).isoformat(),

                "open":
                    float(o),

                "high":
                    float(h),

                "low":
                    float(l),

                "close":
                    float(c),

                "volume":
                    float(volume)
            })

        except Exception:

            continue

    candles = normalize_candles(
        candles
    )

    return candles


# ============================================================
# GET MARKET DATA
# ============================================================

def get_market_data():

    if MT5_DATA_URL:

        candles = get_mt5_data()

        return {
            "source":
                "MT5_BRIDGE",

            "candles":
                candles
        }

    if DATA_SOURCE_FALLBACK == "YAHOO":

        print(
            "WARNING: MT5_DATA_URL is not configured."
        )

        print(
            "Using Yahoo fallback."
        )

        candles = get_yahoo_data()

        return {
            "source":
                "YAHOO_FALLBACK",

            "candles":
                candles
        }

    raise Exception(
        "MT5_DATA_URL is not configured"
    )


# ============================================================
# MATH
# ============================================================

def mean(
    values
):

    if not values:

        return 0.0

    return sum(
        values
    ) / len(
        values
    )


def ema(
    values,
    period
):

    if not values:

        return []

    result = []

    alpha = (
        2.0
        / (
            period
            + 1
        )
    )

    current = values[0]

    result.append(
        current
    )

    for value in values[1:]:

        current = (
            current
            + alpha
            * (
                value
                - current
            )
        )

        result.append(
            current
        )

    return result


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    closes,
    period=14
):

    result = [
        50.0
    ] * len(
        closes
    )

    if len(
        closes
    ) <= period:

        return result

    gains = []
    losses = []

    for i in range(
        1,
        period + 1
    ):

        change = (
            closes[i]
            - closes[i - 1]
        )

        gains.append(
            max(
                change,
                0
            )
        )

        losses.append(
            max(
                -change,
                0
            )
        )

    avg_gain = mean(
        gains
    )

    avg_loss = mean(
        losses
    )

    def rsi_value():

        if avg_loss == 0:

            return 100.0

        rs = (
            avg_gain
            / avg_loss
        )

        return (
            100
            - (
                100
                / (
                    1
                    + rs
                )
            )
        )

    result[period] = rsi_value()

    for i in range(
        period + 1,
        len(closes)
    ):

        change = (
            closes[i]
            - closes[i - 1]
        )

        gain = max(
            change,
            0
        )

        loss = max(
            -change,
            0
        )

        avg_gain = (
            (
                avg_gain
                * (
                    period - 1
                )
                + gain
            )
            / period
        )

        avg_loss = (
            (
                avg_loss
                * (
                    period - 1
                )
                + loss
            )
            / period
        )

        result[i] = rsi_value()

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=14
):

    tr = [
        0.0
    ]

    for i in range(
        1,
        len(candles)
    ):

        high = candles[i][
            "high"
        ]

        low = candles[i][
            "low"
        ]

        previous_close = candles[
            i - 1
        ][
            "close"
        ]

        value = max(

            high - low,

            abs(
                high
                - previous_close
            ),

            abs(
                low
                - previous_close
            )
        )

        tr.append(
            value
        )

    result = [
        0.0
    ] * len(
        candles
    )

    if len(
        tr
    ) <= period:

        return result

    current = mean(
        tr[
            1:
            period + 1
        ]
    )

    for i in range(
        period,
        len(candles)
    ):

        if i == period:

            current = mean(
                tr[
                    1:
                    period + 1
                ]
            )

        else:

            current = (
                (
                    current
                    * (
                        period - 1
                    )
                )
                + tr[i]
            ) / period

        result[i] = current

    return result


# ============================================================
# INDICATORS
# ============================================================

def build_indicators(
    candles
):

    closes = [
        x["close"]
        for x in candles
    ]

    ema20 = ema(
        closes,
        EMA_FAST
    )

    ema50 = ema(
        closes,
        EMA_SLOW
    )

    rsi = calculate_rsi(
        closes,
        RSI_PERIOD
    )

    atr = calculate_atr(
        candles,
        ATR_PERIOD
    )

    result = []

    for i in range(
        len(candles)
    ):

        momentum = 0.0

        if i >= 5:

            momentum = (
                closes[i]
                - closes[i - 5]
            )

        atr_value = atr[i]

        normalized_momentum = 0.0

        if atr_value > 0:

            normalized_momentum = (
                momentum
                / atr_value
            )

        result.append({

            "ema20":
                ema20[i],

            "ema50":
                ema50[i],

            "rsi":
                rsi[i],

            "atr":
                atr[i],

            "momentum":
                normalized_momentum
        })

    return result


# ============================================================
# CANDLE FEATURE
# ============================================================

def candle_features(
    candle
):

    o = candle["open"]
    h = candle["high"]
    l = candle["low"]
    c = candle["close"]

    candle_range = max(
        h - l,
        0.0000001
    )

    body = abs(
        c - o
    )

    upper_wick = (
        h
        - max(
            o,
            c
        )
    )

    lower_wick = (
        min(
            o,
            c
        )
        - l
    )

    return [

        body
        / candle_range,

        upper_wick
        / candle_range,

        lower_wick
        / candle_range
    ]


# ============================================================
# PATTERN VECTOR
# ============================================================

def pattern_vector(
    candles,
    indicators,
    end_index
):

    start = (
        end_index
        - PATTERN_LENGTH
        + 1
    )

    if start < 0:

        return None

    vector = []

    for i in range(
        start,
        end_index + 1
    ):

        candle = candle_features(
            candles[i]
        )

        indicator = indicators[i]

        vector.extend(
            candle
        )

        vector.append(
            max(
                -3,
                min(
                    3,
                    indicator[
                        "momentum"
                    ]
                )
            )
        )

        vector.append(
            indicator[
                "rsi"
            ] / 100
        )

        vector.append(

            1.0

            if
            indicator["ema20"]
            >
            indicator["ema50"]

            else

            -1.0
        )

    return vector


# ============================================================
# DISTANCE
# ============================================================

def euclidean_distance(
    a,
    b
):

    if not a or not b:

        return 999999

    if len(a) != len(b):

        return 999999

    total = 0.0

    for x, y in zip(
        a,
        b
    ):

        total += (
            x - y
        ) ** 2

    return math.sqrt(
        total
        / len(a)
    )


def similarity(
    a,
    b
):

    distance = euclidean_distance(
        a,
        b
    )

    return (
        1
        / (
            1
            + distance
        )
    )


# ============================================================
# HISTORICAL MATCHES
# ============================================================

def find_historical_matches(
    candles,
    indicators,
    current_index
):

    current = pattern_vector(
        candles,
        indicators,
        current_index
    )

    if current is None:

        return []

    matches = []

    first_index = max(
        PATTERN_LENGTH
        + 20,
        current_index
        - MAX_SCAN
    )

    last_index = (
        current_index
        - FORWARD_BARS
        - 2
    )

    for i in range(
        first_index,
        last_index + 1
    ):

        historical = pattern_vector(
            candles,
            indicators,
            i
        )

        if historical is None:

            continue

        sim = similarity(
            current,
            historical
        )

        entry = candles[i][
            "close"
        ]

        future = candles[
            i + 1:
            i + 1 + FORWARD_BARS
        ]

        if len(
            future
        ) < FORWARD_BARS:

            continue

        high = max(
            x["high"]
            for x in future
        )

        low = min(
            x["low"]
            for x in future
        )

        close = future[
            -1
        ][
            "close"
        ]

        up_move = (
            high
            - entry
        )

        down_move = (
            entry
            - low
        )

        close_move = (
            close
            - entry
        )

        direction = (
            "BUY"
            if close_move > 0
            else "SELL"
        )

        matches.append({

            "index":
                i,

            "similarity":
                sim,

            "entry":
                entry,

            "up_move":
                up_move,

            "down_move":
                down_move,

            "close_move":
                close_move,

            "direction":
                direction
        })

    matches.sort(

        key=lambda x:
            x["similarity"],

        reverse=True
    )

    return matches[
        :TOP_MATCHES
    ]


# ============================================================
# HISTORICAL STATISTICS
# ============================================================

def historical_statistics(
    matches,
    atr_value
):

    if not matches:

        return {

            "sample_size":
                0,

            "buy_probability":
                0,

            "sell_probability":
                0,

            "expected_up_atr":
                0,

            "expected_down_atr":
                0,

            "average_similarity":
                0,

            "best_similarity":
                0
        }

    buy_weight = 0.0
    sell_weight = 0.0

    total_weight = 0.0

    weighted_up = 0.0
    weighted_down = 0.0

    similarities = []

    for item in matches:

        weight = (
            item[
                "similarity"
            ]
            ** 3
        )

        total_weight += weight

        similarities.append(
            item[
                "similarity"
            ]
        )

        if item[
            "direction"
        ] == "BUY":

            buy_weight += weight

        else:

            sell_weight += weight

        if atr_value > 0:

            weighted_up += (
                item[
                    "up_move"
                ]
                / atr_value
                * weight
            )

            weighted_down += (
                item[
                    "down_move"
                ]
                / atr_value
                * weight
            )

    if total_weight <= 0:

        return {

            "sample_size":
                len(matches),

            "buy_probability":
                0,

            "sell_probability":
                0,

            "expected_up_atr":
                0,

            "expected_down_atr":
                0,

            "average_similarity":
                0,

            "best_similarity":
                0
        }

    return {

        "sample_size":
            len(matches),

        "buy_probability":
            round(
                buy_weight
                / total_weight
                * 100,
                2
            ),

        "sell_probability":
            round(
                sell_weight
                / total_weight
                * 100,
                2
            ),

        "expected_up_atr":
            round(
                weighted_up
                / total_weight,
                3
            ),

        "expected_down_atr":
            round(
                weighted_down
                / total_weight,
                3
            ),

        "average_similarity":
            round(
                mean(
                    similarities
                ),
                4
            ),

        "best_similarity":
            round(
                max(
                    similarities
                ),
                4
            )
    }


# ============================================================
# SWING STRUCTURE
# ============================================================

def recent_swing_low(
    candles,
    index,
    window=5,
    lookback=100
):

    start = max(
        window,
        index
        - lookback
    )

    for i in range(
        index - window,
        start - 1,
        -1
    ):

        value = candles[i][
            "low"
        ]

        is_low = True

        for j in range(
            i - window,
            i + window + 1
        ):

            if j < 0:
                continue

            if j >= len(
                candles
            ):
                continue

            if j == i:
                continue

            if candles[j][
                "low"
            ] <= value:

                is_low = False

                break

        if is_low:

            return value

    return None


def recent_swing_high(
    candles,
    index,
    window=5,
    lookback=100
):

    start = max(
        window,
        index
        - lookback
    )

    for i in range(
        index - window,
        start - 1,
        -1
    ):

        value = candles[i][
            "high"
        ]

        is_high = True

        for j in range(
            i - window,
            i + window + 1
        ):

            if j < 0:
                continue

            if j >= len(
                candles
            ):
                continue

            if j == i:
                continue

            if candles[j][
                "high"
            ] >= value:

                is_high = False

                break

        if is_high:

            return value

    return None


# ============================================================
# SIGNAL
# ============================================================

def generate_signal(
    candles
):

    if len(
        candles
    ) < 250:

        raise Exception(
            "At least 250 candles are required"
        )

    indicators = build_indicators(
        candles
    )

    index = len(
        candles
    ) - 1

    candle = candles[
        index
    ]

    indicator = indicators[
        index
    ]

    atr_value = indicator[
        "atr"
    ]

    if atr_value <= 0:

        return {

            "signal":
                "NO_TRADE",

            "reason":
                "ATR unavailable"
        }

    matches = find_historical_matches(
        candles,
        indicators,
        index
    )

    stats = historical_statistics(
        matches,
        atr_value
    )

    buy_score = 0.0
    sell_score = 0.0

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if indicator[
        "ema20"
    ] > indicator[
        "ema50"
    ]:

        buy_score += 18

    else:

        sell_score += 18

    # --------------------------------------------------------
    # HISTORICAL PROBABILITY
    # --------------------------------------------------------

    buy_score += (
        stats[
            "buy_probability"
        ]
        * 0.30
    )

    sell_score += (
        stats[
            "sell_probability"
        ]
        * 0.30
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi_value = indicator[
        "rsi"
    ]

    if (
        50 <= rsi_value <= 68
    ):

        buy_score += 12

    elif (
        32 <= rsi_value < 50
    ):

        sell_score += 12

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum = indicator[
        "momentum"
    ]

    if momentum > 0.25:

        buy_score += 12

    elif momentum < -0.25:

        sell_score += 12

    # --------------------------------------------------------
    # CANDLE
    # --------------------------------------------------------

    candle_range = max(
        candle["high"]
        - candle["low"],
        0.000001
    )

    body = abs(
        candle["close"]
        - candle["open"]
    )

    body_ratio = (
        body
        / candle_range
    )

    if (
        candle["close"]
        >
        candle["open"]
        and
        body_ratio >= 0.35
    ):

        buy_score += 8

    elif (
        candle["close"]
        <
        candle["open"]
        and
        body_ratio >= 0.35
    ):

        sell_score += 8

    # --------------------------------------------------------
    # FINAL DIRECTION
    # --------------------------------------------------------

    if (
        buy_score >= MIN_SCORE
        and
        buy_score > sell_score + 5
        and
        stats[
            "buy_probability"
        ] >= MIN_PROBABILITY
    ):

        direction = "BUY"

        score = buy_score

    elif (
        sell_score >= MIN_SCORE
        and
        sell_score > buy_score + 5
        and
        stats[
            "sell_probability"
        ] >= MIN_PROBABILITY
    ):

        direction = "SELL"

        score = sell_score

    else:

        direction = "NO_TRADE"

        score = max(
            buy_score,
            sell_score
        )

    entry = candle[
        "close"
    ]

    # --------------------------------------------------------
    # BUY SL / TP
    # --------------------------------------------------------

    if direction == "BUY":

        swing_low = recent_swing_low(
            candles,
            index
        )

        atr_stop = (
            entry
            - atr_value
            * SL_ATR_MULTIPLIER
        )

        if swing_low is not None:

            structure_stop = (
                swing_low
                - atr_value
                * SL_BUFFER_ATR
            )

            stop_loss = min(
                atr_stop,
                structure_stop
            )

        else:

            stop_loss = atr_stop

        risk = (
            entry
            - stop_loss
        )

        statistical_target = (
            entry
            + atr_value
            * max(
                1.5,
                stats[
                    "expected_up_atr"
                ]
            )
        )

        minimum_target = (
            entry
            + risk
            * MIN_RR
        )

        take_profit = max(
            statistical_target,
            minimum_target
        )

    # --------------------------------------------------------
    # SELL SL / TP
    # --------------------------------------------------------

    elif direction == "SELL":

        swing_high = recent_swing_high(
            candles,
            index
        )

        atr_stop = (
            entry
            + atr_value
            * SL_ATR_MULTIPLIER
        )

        if swing_high is not None:

            structure_stop = (
                swing_high
                + atr_value
                * SL_BUFFER_ATR
            )

            stop_loss = max(
                atr_stop,
                structure_stop
            )

        else:

            stop_loss = atr_stop

        risk = (
            stop_loss
            - entry
        )

        statistical_target = (
            entry
            - atr_value
            * max(
                1.5,
                stats[
                    "expected_down_atr"
                ]
            )
        )

        minimum_target = (
            entry
            - risk
            * MIN_RR
        )

        take_profit = min(
            statistical_target,
            minimum_target
        )

    else:

        stop_loss = None

        take_profit = None

        risk = None

    # --------------------------------------------------------
    # RISK / REWARD
    # --------------------------------------------------------

    if (
        direction == "BUY"
        and
        risk
        and
        risk > 0
    ):

        reward = (
            take_profit
            - entry
        )

        rr = (
            reward
            / risk
        )

    elif (
        direction == "SELL"
        and
        risk
        and
        risk > 0
    ):

        reward = (
            entry
            - take_profit
        )

        rr = (
            reward
            / risk
        )

    else:

        rr = None

    result = {

        "timestamp":
            candle["time"],

        "symbol":
            SYMBOL,

        "timeframe":
            TIMEFRAME,

        "data_source":
            (
                "MT5_BRIDGE"
                if MT5_DATA_URL
                else "YAHOO_FALLBACK"
            ),

        "signal":
            direction,

        "score":
            round(
                score,
                2
            ),

        "entry":
            round(
                entry,
                2
            ),

        "stop_loss":
            (
                round(
                    stop_loss,
                    2
                )
                if stop_loss is not None
                else None
            ),

        "take_profit":
            (
                round(
                    take_profit,
                    2
                )
                if take_profit is not None
                else None
            ),

        "risk_reward":
            (
                round(
                    rr,
                    2
                )
                if rr is not None
                else None
            ),

        "atr":
            round(
                atr_value,
                2
            ),

        "rsi":
            round(
                rsi_value,
                2
            ),

        "ema20":
            round(
                indicator[
                    "ema20"
                ],
                2
            ),

        "ema50":
            round(
                indicator[
                    "ema50"
                ],
                2
            ),

        "trend":
            (
                "BULLISH"
                if indicator[
                    "ema20"
                ]
                >
                indicator[
                    "ema50"
                ]
                else
                "BEARISH"
            ),

        "momentum":
            round(
                momentum,
                3
            ),

        "historical_statistics":
            stats,

        "matched_patterns":
            len(matches),

        "pattern_method":
            "TOP-N HISTORICAL SIMILARITY",

        "parameters": {

            "pattern_length":
                PATTERN_LENGTH,

            "top_matches":
                TOP_MATCHES,

            "minimum_score":
                MIN_SCORE,

            "minimum_probability":
                MIN_PROBABILITY,

            "minimum_rr":
                MIN_RR
        }
    }

    return result


# ============================================================
# PROCESS SIGNAL
# ============================================================

def process_signal():

    global LAST_SIGNAL_KEY

    market = get_market_data()

    candles = market[
        "candles"
    ]

    if len(
        candles
    ) < 250:

        raise Exception(
            "Not enough candles"
        )

    result = generate_signal(
        candles
    )

    result[
        "data_source"
    ] = market[
        "source"
    ]

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )

    if result[
        "signal"
    ] not in (
        "BUY",
        "SELL"
    ):

        return result

    candle_time = result[
        "timestamp"
    ]

    signal_key = (
        candle_time
        + "_"
        + result["signal"]
    )

    with STATE_LOCK:

        if signal_key == LAST_SIGNAL_KEY:

            print(
                "Duplicate signal. "
                "Telegram not sent."
            )

            return result

        LAST_SIGNAL_KEY = signal_key

    message = format_signal(
        result
    )

    telegram_result = send_telegram(
        message
    )

    result[
        "telegram_sent"
    ] = telegram_result

    return result


# ============================================================
# BACKTEST
# ============================================================

def backtest(
    candles
):

    if len(
        candles
    ) < 400:

        raise Exception(
            "At least 400 candles are required"
        )

    indicators = build_indicators(
        candles
    )

    trades = []

    start = max(
        300,
        PATTERN_LENGTH
        + 50
    )

    end = (
        len(candles)
        - FORWARD_BARS
        - 2
    )

    for i in range(
        start,
        end
    ):

        matches = find_historical_matches(
            candles,
            indicators,
            i
        )

        if len(
            matches
        ) < 10:

            continue

        atr_value = indicators[
            i
        ][
            "atr"
        ]

        stats = historical_statistics(
            matches,
            atr_value
        )

        buy_probability = stats[
            "buy_probability"
        ]

        sell_probability = stats[
            "sell_probability"
        ]

        if (
            buy_probability
            >= MIN_PROBABILITY
            and
            buy_probability
            >
            sell_probability + 5
        ):

            direction = "BUY"

        elif (
            sell_probability
            >= MIN_PROBABILITY
            and
            sell_probability
            >
            buy_probability + 5
        ):

            direction = "SELL"

        else:

            continue

        entry = candles[
            i
        ][
            "close"
        ]

        if direction == "BUY":

            stop_loss = (
                entry
                - atr_value
                * SL_ATR_MULTIPLIER
            )

            take_profit = (
                entry
                + (
                    entry
                    - stop_loss
                )
                * MIN_RR
            )

        else:

            stop_loss = (
                entry
                + atr_value
                * SL_ATR_MULTIPLIER
            )

            take_profit = (
                entry
                - (
                    stop_loss
                    - entry
                )
                * MIN_RR
            )

        result = "TIMEOUT"

        exit_price = candles[
            min(
                i + FORWARD_BARS,
                len(candles) - 1
            )
        ][
            "close"
        ]

        for j in range(
            i + 1,
            min(
                i + 1 + FORWARD_BARS,
                len(candles)
            )
        ):

            high = candles[
                j
            ][
                "high"
            ]

            low = candles[
                j
            ][
                "low"
            ]

            if direction == "BUY":

                if low <= stop_loss:

                    result = "LOSS"

                    exit_price = stop_loss

                    break

                if high >= take_profit:

                    result = "WIN"

                    exit_price = take_profit

                    break

            else:

                if high >= stop_loss:

                    result = "LOSS"

                    exit_price = stop_loss

                    break

                if low <= take_profit:

                    result = "WIN"

                    exit_price = take_profit

                    break

        if direction == "BUY":

            pnl_r = (
                exit_price
                - entry
            ) / (
                entry
                - stop_loss
            )

        else:

            pnl_r = (
                entry
                - exit_price
            ) / (
                stop_loss
                - entry
            )

        trades.append({

            "time":
                candles[i][
                    "time"
                ],

            "direction":
                direction,

            "result":
                result,

            "pnl_r":
                round(
                    pnl_r,
                    3
                )
        })

    wins = sum(

        1

        for x in trades

        if x["result"] == "WIN"
    )

    losses = sum(

        1

        for x in trades

        if x["result"] == "LOSS"
    )

    timeouts = sum(

        1

        for x in trades

        if x["result"] == "TIMEOUT"
    )

    total = len(
        trades
    )

    closed = (
        wins
        + losses
    )

    win_rate = (

        wins
        / closed
        * 100

        if closed > 0

        else 0
    )

    total_r = sum(

        x["pnl_r"]

        for x in trades
    )

    avg_r = (

        total_r
        / total

        if total > 0

        else 0
    )

    return {

        "symbol":
            SYMBOL,

        "timeframe":
            TIMEFRAME,

        "data_source":
            (
                "MT5_BRIDGE"
                if MT5_DATA_URL
                else "YAHOO_FALLBACK"
            ),

        "candles":
            len(candles),

        "trades":
            total,

        "wins":
            wins,

        "losses":
            losses,

        "timeouts":
            timeouts,

        "closed_trades":
            closed,

        "win_rate":
            round(
                win_rate,
                2
            ),

        "total_R":
            round(
                total_r,
                3
            ),

        "average_R":
            round(
                avg_r,
                3
            ),

        "minimum_probability":
            MIN_PROBABILITY,

        "minimum_rr":
            MIN_RR,

        "warning":
            "Backtest results are historical and do not guarantee future performance."
    }


# ============================================================
# HTTP SERVER
# ============================================================

class Handler(
    BaseHTTPRequestHandler
):

    def send_json(
        self,
        payload,
        status=200
    ):

        body = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ).encode(
            "utf-8"
        )

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(
                len(body)
            )
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def do_HEAD(
        self
    ):

        path = self.path.split(
            "?",
            1
        )[0]

        if path in (
            "/",
            "/health",
            "/signal",
            "/backtest"
        ):

            self.send_response(
                200
            )

            self.send_header(
                "Content-Type",
                "application/json"
            )

            self.end_headers()

        else:

            self.send_response(
                404
            )

            self.end_headers()

    def do_GET(
        self
    ):

        try:

            path = self.path.split(
                "?",
                1
            )[0]

            print(
                "GET:",
                self.path,
                "=>",
                path
            )

            # ------------------------------------------------
            # HOME
            # ------------------------------------------------

            if path == "/":

                self.send_json({

                    "name":
                        "XAUUSD M5 Statistical Signal Engine",

                    "status":
                        "online",

                    "symbol":
                        SYMBOL,

                    "timeframe":
                        TIMEFRAME,

                    "data_source":
                        (
                            "MT5_BRIDGE"
                            if MT5_DATA_URL
                            else "YAHOO_FALLBACK"
                        ),

                    "telegram":
                        telegram_enabled(),

                    "endpoints": [

                        "/signal",

                        "/backtest",

                        "/health"

                    ]
                })

                return

            # ------------------------------------------------
            # HEALTH
            # ------------------------------------------------

            if path == "/health":

                self.send_json({

                    "status":
                        "healthy",

                    "symbol":
                        SYMBOL,

                    "timeframe":
                        TIMEFRAME,

                    "telegram":
                        telegram_enabled(),

                    "mt5_data_url":
                        bool(
                            MT5_DATA_URL
                        ),

                    "fallback":
                        DATA_SOURCE_FALLBACK,

                    "time":
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                })

                return

            # ------------------------------------------------
            # SIGNAL
            # ------------------------------------------------

            if path == "/signal":

                result = process_signal()

                self.send_json(
                    result
                )

                return

            # ------------------------------------------------
            # BACKTEST
            # ------------------------------------------------

            if path == "/backtest":

                market = get_market_data()

                result = backtest(
                    market[
                        "candles"
                    ]
                )

                result[
                    "data_source"
                ] = market[
                    "source"
                ]

                self.send_json(
                    result
                )

                return

            # ------------------------------------------------
            # 404
            # ------------------------------------------------

            self.send_json({

                "error":
                    "Endpoint not found",

                "requested_path":
                    path,

                "available_endpoints": [

                    "/",

                    "/signal",

                    "/backtest",

                    "/health"

                ]

            }, 404)

        except Exception as error:

            print(
                "Request error:",
                repr(error)
            )

            self.send_json({

                "signal":
                    "ERROR",

                "error":
                    str(error)

            }, 500)

    def log_message(
        self,
        format_string,
        *args
    ):

        print(
            "%s - - [%s] %s"
            % (
                self.address_string(),
                self.log_date_time_string(),
                format_string % args
            )
        )


# ============================================================
# BACKGROUND LOOP
# ============================================================

def signal_loop():

    print(
        "Signal loop started."
    )

    while True:

        try:

            process_signal()

        except Exception as error:

            print(
                "Signal loop error:",
                repr(error)
            )

        time.sleep(
            SIGNAL_INTERVAL
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "XAUUSD M5 STATISTICAL SIGNAL ENGINE"
    )

    print("=" * 70)

    print(
        "PORT:",
        PORT
    )

    print(
        "SYMBOL:",
        SYMBOL
    )

    print(
        "TIMEFRAME:",
        TIMEFRAME
    )

    print(
        "MT5 DATA URL:",
        bool(
            MT5_DATA_URL
        )
    )

    print(
        "DATA FALLBACK:",
        DATA_SOURCE_FALLBACK
    )

    print(
        "PATTERN LENGTH:",
        PATTERN_LENGTH
    )

    print(
        "TOP MATCHES:",
        TOP_MATCHES
    )

    print(
        "MIN SCORE:",
        MIN_SCORE
    )

    print(
        "MIN PROBABILITY:",
        MIN_PROBABILITY
    )

    print(
        "MIN R/R:",
        MIN_RR
    )

    print(
        "TELEGRAM:",
        telegram_enabled()
    )

    print("=" * 70)

    thread = threading.Thread(
        target=signal_loop,
        daemon=True
    )

    thread.start()

    server = HTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        Handler
    )

    print(
        "HTTP server listening on port",
        PORT
    )

    print("=" * 70)

    server.serve_forever()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()

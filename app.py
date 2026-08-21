"""
XAUUSD M5 STATISTICAL SIGNAL + TELEGRAM
========================================

ระบบ:
- วิเคราะห์ XAUUSD M5
- Historical Pattern Matching
- EMA20 / EMA50
- RSI
- ATR
- Momentum
- Dynamic SL
- Dynamic TP
- BUY / SELL
- Telegram notification

Environment Variables:

TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
PORT

Render Start Command:

python app.py
"""

import json
import math
import statistics
import os
import time
import threading
from datetime import datetime, timezone
from urllib.request import (
    Request,
    urlopen
)
from urllib.parse import urlencode


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "XAUUSD=X",
    "GC=F"
]

INTERVAL = "5m"

LOOKBACK = 1000

PATTERN_LENGTH = 12

FORWARD_BARS = 12

MAX_MATCHES = 100

MIN_SIMILARITY = 0.78

ATR_PERIOD = 14

EMA_FAST = 20

EMA_SLOW = 50

RSI_PERIOD = 14

MIN_RR = 1.50

DEFAULT_RR = 2.00

SL_BUFFER_ATR = 0.15

MIN_SCORE = 65


# ============================================================
# TELEGRAM CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    ""
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    ""
)


# ============================================================
# SIGNAL MEMORY
# ============================================================

LAST_SIGNAL_ID = None

SIGNAL_LOCK = threading.Lock()


# ============================================================
# HTTP
# ============================================================

def http_get(url, timeout=20):

    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(
        req,
        timeout=timeout
    ) as response:

        return response.read().decode(
            "utf-8"
        )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        print(
            "Telegram disabled: "
            "TELEGRAM_BOT_TOKEN not set"
        )
        return False

    if not TELEGRAM_CHAT_ID:
        print(
            "Telegram disabled: "
            "TELEGRAM_CHAT_ID not set"
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

    }).encode("utf-8")

    try:

        req = Request(
            url,
            data=payload,

            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded"
            }
        )

        with urlopen(
            req,
            timeout=20
        ) as response:

            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        if result.get("ok"):

            print(
                "Telegram message sent"
            )

            return True

        print(
            "Telegram error:",
            result
        )

        return False

    except Exception as e:

        print(
            "Telegram exception:",
            e
        )

        return False


# ============================================================
# FORMAT TELEGRAM SIGNAL
# ============================================================

def format_signal_message(signal):

    direction = signal["signal"]

    if direction == "BUY":

        icon = "🟢"

    else:

        icon = "🔴"

    probability_key = (
        "buy_probability"
        if direction == "BUY"
        else "sell_probability"
    )

    probability = signal[
        "historical_statistics"
    ][probability_key]

    timestamp = datetime.fromisoformat(
        signal["timestamp"]
    )

    local_time = timestamp.strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    message = f"""
{icon} <b>XAUUSD M5 SIGNAL</b>

<b>สัญญาณ:</b> {direction}

<b>จุดเข้าออเดอร์:</b> {signal["entry"]}

<b>T/P:</b> {signal["take_profit"]}

<b>S/L:</b> {signal["stop_loss"]}

<b>Score:</b> {signal["score"]}

<b>Probability:</b> {probability}%

<b>RSI:</b> {signal["rsi"]}

<b>ATR:</b> {signal["atr"]}

<b>เวลา:</b> {local_time}
""".strip()

    return message


# ============================================================
# YAHOO DATA
# ============================================================

def get_yahoo_data(
    symbol,
    interval="5m",
    range_value="7d"
):

    params = urlencode({

        "range":
            range_value,

        "interval":
            interval,

        "includePrePost":
            "true",

        "events":
            "div,splits"
    })

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?"
        + params
    )

    raw = http_get(url)

    data = json.loads(raw)

    result = data[
        "chart"
    ][
        "result"
    ]

    if not result:

        raise Exception(
            "Yahoo returned no data"
        )

    result = result[0]

    timestamps = result[
        "timestamp"
    ]

    quote = result[
        "indicators"
    ][
        "quote"
    ][0]

    rows = []

    for i, ts in enumerate(
        timestamps
    ):

        o = quote[
            "open"
        ][i]

        h = quote[
            "high"
        ][i]

        l = quote[
            "low"
        ][i]

        c = quote[
            "close"
        ][i]

        volumes = quote.get(
            "volume",
            [None] * len(timestamps)
        )

        v = volumes[i]

        if None in (
            o,
            h,
            l,
            c
        ):

            continue

        rows.append({

            "time":
                datetime.fromtimestamp(
                    ts,
                    timezone.utc
                ).isoformat(),

            "timestamp":
                ts,

            "open":
                float(o),

            "high":
                float(h),

            "low":
                float(l),

            "close":
                float(c),

            "volume":
                float(v or 0)
        })

    return rows


def get_market_data():

    last_error = None

    for symbol in SYMBOLS:

        try:

            data = get_yahoo_data(
                symbol,
                INTERVAL,
                "7d"
            )

            if len(data) >= 200:

                return {

                    "symbol":
                        symbol,

                    "data":
                        data[-LOOKBACK:]
                }

        except Exception as e:

            last_error = str(e)

    raise Exception(
        "Unable to retrieve gold market data: "
        + str(last_error)
    )


# ============================================================
# MATH
# ============================================================

def mean(values):

    if not values:
        return 0.0

    return sum(values) / len(values)


def std(values):

    if len(values) < 2:
        return 0.0

    return statistics.stdev(
        values
    )


def ema(values, period):

    if not values:
        return []

    result = []

    multiplier = (
        2.0 /
        (period + 1)
    )

    current = values[0]

    result.append(current)

    for value in values[1:]:

        current = (
            (value - current)
            * multiplier
            + current
        )

        result.append(
            current
        )

    return result


# ============================================================
# RSI
# ============================================================

def rsi(
    values,
    period=14
):

    if len(values) < period + 1:

        return [
            50.0
        ] * len(values)

    result = [
        50.0
    ] * len(values)

    gains = []

    losses = []

    for i in range(
        1,
        period + 1
    ):

        change = (
            values[i]
            - values[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    avg_gain = mean(
        gains
    )

    avg_loss = mean(
        losses
    )

    if avg_loss == 0:

        result[period] = 100.0

    else:

        rs = (
            avg_gain /
            avg_loss
        )

        result[period] = (
            100
            - 100 /
            (1 + rs)
        )

    for i in range(
        period + 1,
        len(values)
    ):

        change = (
            values[i]
            - values[i - 1]
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
                * (period - 1)
                + gain
            )
            / period
        )

        avg_loss = (
            (
                avg_loss
                * (period - 1)
                + loss
            )
            / period
        )

        if avg_loss == 0:

            result[i] = 100.0

        else:

            rs = (
                avg_gain /
                avg_loss
            )

            result[i] = (
                100
                - 100 /
                (1 + rs)
            )

    return result


# ============================================================
# ATR
# ============================================================

def atr(
    data,
    period=14
):

    if len(data) < 2:

        return [
            0.0
        ] * len(data)

    tr = [0.0]

    for i in range(
        1,
        len(data)
    ):

        high = data[i][
            "high"
        ]

        low = data[i][
            "low"
        ]

        previous_close = data[
            i - 1
        ][
            "close"
        ]

        true_range = max(

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
            true_range
        )

    result = [
        0.0
    ] * len(data)

    current = mean(
        tr[
            1:
            period + 1
        ]
    )

    if period < len(result):

        result[period] = (
            current
        )

    for i in range(
        period + 1,
        len(data)
    ):

        current = (
            (
                current
                * (period - 1)
                + tr[i]
            )
            / period
        )

        result[i] = (
            current
        )

    for i in range(
        period
    ):

        result[i] = current

    return result


# ============================================================
# SWING
# ============================================================

def swing_high(
    data,
    index,
    window=5
):

    if (
        index < window
        or
        index + window >= len(data)
    ):

        return False

    value = data[index][
        "high"
    ]

    for i in range(
        index - window,
        index + window + 1
    ):

        if i == index:
            continue

        if data[i][
            "high"
        ] >= value:

            return False

    return True


def swing_low(
    data,
    index,
    window=5
):

    if (
        index < window
        or
        index + window >= len(data)
    ):

        return False

    value = data[index][
        "low"
    ]

    for i in range(
        index - window,
        index + window + 1
    ):

        if i == index:
            continue

        if data[i][
            "low"
        ] <= value:

            return False

    return True


# ============================================================
# FEATURES
# ============================================================

def build_features(data):

    closes = [
        x["close"]
        for x in data
    ]

    ema20 = ema(
        closes,
        EMA_FAST
    )

    ema50 = ema(
        closes,
        EMA_SLOW
    )

    rsis = rsi(
        closes,
        RSI_PERIOD
    )

    atrs = atr(
        data,
        ATR_PERIOD
    )

    features = []

    for i in range(
        len(data)
    ):

        close = data[i][
            "close"
        ]

        open_ = data[i][
            "open"
        ]

        high = data[i][
            "high"
        ]

        low = data[i][
            "low"
        ]

        candle_range = max(
            high - low,
            1e-9
        )

        body = abs(
            close - open_
        )

        upper_wick = (
            high
            - max(
                open_,
                close
            )
        )

        lower_wick = (
            min(
                open_,
                close
            )
            - low
        )

        momentum = 0.0

        if i >= 5:

            momentum = (
                close
                - data[
                    i - 5
                ]["close"]
            )

        atr_value = atrs[i]

        normalized_momentum = 0.0

        if atr_value > 0:

            normalized_momentum = (
                momentum
                / atr_value
            )

        features.append({

            "ema20":
                ema20[i],

            "ema50":
                ema50[i],

            "rsi":
                rsis[i],

            "atr":
                atr_value,

            "body_ratio":
                body
                / candle_range,

            "upper_wick_ratio":
                upper_wick
                / candle_range,

            "lower_wick_ratio":
                lower_wick
                / candle_range,

            "range":
                candle_range,

            "momentum":
                normalized_momentum,

            "trend":

                1
                if ema20[i]
                > ema50[i]

                else -1
        })

    return features


# ============================================================
# PATTERN
# ============================================================

def candle_vector(
    feature
):

    return [

        feature[
            "body_ratio"
        ],

        feature[
            "upper_wick_ratio"
        ],

        feature[
            "lower_wick_ratio"
        ],

        feature[
            "momentum"
        ],

        feature[
            "rsi"
        ] / 100.0,

        feature[
            "trend"
        ]
    ]


def normalize_vector(
    vector
):

    result = []

    for x in vector:

        x = max(
            -3,
            min(3, x)
        )

        result.append(
            x
        )

    return result


def vector_distance(
    a,
    b
):

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


def pattern_similarity(
    current,
    historical
):

    distance = vector_distance(
        current,
        historical
    )

    return (
        1.0 /
        (1.0 + distance)
    )


def create_pattern(
    features,
    end_index
):

    vectors = []

    start = (
        end_index
        - PATTERN_LENGTH
        + 1
    )

    if start < 0:

        return None

    for i in range(
        start,
        end_index + 1
    ):

        vectors.extend(
            candle_vector(
                features[i]
            )
        )

    return normalize_vector(
        vectors
    )


# ============================================================
# HISTORICAL MATCH
# ============================================================

def historical_patterns(
    data,
    features,
    current_index
):

    current_pattern = create_pattern(
        features,
        current_index
    )

    if current_pattern is None:

        return []

    matches = []

    minimum_index = (
        PATTERN_LENGTH
        + ATR_PERIOD
        + 10
    )

    maximum_index = (
        current_index
        - FORWARD_BARS
        - 2
    )

    for i in range(
        minimum_index,
        maximum_index
    ):

        historical_pattern = create_pattern(
            features,
            i
        )

        if historical_pattern is None:

            continue

        similarity = pattern_similarity(
            current_pattern,
            historical_pattern
        )

        if similarity < MIN_SIMILARITY:

            continue

        entry = data[i][
            "close"
        ]

        future = data[
            i + 1:
            i + 1 + FORWARD_BARS
        ]

        if not future:

            continue

        future_high = max(
            x["high"]
            for x in future
        )

        future_low = min(
            x["low"]
            for x in future
        )

        future_close = future[
            -1
        ]["close"]

        up_move = (
            future_high
            - entry
        )

        down_move = (
            entry
            - future_low
        )

        close_move = (
            future_close
            - entry
        )

        direction = (

            1
            if close_move > 0
            else -1
        )

        matches.append({

            "index":
                i,

            "similarity":
                similarity,

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
        :MAX_MATCHES
    ]


# ============================================================
# STATISTICS
# ============================================================

def calculate_statistics(
    matches,
    atr_value
):

    if (
        not matches
        or atr_value <= 0
    ):

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
                0
        }

    weighted_up = 0.0

    weighted_down = 0.0

    buy_weight = 0.0

    sell_weight = 0.0

    total_weight = 0.0

    for match in matches:

        weight = (
            match[
                "similarity"
            ] ** 3
        )

        total_weight += (
            weight
        )

        if match[
            "direction"
        ] == 1:

            buy_weight += (
                weight
            )

        else:

            sell_weight += (
                weight
            )

        weighted_up += (
            match[
                "up_move"
            ]
            / atr_value
            * weight
        )

        weighted_down += (
            match[
                "down_move"
            ]
            / atr_value
            * weight
        )

    if total_weight == 0:

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
                0
        }

    buy_probability = (
        buy_weight
        / total_weight
    )

    sell_probability = (
        sell_weight
        / total_weight
    )

    return {

        "sample_size":
            len(matches),

        "buy_probability":
            round(
                buy_probability
                * 100,
                2
            ),

        "sell_probability":
            round(
                sell_probability
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
            )
    }


# ============================================================
# MARKET STRUCTURE
# ============================================================

def find_recent_swing_high(
    data,
    index
):

    start = max(
        0,
        index - 80
    )

    for i in range(
        index - 3,
        start,
        -1
    ):

        if swing_high(
            data,
            i
        ):

            return data[i][
                "high"
            ]

    return None


def find_recent_swing_low(
    data,
    index
):

    start = max(
        0,
        index - 80
    )

    for i in range(
        index - 3,
        start,
        -1
    ):

        if swing_low(
            data,
            i
        ):

            return data[i][
                "low"
            ]

    return None


# ============================================================
# SIGNAL
# ============================================================

def generate_signal(
    data
):

    if len(data) < 200:

        raise Exception(
            "Not enough market data"
        )

    features = build_features(
        data
    )

    index = len(data) - 1

    candle = data[
        index
    ]

    f = features[
        index
    ]

    atr_value = f[
        "atr"
    ]

    if atr_value <= 0:

        return {

            "signal":
                "NO_TRADE",

            "reason":
                "ATR unavailable"
        }

    matches = historical_patterns(
        data,
        features,
        index
    )

    stats = calculate_statistics(
        matches,
        atr_value
    )

    score_buy = 0.0

    score_sell = 0.0

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if f[
        "ema20"
    ] > f[
        "ema50"
    ]:

        score_buy += 20

    else:

        score_sell += 20

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if (
        50 <= f["rsi"] <= 68
    ):

        score_buy += 15

    if (
        32 <= f["rsi"] <= 50
    ):

        score_sell += 15

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    if f[
        "momentum"
    ] > 0.3:

        score_buy += 15

    if f[
        "momentum"
    ] < -0.3:

        score_sell += 15

    # --------------------------------------------------------
    # HISTORICAL PROBABILITY
    # --------------------------------------------------------

    score_buy += (
        stats[
            "buy_probability"
        ]
        * 0.35
    )

    score_sell += (
        stats[
            "sell_probability"
        ]
        * 0.35
    )

    # --------------------------------------------------------
    # CANDLE
    # --------------------------------------------------------

    body = abs(
        candle["close"]
        - candle["open"]
    )

    bullish = (
        candle["close"]
        > candle["open"]
    )

    bearish = (
        candle["close"]
        < candle["open"]
    )

    if (
        bullish
        and body
        > atr_value * 0.25
    ):

        score_buy += 10

    if (
        bearish
        and body
        > atr_value * 0.25
    ):

        score_sell += 10

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    if (
        score_buy >= MIN_SCORE
        and
        score_buy
        > score_sell + 8
    ):

        direction = "BUY"

        score = score_buy

    elif (
        score_sell >= MIN_SCORE
        and
        score_sell
        > score_buy + 8
    ):

        direction = "SELL"

        score = score_sell

    else:

        direction = "NO_TRADE"

        score = max(
            score_buy,
            score_sell
        )

    entry = candle[
        "close"
    ]

    swing_low_value = (
        find_recent_swing_low(
            data,
            index
        )
    )

    swing_high_value = (
        find_recent_swing_high(
            data,
            index
        )
    )

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if direction == "BUY":

        atr_sl = (
            entry
            - atr_value * 1.25
        )

        if (
            swing_low_value
            is not None
        ):

            structure_sl = (
                swing_low_value
                - atr_value
                * SL_BUFFER_ATR
            )

            stop_loss = min(
                atr_sl,
                structure_sl
            )

        else:

            stop_loss = atr_sl

        risk = (
            entry
            - stop_loss
        )

        historical_target = (
            entry
            + atr_value
            * max(
                DEFAULT_RR,
                stats[
                    "expected_up_atr"
                ]
            )
        )

        target = historical_target

        if risk > 0:

            target = max(

                target,

                entry
                + risk * MIN_RR
            )

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    elif direction == "SELL":

        atr_sl = (
            entry
            + atr_value * 1.25
        )

        if (
            swing_high_value
            is not None
        ):

            structure_sl = (
                swing_high_value
                + atr_value
                * SL_BUFFER_ATR
            )

            stop_loss = max(
                atr_sl,
                structure_sl
            )

        else:

            stop_loss = atr_sl

        risk = (
            stop_loss
            - entry
        )

        historical_target = (
            entry
            - atr_value
            * max(
                DEFAULT_RR,
                stats[
                    "expected_down_atr"
                ]
            )
        )

        target = historical_target

        if risk > 0:

            target = min(

                target,

                entry
                - risk * MIN_RR
            )

    else:

        stop_loss = None

        target = None

    digits = 2

    return {

        "timestamp":
            candle[
                "time"
            ],

        "symbol":
            "XAUUSD",

        "timeframe":
            "M5",

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
                digits
            ),

        "stop_loss":
            (
                round(
                    stop_loss,
                    digits
                )
                if stop_loss
                is not None
                else None
            ),

        "take_profit":
            (
                round(
                    target,
                    digits
                )
                if target
                is not None
                else None
            ),

        "atr":
            round(
                atr_value,
                digits
            ),

        "rsi":
            round(
                f["rsi"],
                2
            ),

        "ema20":
            round(
                f["ema20"],
                digits
            ),

        "ema50":
            round(
                f["ema50"],
                digits
            ),

        "historical_statistics":
            stats,

        "matched_patterns":
            len(matches),

        "method":
            "M5 historical pattern matching"
    }


# ============================================================
# SEND ONLY NEW SIGNAL
# ============================================================

def process_signal():

    global LAST_SIGNAL_ID

    try:

        market = get_market_data()

        data = market[
            "data"
        ]

        signal = generate_signal(
            data
        )

        print(
            json.dumps(
                signal,
                ensure_ascii=False,
                indent=2
            )
        )

        if signal[
            "signal"
        ] not in (
            "BUY",
            "SELL"
        ):

            return signal

        # ----------------------------------------------------
        # SIGNAL ID
        # ----------------------------------------------------

        signal_id = (
            signal["timestamp"]
            + "_"
            + signal["signal"]
        )

        with SIGNAL_LOCK:

            if (
                signal_id
                == LAST_SIGNAL_ID
            ):

                print(
                    "Signal already sent"
                )

                return signal

            LAST_SIGNAL_ID = signal_id

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        message = (
            format_signal_message(
                signal
            )
        )

        send_telegram(
            message
        )

        return signal

    except Exception as e:

        print(
            "Signal error:",
            e
        )

        return {

            "signal":
                "ERROR",

            "error":
                str(e)
        }


# ============================================================
# BACKGROUND SIGNAL LOOP
# ============================================================

def signal_loop():

    print(
        "Starting signal loop..."
    )

    while True:

        try:

            process_signal()

        except Exception as e:

            print(
                "Loop error:",
                e
            )

        # M5
        # ตรวจประมาณทุก 60 วินาที

        time.sleep(
            60
        )


# ============================================================
# BACKTEST
# ============================================================

def backtest(data):

    if len(data) < 400:

        return {

            "error":
                "Not enough data"
        }

    features = build_features(
        data
    )

    trades = []

    start = 250

    end = (
        len(data)
        - FORWARD_BARS
        - 1
    )

    for i in range(
        start,
        end
    ):

        matches = historical_patterns(
            data,
            features,
            i
        )

        if not matches:

            continue

        atr_value = features[
            i
        ][
            "atr"
        ]

        stats = calculate_statistics(
            matches,
            atr_value
        )

        if (
            stats[
                "buy_probability"
            ] >= 62
            and
            stats[
                "buy_probability"
            ]
            >
            stats[
                "sell_probability"
            ] + 8
        ):

            direction = "BUY"

        elif (
            stats[
                "sell_probability"
            ] >= 62
            and
            stats[
                "sell_probability"
            ]
            >
            stats[
                "buy_probability"
            ] + 8
        ):

            direction = "SELL"

        else:

            continue

        entry = data[
            i
        ][
            "close"
        ]

        if direction == "BUY":

            sl = (
                entry
                - atr_value * 1.25
            )

            tp = (
                entry
                + (
                    entry
                    - sl
                )
                * DEFAULT_RR
            )

        else:

            sl = (
                entry
                + atr_value * 1.25
            )

            tp = (
                entry
                - (
                    sl
                    - entry
                )
                * DEFAULT_RR
            )

        result = "OPEN"

        exit_price = None

        for j in range(

            i + 1,

            min(
                i + 1
                + FORWARD_BARS,

                len(data)
            )
        ):

            high = data[
                j
            ][
                "high"
            ]

            low = data[
                j
            ][
                "low"
            ]

            if direction == "BUY":

                if low <= sl:

                    result = "LOSS"

                    exit_price = sl

                    break

                if high >= tp:

                    result = "WIN"

                    exit_price = tp

                    break

            else:

                if high >= sl:

                    result = "LOSS"

                    exit_price = sl

                    break

                if low <= tp:

                    result = "WIN"

                    exit_price = tp

                    break

        if result == "OPEN":

            continue

        trades.append({

            "index":
                i,

            "direction":
                direction,

            "entry":
                entry,

            "sl":
                sl,

            "tp":
                tp,

            "result":
                result
        })

    wins = sum(

        1

        for x in trades

        if x[
            "result"
        ] == "WIN"
    )

    losses = sum(

        1

        for x in trades

        if x[
            "result"
        ] == "LOSS"
    )

    total = (
        wins
        + losses
    )

    win_rate = (

        wins
        / total
        * 100

        if total > 0

        else 0
    )

    return {

        "bars":
            len(data),

        "trades":
            total,

        "wins":
            wins,

        "losses":
            losses,

        "win_rate":
            round(
                win_rate,
                2
            ),

        "risk_reward":
            DEFAULT_RR
    }


# ============================================================
# WEB SERVER
# ============================================================

from http.server import (
    BaseHTTPRequestHandler,
    HTTPServer
)


class Handler(
    BaseHTTPRequestHandler
):

    def send_json(
        self,
        payload
    ):

        body = json.dumps(

            payload,

            ensure_ascii=False,

            indent=2
        ).encode(
            "utf-8"
        )

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def do_GET(self):

        try:

            if self.path == "/":

                self.send_json({

                    "name":
                        "XAUUSD M5 Telegram Signal",

                    "status":
                        "online",

                    "endpoints": [

                        "/signal",

                        "/backtest",

                        "/health"

                    ]
                })

                return

            if self.path == "/health":

                self.send_json({

                    "status":
                        "healthy",

                    "telegram":
                        bool(
                            TELEGRAM_BOT_TOKEN
                            and
                            TELEGRAM_CHAT_ID
                        ),

                    "time":
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                })

                return

            if self.path == "/signal":

                result = process_signal()

                self.send_json(
                    result
                )

                return

            if self.path == "/backtest":

                market = (
                    get_market_data()
                )

                result = backtest(
                    market["data"]
                )

                result[
                    "data_source"
                ] = market[
                    "symbol"
                ]

                self.send_json(
                    result
                )

                return

            self.send_response(
                404
            )

            self.end_headers()

        except Exception as e:

            self.send_response(
                500
            )

            body = json.dumps({

                "error":
                    str(e)

            }).encode(
                "utf-8"
            )

            self.send_header(
                "Content-Type",
                "application/json"
            )

            self.send_header(
                "Content-Length",
                str(len(body))
            )

            self.end_headers()

            self.wfile.write(
                body
            )


# ============================================================
# MAIN
# ============================================================

def main():

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    # --------------------------------------------------------
    # START TELEGRAM SIGNAL LOOP
    # --------------------------------------------------------

    thread = threading.Thread(
        target=signal_loop,
        daemon=True
    )

    thread.start()

    # --------------------------------------------------------
    # WEB SERVER
    # --------------------------------------------------------

    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        Handler
    )

    print("=" * 60)

    print(
        "XAUUSD M5 TELEGRAM SIGNAL ENGINE"
    )

    print("=" * 60)

    print(
        "PORT:",
        port
    )

    print(
        "TIMEFRAME:",
        INTERVAL
    )

    print(
        "TELEGRAM:",
        bool(
            TELEGRAM_BOT_TOKEN
            and
            TELEGRAM_CHAT_ID
        )
    )

    print("=" * 60)

    server.serve_forever()


if __name__ == "__main__":

    main()

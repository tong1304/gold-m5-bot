import os
import json
import math
import time
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from http.server import BaseHTTPRequestHandler, HTTPServer


# ============================================================
# CONFIG
# ============================================================

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"

PORT = int(os.environ.get("PORT", "10000"))

TWELVE_DATA_API_KEY = os.environ.get(
    "TWELVE_DATA_API_KEY",
    ""
).strip()

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    ""
).strip()


# Pattern settings
CANDLE_HISTORY = int(
    os.environ.get("CANDLE_HISTORY", "1000")
)

PATTERN_LENGTH = int(
    os.environ.get("PATTERN_LENGTH", "12")
)

TOP_MATCHES = int(
    os.environ.get("TOP_MATCHES", "40")
)

MIN_MATCHES = int(
    os.environ.get("MIN_MATCHES", "10")
)

MIN_SCORE = float(
    os.environ.get("MIN_SCORE", "68")
)

MIN_PROBABILITY = float(
    os.environ.get("MIN_PROBABILITY", "60")
)

MIN_RR = float(
    os.environ.get("MIN_RR", "1.5")
)

FORWARD_BARS = int(
    os.environ.get("FORWARD_BARS", "12")
)

POLL_SECONDS = int(
    os.environ.get("POLL_SECONDS", "60")
)

# Risk settings
SL_ATR_MULTIPLIER = float(
    os.environ.get("SL_ATR_MULTIPLIER", "1.25")
)

TP_ATR_MULTIPLIER = float(
    os.environ.get("TP_ATR_MULTIPLIER", "2.0")
)


# ============================================================
# GLOBAL STATE
# ============================================================

CACHE = {
    "candles": [],
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "telegram_sent": False,
    "error": None,
}

LOCK = threading.Lock()


# ============================================================
# HTTP GET
# ============================================================

def http_get(url, timeout=30):

    request = Request(
        url,
        headers={
            "User-Agent":
                "XAUUSD-M5-Signal-Bot/1.0"
        }
    )

    with urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read().decode(
            "utf-8"
        )


# ============================================================
# TWELVE DATA
# ============================================================

def twelve_data_request(
    interval="5min",
    outputsize=1000
):

    if not TWELVE_DATA_API_KEY:

        raise Exception(
            "TWELVE_DATA_API_KEY is not configured"
        )

    params = urlencode({

        "symbol":
            SYMBOL,

        "interval":
            interval,

        "outputsize":
            outputsize,

        "timezone":
            "UTC",

        "apikey":
            TWELVE_DATA_API_KEY

    })

    url = (
        "https://api.twelvedata.com/time_series?"
        + params
    )

    raw = http_get(
        url
    )

    data = json.loads(
        raw
    )

    if data.get("status") == "error":

        raise Exception(
            data.get(
                "message",
                "Twelve Data API error"
            )
        )

    values = data.get(
        "values",
        []
    )

    if not values:

        raise Exception(
            "Twelve Data returned no candle data"
        )

    candles = []

    for row in values:

        try:

            candles.append({

                "time":
                    str(
                        row["datetime"]
                    ),

                "open":
                    float(
                        row["open"]
                    ),

                "high":
                    float(
                        row["high"]
                    ),

                "low":
                    float(
                        row["low"]
                    ),

                "close":
                    float(
                        row["close"]
                    ),

                "volume":
                    float(
                        row.get(
                            "volume",
                            0
                        ) or 0
                    )
            })

        except Exception:

            continue

    candles.sort(
        key=lambda x:
            x["time"]
    )

    return candles


# ============================================================
# GET MARKET DATA
# ============================================================

def get_market_data():

    candles = twelve_data_request(
        interval=TIMEFRAME,
        outputsize=CANDLE_HISTORY
    )

    if len(candles) < 250:

        raise Exception(
            "Not enough XAU/USD M5 candles"
        )

    # Remove duplicate timestamps
    unique = {}

    for candle in candles:

        unique[
            candle["time"]
        ] = candle

    candles = list(
        unique.values()
    )

    candles.sort(
        key=lambda x:
            x["time"]
    )

    return candles[
        -CANDLE_HISTORY:
    ]


# ============================================================
# MATH
# ============================================================

def mean(values):

    if not values:

        return 0.0

    return sum(
        values
    ) / len(values)


def ema(values, period):

    if not values:

        return []

    alpha = (
        2.0
        / (
            period
            + 1
        )
    )

    result = [
        values[0]
    ]

    current = values[0]

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

    if len(closes) <= period:

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

    for i in range(
        period,
        len(closes)
    ):

        if i > period:

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
                )
                + gain
            ) / period

            avg_loss = (
                (
                    avg_loss
                    * (
                        period - 1
                    )
                )
                + loss
            ) / period

        if avg_loss == 0:

            result[i] = 100.0

        else:

            rs = (
                avg_gain
                / avg_loss
            )

            result[i] = (
                100
                - (
                    100
                    / (
                        1
                        + rs
                    )
                )
            )

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=14
):

    if len(candles) < period + 2:

        return [
            0.0
        ] * len(candles)

    tr = [
        0.0
    ]

    for i in range(
        1,
        len(candles)
    ):

        high = candles[i]["high"]
        low = candles[i]["low"]

        previous_close = (
            candles[i - 1]["close"]
        )

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

    atr = [
        0.0
    ] * len(candles)

    current = mean(
        tr[
            1:
            period + 1
        ]
    )

    atr[period] = current

    for i in range(
        period + 1,
        len(candles)
    ):

        current = (
            (
                current
                * (
                    period - 1
                )
            )
            + tr[i]
        ) / period

        atr[i] = current

    return atr


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(
    candles
):

    closes = [
        c["close"]
        for c in candles
    ]

    ema20 = ema(
        closes,
        20
    )

    ema50 = ema(
        closes,
        50
    )

    rsi = calculate_rsi(
        closes,
        14
    )

    atr = calculate_atr(
        candles,
        14
    )

    indicators = []

    for i in range(
        len(candles)
    ):

        momentum = 0.0

        if i >= 5 and atr[i] > 0:

            momentum = (
                closes[i]
                - closes[i - 5]
            ) / atr[i]

        indicators.append({

            "ema20":
                ema20[i],

            "ema50":
                ema50[i],

            "rsi":
                rsi[i],

            "atr":
                atr[i],

            "momentum":
                momentum
        })

    return indicators


# ============================================================
# CANDLE FEATURE
# ============================================================

def candle_feature(candle):

    o = candle["open"]
    h = candle["high"]
    l = candle["low"]
    c = candle["close"]

    rng = max(
        h - l,
        0.000001
    )

    body = (
        abs(
            c - o
        )
        / rng
    )

    upper_wick = (
        h
        - max(
            o,
            c
        )
    ) / rng

    lower_wick = (
        min(
            o,
            c
        )
        - l
    ) / rng

    direction = (
        1.0
        if c > o
        else -1.0
        if c < o
        else 0.0
    )

    return [

        body,

        upper_wick,

        lower_wick,

        direction
    ]


# ============================================================
# PATTERN VECTOR
# ============================================================

def build_pattern_vector(
    candles,
    indicators,
    index
):

    start = (
        index
        - PATTERN_LENGTH
        + 1
    )

    if start < 0:

        return None

    vector = []

    for i in range(
        start,
        index + 1
    ):

        vector.extend(
            candle_feature(
                candles[i]
            )
        )

        vector.append(
            max(
                -3.0,
                min(
                    3.0,
                    indicators[i][
                        "momentum"
                    ]
                )
            )
        )

        vector.append(
            indicators[i][
                "rsi"
            ] / 100.0
        )

        vector.append(

            1.0

            if
            indicators[i][
                "ema20"
            ]
            >
            indicators[i][
                "ema50"
            ]

            else

            -1.0
        )

    return vector


# ============================================================
# DISTANCE / SIMILARITY
# ============================================================

def distance(a, b):

    if (
        a is None
        or
        b is None
        or
        len(a) != len(b)
    ):

        return 999999.0

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


def similarity(a, b):

    d = distance(
        a,
        b
    )

    return (
        1.0
        / (
            1.0
            + d
        )
    )


# ============================================================
# HISTORICAL PATTERN MATCHING
# ============================================================

def find_matches(
    candles,
    indicators,
    current_index
):

    current_vector = (
        build_pattern_vector(
            candles,
            indicators,
            current_index
        )
    )

    if current_vector is None:

        return []

    matches = []

    first = (
        PATTERN_LENGTH
        + 30
    )

    last = (
        current_index
        - FORWARD_BARS
        - 1
    )

    # Limit scan to prevent excessive CPU
    first = max(
        first,
        last - 900
    )

    for i in range(
        first,
        last + 1
    ):

        historical_vector = (
            build_pattern_vector(
                candles,
                indicators,
                i
            )
        )

        if historical_vector is None:

            continue

        sim = similarity(
            current_vector,
            historical_vector
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

        highest = max(
            c["high"]
            for c in future
        )

        lowest = min(
            c["low"]
            for c in future
        )

        final_close = future[
            -1
        ][
            "close"
        ]

        up_move = (
            highest
            - entry
        )

        down_move = (
            entry
            - lowest
        )

        close_move = (
            final_close
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

            "direction":
                direction,

            "up_move":
                up_move,

            "down_move":
                down_move,

            "close_move":
                close_move
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
# STATISTICS
# ============================================================

def calculate_statistics(
    matches,
    atr
):

    if len(matches) < MIN_MATCHES:

        return {

            "sample_size":
                len(matches),

            "buy_probability":
                0.0,

            "sell_probability":
                0.0,

            "expected_up_atr":
                0.0,

            "expected_down_atr":
                0.0,

            "average_similarity":
                0.0,

            "best_similarity":
                0.0
        }

    buy_weight = 0.0
    sell_weight = 0.0

    total_weight = 0.0

    up_weighted = 0.0
    down_weighted = 0.0

    similarities = []

    for match in matches:

        weight = (
            match["similarity"]
            ** 3
        )

        total_weight += weight

        similarities.append(
            match["similarity"]
        )

        if match[
            "direction"
        ] == "BUY":

            buy_weight += weight

        else:

            sell_weight += weight

        if atr > 0:

            up_weighted += (
                match["up_move"]
                / atr
                * weight
            )

            down_weighted += (
                match["down_move"]
                / atr
                * weight
            )

    if total_weight == 0:

        return {

            "sample_size":
                len(matches),

            "buy_probability":
                0.0,

            "sell_probability":
                0.0,

            "expected_up_atr":
                0.0,

            "expected_down_atr":
                0.0,

            "average_similarity":
                0.0,

            "best_similarity":
                0.0
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
                up_weighted
                / total_weight,
                3
            ),

        "expected_down_atr":
            round(
                down_weighted
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
# SWING HIGH / LOW
# ============================================================

def swing_low(
    candles,
    index,
    lookback=60
):

    start = max(
        0,
        index - lookback
    )

    values = [
        c["low"]
        for c in candles[
            start:index
        ]
    ]

    if not values:

        return None

    return min(
        values
    )


def swing_high(
    candles,
    index,
    lookback=60
):

    start = max(
        0,
        index - lookback
    )

    values = [
        c["high"]
        for c in candles[
            start:index
        ]
    ]

    if not values:

        return None

    return max(
        values
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(
    candles
):

    indicators = calculate_indicators(
        candles
    )

    index = len(
        candles
    ) - 1

    candle = candles[
        index
    ]

    ind = indicators[
        index
    ]

    entry = candle[
        "close"
    ]

    atr = ind[
        "atr"
    ]

    if atr <= 0:

        raise Exception(
            "ATR unavailable"
        )

    matches = find_matches(
        candles,
        indicators,
        index
    )

    stats = calculate_statistics(
        matches,
        atr
    )

    buy_score = 0.0
    sell_score = 0.0

    # --------------------------------------------------------
    # EMA TREND
    # --------------------------------------------------------

    if ind[
        "ema20"
    ] > ind[
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

    if 50 <= ind["rsi"] <= 68:

        buy_score += 12

    elif 32 <= ind["rsi"] < 50:

        sell_score += 12

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    if ind[
        "momentum"
    ] > 0.25:

        buy_score += 12

    elif ind[
        "momentum"
    ] < -0.25:

        sell_score += 12

    # --------------------------------------------------------
    # CANDLE DIRECTION
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
    # SELECT DIRECTION
    # --------------------------------------------------------

    if (
        len(matches) >= MIN_MATCHES
        and
        buy_score >= MIN_SCORE
        and
        buy_score > sell_score + 5
        and
        stats[
            "buy_probability"
        ] >= MIN_PROBABILITY
    ):

        signal = "BUY"

    elif (
        len(matches) >= MIN_MATCHES
        and
        sell_score >= MIN_SCORE
        and
        sell_score > buy_score + 5
        and
        stats[
            "sell_probability"
        ] >= MIN_PROBABILITY
    ):

        signal = "SELL"

    else:

        signal = "NO_TRADE"

    score = max(
        buy_score,
        sell_score
    )

    # --------------------------------------------------------
    # SL / TP
    # --------------------------------------------------------

    if signal == "BUY":

        structural_sl = swing_low(
            candles,
            index
        )

        atr_sl = (
            entry
            - atr
            * SL_ATR_MULTIPLIER
        )

        if structural_sl:

            stop_loss = min(
                atr_sl,
                structural_sl
                - atr * 0.10
            )

        else:

            stop_loss = atr_sl

        risk = (
            entry
            - stop_loss
        )

        statistical_target = (
            entry
            + atr
            * max(
                TP_ATR_MULTIPLIER,
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

    elif signal == "SELL":

        structural_sl = swing_high(
            candles,
            index
        )

        atr_sl = (
            entry
            + atr
            * SL_ATR_MULTIPLIER
        )

        if structural_sl:

            stop_loss = max(
                atr_sl,
                structural_sl
                + atr * 0.10
            )

        else:

            stop_loss = atr_sl

        risk = (
            stop_loss
            - entry
        )

        statistical_target = (
            entry
            - atr
            * max(
                TP_ATR_MULTIPLIER,
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
    # R/R
    # --------------------------------------------------------

    if (
        signal == "BUY"
        and
        risk
        and
        risk > 0
    ):

        rr = (
            take_profit
            - entry
        ) / risk

    elif (
        signal == "SELL"
        and
        risk
        and
        risk > 0
    ):

        rr = (
            entry
            - take_profit
        ) / risk

    else:

        rr = None

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {

        "timestamp":
            candle["time"],

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "signal":
            signal,

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
                atr,
                2
            ),

        "rsi":
            round(
                ind["rsi"],
                2
            ),

        "ema20":
            round(
                ind["ema20"],
                2
            ),

        "ema50":
            round(
                ind["ema50"],
                2
            ),

        "momentum":
            round(
                ind["momentum"],
                3
            ),

        "trend":
            (
                "BULLISH"
                if
                ind["ema20"]
                >
                ind["ema50"]
                else
                "BEARISH"
            ),

        "historical_statistics":
            stats,

        "matched_patterns":
            len(matches),

        "method":
            "M5 historical pattern matching",

        "data_source":
            "Twelve Data XAU/USD"
    }


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
    result
):

    if not telegram_enabled():

        return False

    signal = result[
        "signal"
    ]

    if signal == "BUY":

        icon = "🟢"

    elif signal == "SELL":

        icon = "🔴"

    else:

        return False

    stats = result[
        "historical_statistics"
    ]

    message = f"""
{icon} <b>XAUUSD M5 SIGNAL</b>

<b>Signal:</b> {signal}

<b>Entry:</b> {result["entry"]}

<b>T/P:</b> {result["take_profit"]}

<b>S/L:</b> {result["stop_loss"]}

<b>R/R:</b> {result["risk_reward"]}

<b>Score:</b> {result["score"]}

<b>BUY Probability:</b> {stats["buy_probability"]}%

<b>SELL Probability:</b> {stats["sell_probability"]}%

<b>Historical Matches:</b> {stats["sample_size"]}

<b>Expected Up:</b> {stats["expected_up_atr"]} ATR

<b>Expected Down:</b> {stats["expected_down_atr"]} ATR

<b>RSI:</b> {result["rsi"]}

<b>ATR:</b> {result["atr"]}

<b>EMA20:</b> {result["ema20"]}

<b>EMA50:</b> {result["ema50"]}

<b>Trend:</b> {result["trend"]}

<b>Time:</b> {result["timestamp"]}
""".strip()

    params = urlencode({

        "chat_id":
            TELEGRAM_CHAT_ID,

        "text":
            message,

        "parse_mode":
            "HTML"

    }).encode(
        "utf-8"
    )

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    request = Request(
        url,
        data=params,
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

            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        return bool(
            data.get("ok")
        )

    except Exception as error:

        print(
            "Telegram error:",
            error
        )

        return False


# ============================================================
# PROCESS
# ============================================================

def run_signal():

    global CACHE

    candles = get_market_data()

    result = generate_signal(
        candles
    )

    with LOCK:

        CACHE[
            "candles"
        ] = candles

        CACHE[
            "last_update"
        ] = datetime.now(
            timezone.utc
        ).isoformat()

        CACHE[
            "error"
        ] = None

    # --------------------------------------------------------
    # Telegram only once per signal/candle
    # --------------------------------------------------------

    if result[
        "signal"
    ] in (
        "BUY",
        "SELL"
    ):

        signal_key = (
            result["timestamp"]
            + "_"
            + result["signal"]
        )

        with LOCK:

            already_sent = (
                CACHE[
                    "last_signal_key"
                ]
                == signal_key
            )

        if not already_sent:

            sent = send_telegram(
                result
            )

            with LOCK:

                CACHE[
                    "last_signal_key"
                ] = signal_key

                CACHE[
                    "telegram_sent"
                ] = sent

    with LOCK:

        CACHE[
            "last_signal"
        ] = result

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )

    return result


# ============================================================
# BACKGROUND LOOP
# ============================================================

def background_loop():

    print(
        "Background signal engine started"
    )

    while True:

        try:

            run_signal()

        except Exception as error:

            print(
                "Background error:",
                repr(error)
            )

            with LOCK:

                CACHE[
                    "error"
                ] = str(error)

        time.sleep(
            POLL_SECONDS
        )


# ============================================================
# HTTP SERVER
# ============================================================

class Handler(
    BaseHTTPRequestHandler
):

    def send_json(
        self,
        data,
        status=200
    ):

        body = json.dumps(
            data,
            indent=2,
            ensure_ascii=False
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

    def do_HEAD(self):

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

    def do_GET(self):

        path = self.path.split(
            "?",
            1
        )[0]

        print(
            "GET",
            self.path
        )

        try:

            # ------------------------------------------------
            # HOME
            # ------------------------------------------------

            if path == "/":

                self.send_json({

                    "name":
                        "XAUUSD M5 Real-Time Statistical Signal",

                    "status":
                        "online",

                    "symbol":
                        SYMBOL,

                    "timeframe":
                        "M5",

                    "data_source":
                        "Twelve Data",

                    "telegram":
                        telegram_enabled(),

                    "endpoints": [

                        "/",

                        "/signal",

                        "/health",

                        "/backtest"

                    ]
                })

                return

            # ------------------------------------------------
            # HEALTH
            # ------------------------------------------------

            if path == "/health":

                with LOCK:

                    candle_count = len(
                        CACHE[
                            "candles"
                        ]
                    )

                    last_update = (
                        CACHE[
                            "last_update"
                        ]
                    )

                    last_signal = (
                        CACHE[
                            "last_signal"
                        ]
                    )

                    error = (
                        CACHE[
                            "error"
                        ]
                    )

                self.send_json({

                    "status":
                        "healthy",

                    "data_source":
                        "Twelve Data",

                    "symbol":
                        SYMBOL,

                    "timeframe":
                        "M5",

                    "candles":
                        candle_count,

                    "telegram":
                        telegram_enabled(),

                    "last_update":
                        last_update,

                    "last_signal":
                        last_signal,

                    "error":
                        error
                })

                return

            # ------------------------------------------------
            # SIGNAL
            # ------------------------------------------------

            if path == "/signal":

                result = run_signal()

                self.send_json(
                    result
                )

                return

            # ------------------------------------------------
            # BACKTEST
            # ------------------------------------------------

            if path == "/backtest":

                candles = get_market_data()

                if len(candles) < 500:

                    raise Exception(
                        "Not enough data for backtest"
                    )

                indicators = (
                    calculate_indicators(
                        candles
                    )
                )

                wins = 0
                losses = 0
                trades = 0

                start = max(
                    300,
                    PATTERN_LENGTH
                    + 50
                )

                end = (
                    len(candles)
                    - FORWARD_BARS
                    - 1
                )

                for i in range(
                    start,
                    end
                ):

                    matches = find_matches(
                        candles,
                        indicators,
                        i
                    )

                    if len(
                        matches
                    ) < MIN_MATCHES:

                        continue

                    atr = indicators[
                        i
                    ][
                        "atr"
                    ]

                    stats = calculate_statistics(
                        matches,
                        atr
                    )

                    if (
                        stats[
                            "buy_probability"
                        ]
                        >=
                        MIN_PROBABILITY
                        and
                        stats[
                            "buy_probability"
                        ]
                        >
                        stats[
                            "sell_probability"
                        ]
                        + 5
                    ):

                        direction = "BUY"

                    elif (
                        stats[
                            "sell_probability"
                        ]
                        >=
                        MIN_PROBABILITY
                        and
                        stats[
                            "sell_probability"
                        ]
                        >
                        stats[
                            "buy_probability"
                        ]
                        + 5
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

                        sl = (
                            entry
                            - atr
                            * SL_ATR_MULTIPLIER
                        )

                        tp = (
                            entry
                            + (
                                entry
                                - sl
                            )
                            * MIN_RR
                        )

                    else:

                        sl = (
                            entry
                            + atr
                            * SL_ATR_MULTIPLIER
                        )

                        tp = (
                            entry
                            - (
                                sl
                                - entry
                            )
                            * MIN_RR
                        )

                    outcome = None

                    for j in range(
                        i + 1,
                        min(
                            i
                            + 1
                            + FORWARD_BARS,
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

                            if low <= sl:

                                outcome = "LOSS"

                                break

                            if high >= tp:

                                outcome = "WIN"

                                break

                        else:

                            if high >= sl:

                                outcome = "LOSS"

                                break

                            if low <= tp:

                                outcome = "WIN"

                                break

                    if outcome is None:

                        continue

                    trades += 1

                    if outcome == "WIN":

                        wins += 1

                    else:

                        losses += 1

                win_rate = (

                    wins
                    / trades
                    * 100

                    if trades > 0

                    else 0
                )

                self.send_json({

                    "symbol":
                        SYMBOL,

                    "timeframe":
                        "M5",

                    "data_source":
                        "Twelve Data",

                    "candles":
                        len(candles),

                    "trades":
                        trades,

                    "wins":
                        wins,

                    "losses":
                        losses,

                    "win_rate":
                        round(
                            win_rate,
                            2
                        ),

                    "warning":
                        "Historical backtest results do not guarantee future performance."
                })

                return

            # ------------------------------------------------
            # 404
            # ------------------------------------------------

            self.send_json({

                "error":
                    "Endpoint not found",

                "available_endpoints": [

                    "/",

                    "/signal",

                    "/health",

                    "/backtest"

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
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "XAUUSD M5 REAL-TIME STATISTICAL SIGNAL ENGINE"
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
        "M5"
    )

    print(
        "DATA SOURCE:",
        "Twelve Data"
    )

    print(
        "API KEY:",
        bool(
            TWELVE_DATA_API_KEY
        )
    )

    print(
        "TELEGRAM:",
        telegram_enabled()
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
        "POLL:",
        POLL_SECONDS,
        "seconds"
    )

    print("=" * 70)

    # Start background engine
    thread = threading.Thread(
        target=background_loop,
        daemon=True
    )

    thread.start()

    # Start web server
    server = HTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        Handler
    )

    print(
        "Server listening on:",
        PORT
    )

    server.serve_forever()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()

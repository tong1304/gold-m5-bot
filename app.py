import os
import math
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify


# ============================================================
# APP
# ============================================================

app = Flask(__name__)


# ============================================================
# ENVIRONMENT
# ============================================================

TWELVE_DATA_API_KEY = os.getenv(
    "TWELVE_DATA_API_KEY",
    ""
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()


# ============================================================
# CONFIGURATION
# ============================================================

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"

CANDLE_LIMIT = 1000

PATTERN_LENGTH = 12

MAX_MATCHES = 40

MIN_SIMILARITY = 0.60


# ============================================================
# SIGNAL RULES
# ============================================================

MIN_PROBABILITY = 70.0

MIN_SCORE = 65.0

MIN_MATCHES = 20


# ============================================================
# BACKTEST
# ============================================================

FORWARD_BARS = 12

MAX_BACKTEST_POINTS = 150


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
}

STARTUP_NOTIFICATION_SENT = False


# ============================================================
# TIME
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


# ============================================================
# NUMBER
# ============================================================

def round_price(value):

    return round(
        float(value),
        2
    )


# ============================================================
# TWELVE DATA
# ============================================================

def get_candles():

    if not TWELVE_DATA_API_KEY:

        raise RuntimeError(
            "TWELVE_DATA_API_KEY is not configured"
        )

    url = (
        "https://api.twelvedata.com/"
        "time_series"
    )

    params = {
        "symbol": SYMBOL,
        "interval": TIMEFRAME,
        "outputsize": CANDLE_LIMIT,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
        "timezone": "UTC",
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") == "error":

        raise RuntimeError(
            data.get(
                "message",
                "Twelve Data API error"
            )
        )

    values = data.get(
        "values"
    )

    if not values:

        raise RuntimeError(
            "No candle data received"
        )

    candles = []

    for item in values:

        try:

            candles.append({
                "datetime": item[
                    "datetime"
                ],
                "open": float(
                    item["open"]
                ),
                "high": float(
                    item["high"]
                ),
                "low": float(
                    item["low"]
                ),
                "close": float(
                    item["close"]
                )
            })

        except Exception:

            continue

    candles.reverse()

    minimum_required = (
        PATTERN_LENGTH * 2
        + 20
    )

    if len(candles) < minimum_required:

        raise RuntimeError(
            "Not enough M5 candles"
        )

    return candles


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=14
):

    if len(candles) <= period:

        return 0.0

    true_ranges = []

    for i in range(
        1,
        len(candles)
    ):

        current = candles[i]

        previous = candles[
            i - 1
        ]

        high = current[
            "high"
        ]

        low = current[
            "low"
        ]

        previous_close = previous[
            "close"
        ]

        tr1 = high - low

        tr2 = abs(
            high
            - previous_close
        )

        tr3 = abs(
            low
            - previous_close
        )

        true_range = max(
            tr1,
            tr2,
            tr3
        )

        true_ranges.append(
            true_range
        )

    recent = true_ranges[
        -period:
    ]

    if not recent:

        return 0.0

    return (
        sum(recent)
        / len(recent)
    )


# ============================================================
# CREATE NORMALIZED PATTERN
# ============================================================

def make_pattern(
    candles
):

    if len(candles) < PATTERN_LENGTH:

        return None

    window = candles[
        -PATTERN_LENGTH:
    ]

    first_close = window[
        0
    ]["close"]

    if first_close <= 0:

        return None

    pattern = []

    for candle in window:

        value = (
            candle["close"]
            / first_close
            - 1.0
        )

        pattern.append(
            value
        )

    return pattern


# ============================================================
# PATTERN SIMILARITY
# ============================================================

def pattern_similarity(
    pattern_a,
    pattern_b
):

    if (
        not pattern_a
        or not pattern_b
    ):

        return 0.0

    if len(pattern_a) != len(
        pattern_b
    ):

        return 0.0

    squared = 0.0

    for a, b in zip(
        pattern_a,
        pattern_b
    ):

        difference = (
            a - b
        )

        squared += (
            difference
            * difference
        )

    mse = (
        squared
        / len(pattern_a)
    )

    distance = math.sqrt(
        mse
    )

    similarity = math.exp(
        -distance * 25.0
    )

    return max(
        0.0,
        min(
            1.0,
            similarity
        )
    )


# ============================================================
# HISTORICAL MATCHING
# ============================================================

def find_matches(
    candles
):

    current_pattern = make_pattern(
        candles
    )

    if current_pattern is None:

        return []

    matches = []

    last_index = (
        len(candles)
        - PATTERN_LENGTH
        - 1
    )

    for i in range(
        PATTERN_LENGTH,
        last_index + 1
    ):

        historical_window = candles[
            i - PATTERN_LENGTH:i
        ]

        historical_pattern = (
            make_pattern(
                historical_window
            )
        )

        if historical_pattern is None:

            continue

        similarity = (
            pattern_similarity(
                current_pattern,
                historical_pattern
            )
        )

        if similarity < MIN_SIMILARITY:

            continue

        historical_close = candles[
            i - 1
        ]["close"]

        future_close = candles[
            i
        ]["close"]

        if historical_close <= 0:

            continue

        movement_percent = (
            (
                future_close
                - historical_close
            )
            / historical_close
        ) * 100.0

        if movement_percent > 0:

            direction = "BUY"

        elif movement_percent < 0:

            direction = "SELL"

        else:

            direction = "FLAT"

        matches.append({

            "index":
                i,

            "similarity":
                similarity,

            "movement_percent":
                movement_percent,

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
# HISTORICAL STATISTICS
# ============================================================

def historical_statistics(
    matches
):

    if not matches:

        return {

            "sample_size":
                0,

            "buy_probability":
                0.0,

            "sell_probability":
                0.0,

            "flat_probability":
                0.0,

            "average_similarity":
                0.0,

            "best_similarity":
                0.0,

            "expected_up_percent":
                0.0,

            "expected_down_percent":
                0.0
        }

    buy_count = 0
    sell_count = 0
    flat_count = 0

    similarities = []

    up_moves = []
    down_moves = []

    for match in matches:

        direction = match[
            "direction"
        ]

        similarity = match[
            "similarity"
        ]

        movement = match[
            "movement_percent"
        ]

        similarities.append(
            similarity
        )

        if direction == "BUY":

            buy_count += 1

            if movement > 0:

                up_moves.append(
                    movement
                )

        elif direction == "SELL":

            sell_count += 1

            if movement < 0:

                down_moves.append(
                    abs(movement)
                )

        else:

            flat_count += 1

    total = len(matches)

    buy_probability = (
        buy_count
        / total
        * 100.0
    )

    sell_probability = (
        sell_count
        / total
        * 100.0
    )

    flat_probability = (
        flat_count
        / total
        * 100.0
    )

    average_similarity = (
        sum(similarities)
        / len(similarities)
    )

    best_similarity = max(
        similarities
    )

    expected_up = (
        sum(up_moves)
        / len(up_moves)
        if up_moves
        else 0.0
    )

    expected_down = (
        sum(down_moves)
        / len(down_moves)
        if down_moves
        else 0.0
    )

    return {

        "sample_size":
            total,

        "buy_probability":
            round(
                buy_probability,
                2
            ),

        "sell_probability":
            round(
                sell_probability,
                2
            ),

        "flat_probability":
            round(
                flat_probability,
                2
            ),

        "average_similarity":
            round(
                average_similarity,
                4
            ),

        "best_similarity":
            round(
                best_similarity,
                4
            ),

        "expected_up_percent":
            round(
                expected_up,
                4
            ),

        "expected_down_percent":
            round(
                expected_down,
                4
            )
    }


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    probability,
    matches,
    average_similarity
):

    probability_component = min(
        probability,
        100.0
    )

    sample_component = min(
        (
            len(matches)
            / MAX_MATCHES
        )
        * 100.0,
        100.0
    )

    similarity_component = (
        average_similarity
        * 100.0
    )

    score = (
        probability_component
        * 0.60

        +

        sample_component
        * 0.15

        +

        similarity_component
        * 0.25
    )

    return round(
        score,
        2
    )


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    direction,
    entry,
    atr,
    statistics
):

    if atr <= 0:

        atr = (
            entry
            * 0.001
        )

    if direction == "BUY":

        probability = statistics[
            "buy_probability"
        ]

        multiplier = (
            1.0
            + (
                probability
                - 70.0
            )
            / 100.0
        )

        sl_distance = atr

        tp_distance = (
            atr
            * multiplier
        )

        stop_loss = (
            entry
            - sl_distance
        )

        take_profit = (
            entry
            + tp_distance
        )

    else:

        probability = statistics[
            "sell_probability"
        ]

        multiplier = (
            1.0
            + (
                probability
                - 70.0
            )
            / 100.0
        )

        sl_distance = atr

        tp_distance = (
            atr
            * multiplier
        )

        stop_loss = (
            entry
            + sl_distance
        )

        take_profit = (
            entry
            - tp_distance
        )

    return (

        round_price(
            entry
        ),

        round_price(
            stop_loss
        ),

        round_price(
            take_profit
        )
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(
    candles
):

    latest = candles[
        -1
    ]

    entry = latest[
        "close"
    ]

    atr = calculate_atr(
        candles
    )

    matches = find_matches(
        candles
    )

    statistics = (
        historical_statistics(
            matches
        )
    )

    if not matches:

        return {

            "timestamp":
                latest[
                    "datetime"
                ],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                "NO_TRADE",

            "score":
                0.0,

            "probability":
                0.0,

            "entry":
                round_price(
                    entry
                ),

            "stop_loss":
                None,

            "take_profit":
                None,

            "atr":
                round(
                    atr,
                    4
                ),

            "historical_statistics":
                statistics,

            "matched_patterns":
                0,

            "method":
                "M5 historical pattern matching",

            "data_source":
                "Twelve Data XAU/USD"
        }

    buy_probability = statistics[
        "buy_probability"
    ]

    sell_probability = statistics[
        "sell_probability"
    ]

    if buy_probability > sell_probability:

        direction = "BUY"

        probability = (
            buy_probability
        )

    elif sell_probability > buy_probability:

        direction = "SELL"

        probability = (
            sell_probability
        )

    else:

        direction = "NO_TRADE"

        probability = 0.0

    score = calculate_score(
        probability,
        matches,
        statistics[
            "average_similarity"
        ]
    )

    valid = (

        direction
        in [
            "BUY",
            "SELL"
        ]

        and

        probability
        >= MIN_PROBABILITY

        and

        score
        >= MIN_SCORE

        and

        len(matches)
        >= MIN_MATCHES
    )

    if not valid:

        return {

            "timestamp":
                latest[
                    "datetime"
                ],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                "NO_TRADE",

            "score":
                score,

            "probability":
                round(
                    probability,
                    2
                ),

            "entry":
                round_price(
                    entry
                ),

            "stop_loss":
                None,

            "take_profit":
                None,

            "atr":
                round(
                    atr,
                    4
                ),

            "historical_statistics":
                statistics,

            "matched_patterns":
                len(matches),

            "method":
                "M5 historical pattern matching",

            "data_source":
                "Twelve Data XAU/USD"
        }

    (
        entry,
        stop_loss,
        take_profit
    ) = calculate_trade_levels(
        direction,
        entry,
        atr,
        statistics
    )

    return {

        "timestamp":
            latest[
                "datetime"
            ],

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "signal":
            direction,

        "score":
            score,

        "probability":
            round(
                probability,
                2
            ),

        "entry":
            entry,

        "stop_loss":
            stop_loss,

        "take_profit":
            take_profit,

        "atr":
            round(
                atr,
                4
            ),

        "historical_statistics":
            statistics,

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

def send_telegram(
    message
):

    if not TELEGRAM_BOT_TOKEN:

        return (
            False,
            "TELEGRAM_BOT_TOKEN is not configured"
        )

    if not TELEGRAM_CHAT_ID:

        return (
            False,
            "TELEGRAM_CHAT_ID is not configured"
        )

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    payload = {

        "chat_id":
            TELEGRAM_CHAT_ID,

        "text":
            message,

        "parse_mode":
            "HTML"
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=20
        )

        response.raise_for_status()

        result = response.json()

        if not result.get(
            "ok",
            False
        ):

            return (

                False,

                result.get(
                    "description",
                    "Telegram API error"
                )
            )

        return (
            True,
            None
        )

    except Exception as exc:

        return (
            False,
            str(exc)
        )


# ============================================================
# TELEGRAM STARTUP WELCOME
# ============================================================

def send_startup_notification():

    global STARTUP_NOTIFICATION_SENT

    if STARTUP_NOTIFICATION_SENT:

        return

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram startup skipped: "
            "TELEGRAM_BOT_TOKEN not configured"
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "Telegram startup skipped: "
            "TELEGRAM_CHAT_ID not configured"
        )

        return

    message = (

        "🟢 <b>XAUUSD M5 BOT ONLINE</b>\n"
        "\n"

        "👋 <b>ยินดีต้อนรับเข้าสู่ระบบวิเคราะห์ทองคำ</b>\n"
        "\n"

        "ระบบเริ่มทำงานเรียบร้อยแล้ว ✅\n"
        "\n"

        f"📊 <b>Symbol:</b> {SYMBOL}\n"
        "⏱ <b>Timeframe:</b> M5\n"
        "📡 <b>Data:</b> Twelve Data\n"
        "\n"

        "🤖 <b>ระบบพร้อมวิเคราะห์</b>\n"
        "• BUY\n"
        "• SELL\n"
        "• NO TRADE\n"
        "\n"

        "📈 <b>ระบบใช้การวิเคราะห์</b>\n"
        "• Historical Pattern Matching\n"
        "• Probability\n"
        "• Pattern Similarity\n"
        "• Signal Score\n"
        "• ATR\n"
        "\n"

        "🎯 <b>Signal ที่ผ่านเกณฑ์จะได้รับ</b>\n"
        "• Entry\n"
        "• Take Profit (TP)\n"
        "• Stop Loss (SL)\n"
        "\n"

        f"📌 <b>Minimum Probability:</b> "
        f"{MIN_PROBABILITY:.0f}%\n"

        f"📌 <b>Minimum Score:</b> "
        f"{MIN_SCORE:.0f}\n"

        f"📌 <b>Minimum Patterns:</b> "
        f"{MIN_MATCHES}\n"

        f"📌 <b>Minimum Similarity:</b> "
        f"{MIN_SIMILARITY:.2f}\n"

        "\n"

        "🚀 <b>ระบบพร้อมทำงานแล้ว</b>\n"
        "\n"

        "<i>Historical Pattern Matching System</i>"
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        STARTUP_NOTIFICATION_SENT = True

        print(
            "Telegram welcome message sent successfully"
        )

    else:

        print(
            "Telegram welcome message failed:",
            error
        )


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def format_signal_message(
    signal
):

    direction = signal[
        "signal"
    ]

    if direction == "BUY":

        emoji = "🟢"

    elif direction == "SELL":

        emoji = "🔴"

    else:

        return None

    stats = signal[
        "historical_statistics"
    ]

    return (

        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"

        f"<b>SIGNAL:</b> {direction}\n"

        f"<b>Probability:</b> "
        f"{signal['probability']:.2f}%\n"

        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"

        "\n"

        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"

        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"

        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"

        "\n"

        f"<b>Patterns:</b> "
        f"{signal['matched_patterns']}\n"

        f"<b>Average Similarity:</b> "
        f"{stats['average_similarity']:.4f}\n"

        f"<b>Best Similarity:</b> "
        f"{stats['best_similarity']:.4f}\n"

        "\n"

        f"<b>BUY Probability:</b> "
        f"{stats['buy_probability']:.2f}%\n"

        f"<b>SELL Probability:</b> "
        f"{stats['sell_probability']:.2f}%\n"

        "\n"

        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"

        "\n"

        "<i>Historical Pattern Matching</i>"
    )


# ============================================================
# RUN SIGNAL
# ============================================================

def run_signal(
    send_notification=True
):

    candles = get_candles()

    signal = generate_signal(
        candles
    )

    STATE[
        "last_update"
    ] = utc_now().isoformat()

    STATE[
        "last_error"
    ] = None

    if (

        send_notification

        and

        signal["signal"]
        in [
            "BUY",
            "SELL"
        ]
    ):

        signal_key = (

            str(
                signal["timestamp"]
            )

            + "_"

            + signal["signal"]
        )

        if (

            STATE[
                "last_signal_key"
            ]

            !=

            signal_key
        ):

            message = (
                format_signal_message(
                    signal
                )
            )

            if message:

                ok, error = (
                    send_telegram(
                        message
                    )
                )

                if not ok:

                    STATE[
                        "last_error"
                    ] = error

            STATE[
                "last_signal_key"
            ] = signal_key

    STATE[
        "last_signal"
    ] = signal

    return signal


# ============================================================
# STARTUP HOOK
# ============================================================

@app.before_request
def startup_hook():

    send_startup_notification()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "name":
            "XAUUSD M5 Telegram Signal",

        "status":
            "online",

        "data_source":
            "Twelve Data",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "rules": {

            "minimum_probability":
                MIN_PROBABILITY,

            "minimum_score":
                MIN_SCORE,

            "minimum_patterns":
                MIN_MATCHES,

            "minimum_similarity":
                MIN_SIMILARITY
        },

        "endpoints": [

            "/",

            "/health",

            "/signal",

            "/backtest"
        ]
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status":
            "healthy",

        "data_source":
            "Twelve Data",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "candles":
            CANDLE_LIMIT,

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "twelve_data":
            bool(
                TWELVE_DATA_API_KEY
            ),

        "last_update":
            STATE[
                "last_update"
            ],

        "last_signal":
            STATE[
                "last_signal"
            ],

        "error":
            STATE[
                "last_error"
            ]
    })


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        signal = run_signal(
            send_notification=True
        )

        return jsonify(
            signal
        )

    except Exception as exc:

        STATE[
            "last_error"
        ] = str(exc)

        return jsonify({

            "signal":
                "ERROR",

            "error":
                str(exc)

        }), 500


# ============================================================
# BACKTEST
# ============================================================

@app.route("/backtest")
def backtest():

    try:

        candles = get_candles()

        total_candles = len(
            candles
        )

        start = max(

            PATTERN_LENGTH * 2 + 20,

            80
        )

        end = (
            total_candles - 1
        )

        max_test_points = min(

            MAX_BACKTEST_POINTS,

            end - start
        )

        if max_test_points <= 0:

            return jsonify({

                "error":
                    "Not enough candles"

            }), 400

        start = (

            end
            - max_test_points
        )

        signals = 0

        buy_signals = 0

        sell_signals = 0

        wins = 0

        losses = 0

        timeouts = 0

        tp_hits = 0

        sl_hits = 0

        total_profit_percent = 0.0

        total_loss_percent = 0.0

        mfe_values = []

        mae_values = []

        probability_values = []

        score_values = []

        trade_results = []

        forward_bars = FORWARD_BARS

        for i in range(
            start,
            end
        ):

            historical_candles = (
                candles[:i]
            )

            try:

                signal = generate_signal(
                    historical_candles
                )

            except Exception:

                continue

            direction = signal.get(
                "signal"
            )

            if direction not in [

                "BUY",

                "SELL"
            ]:

                continue

            entry = signal.get(
                "entry"
            )

            stop_loss = signal.get(
                "stop_loss"
            )

            take_profit = signal.get(
                "take_profit"
            )

            probability = float(
                signal.get(
                    "probability",
                    0
                )
            )

            score = float(
                signal.get(
                    "score",
                    0
                )
            )

            if (

                entry is None

                or

                stop_loss is None

                or

                take_profit is None
            ):

                continue

            signals += 1

            probability_values.append(
                probability
            )

            score_values.append(
                score
            )

            if direction == "BUY":

                buy_signals += 1

            else:

                sell_signals += 1

            entry = float(
                entry
            )

            stop_loss = float(
                stop_loss
            )

            take_profit = float(
                take_profit
            )

            max_index = min(

                i + forward_bars,

                len(candles) - 1
            )

            result = "TIMEOUT"

            exit_price = None

            exit_index = None

            mfe = 0.0

            mae = 0.0

            for j in range(
                i,
                max_index + 1
            ):

                candle = candles[j]

                high = float(
                    candle["high"]
                )

                low = float(
                    candle["low"]
                )

                if direction == "BUY":

                    favorable = (

                        high - entry

                    ) / entry * 100.0

                    adverse = (

                        entry - low

                    ) / entry * 100.0

                    mfe = max(

                        mfe,

                        favorable
                    )

                    mae = max(

                        mae,

                        adverse
                    )

                    hit_sl = (
                        low <= stop_loss
                    )

                    hit_tp = (
                        high >= take_profit
                    )

                    if hit_sl and hit_tp:

                        result = "LOSS"

                        exit_price = (
                            stop_loss
                        )

                        exit_index = j

                        break

                    if hit_sl:

                        result = "LOSS"

                        exit_price = (
                            stop_loss
                        )

                        exit_index = j

                        break

                    if hit_tp:

                        result = "WIN"

                        exit_price = (
                            take_profit
                        )

                        exit_index = j

                        break

                else:

                    favorable = (

                        entry - low

                    ) / entry * 100.0

                    adverse = (

                        high - entry

                    ) / entry * 100.0

                    mfe = max(

                        mfe,

                        favorable
                    )

                    mae = max(

                        mae,

                        adverse
                    )

                    hit_sl = (
                        high >= stop_loss
                    )

                    hit_tp = (
                        low <= take_profit
                    )

                    if hit_sl and hit_tp:

                        result = "LOSS"

                        exit_price = (
                            stop_loss
                        )

                        exit_index = j

                        break

                    if hit_sl:

                        result = "LOSS"

                        exit_price = (
                            stop_loss
                        )

                        exit_index = j

                        break

                    if hit_tp:

                        result = "WIN"

                        exit_price = (
                            take_profit
                        )

                        exit_index = j

                        break

            if result == "TIMEOUT":

                exit_index = max_index

                exit_price = float(

                    candles[
                        exit_index
                    ]["close"]
                )

            if direction == "BUY":

                pnl_percent = (

                    exit_price - entry

                ) / entry * 100.0

            else:

                pnl_percent = (

                    entry - exit_price

                ) / entry * 100.0

            mfe_values.append(
                mfe
            )

            mae_values.append(
                mae
            )

            if result == "WIN":

                wins += 1

                tp_hits += 1

                total_profit_percent += max(

                    pnl_percent,

                    0
                )

            elif result == "LOSS":

                losses += 1

                sl_hits += 1

                total_loss_percent += abs(

                    min(

                        pnl_percent,

                        0
                    )
                )

            else:

                timeouts += 1

            trade_results.append({

                "timestamp":
                    candles[i][
                        "datetime"
                    ],

                "signal":
                    direction,

                "probability":
                    round(
                        probability,
                        2
                    ),

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
                    round(
                        stop_loss,
                        2
                    ),

                "take_profit":
                    round(
                        take_profit,
                        2
                    ),

                "result":
                    result,

                "exit_price":
                    round(
                        exit_price,
                        2
                    ),

                "pnl_percent":
                    round(
                        pnl_percent,
                        4
                    ),

                "mfe_percent":
                    round(
                        mfe,
                        4
                    ),

                "mae_percent":
                    round(
                        mae,
                        4
                    ),

                "bars_held":
                    (

                        exit_index - i + 1

                        if exit_index
                        is not None

                        else None
                    )
            })

        # ====================================================
        # PERFORMANCE
        # ====================================================

        if signals > 0:

            win_rate = (

                wins
                / signals
                * 100.0
            )

            loss_rate = (

                losses
                / signals
                * 100.0
            )

            timeout_rate = (

                timeouts
                / signals
                * 100.0
            )

        else:

            win_rate = 0.0

            loss_rate = 0.0

            timeout_rate = 0.0

        average_mfe = (

            sum(mfe_values)
            / len(mfe_values)

            if mfe_values

            else 0.0
        )

        average_mae = (

            sum(mae_values)
            / len(mae_values)

            if mae_values

            else 0.0
        )

        average_probability = (

            sum(probability_values)
            / len(probability_values)

            if probability_values

            else 0.0
        )

        average_score = (

            sum(score_values)
            / len(score_values)

            if score_values

            else 0.0
        )

        if total_loss_percent > 0:

            profit_factor = (

                total_profit_percent
                / total_loss_percent
            )

        elif total_profit_percent > 0:

            profit_factor = float(
                "inf"
            )

        else:

            profit_factor = 0.0

        net_profit_percent = (

            total_profit_percent
            - total_loss_percent
        )

        expectancy = (

            net_profit_percent
            / signals

            if signals > 0

            else 0.0
        )

        # ====================================================
        # MAX DRAWDOWN
        # ====================================================

        equity = 0.0

        peak_equity = 0.0

        max_drawdown = 0.0

        for trade in trade_results:

            equity += trade[
                "pnl_percent"
            ]

            peak_equity = max(

                peak_equity,

                equity
            )

            drawdown = (

                peak_equity
                - equity
            )

            max_drawdown = max(

                max_drawdown,

                drawdown
            )

        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "status":
                "completed",

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "data_source":
                "Twelve Data XAU/USD",

            "candles_available":
                total_candles,

            "test_points":
                max_test_points,

            "rules": {

                "minimum_probability":
                    MIN_PROBABILITY,

                "minimum_score":
                    MIN_SCORE,

                "minimum_patterns":
                    MIN_MATCHES,

                "minimum_similarity":
                    MIN_SIMILARITY,

                "forward_bars":
                    forward_bars
            },

            "signals": {

                "total":
                    signals,

                "buy":
                    buy_signals,

                "sell":
                    sell_signals
            },

            "results": {

                "wins":
                    wins,

                "losses":
                    losses,

                "timeouts":
                    timeouts,

                "tp_hits":
                    tp_hits,

                "sl_hits":
                    sl_hits
            },

            "performance": {

                "win_rate_percent":
                    round(
                        win_rate,
                        2
                    ),

                "loss_rate_percent":
                    round(
                        loss_rate,
                        2
                    ),

                "timeout_rate_percent":
                    round(
                        timeout_rate,
                        2
                    ),

                "total_profit_percent":
                    round(
                        total_profit_percent,
                        4
                    ),

                "total_loss_percent":
                    round(
                        total_loss_percent,
                        4
                    ),

                "net_profit_percent":
                    round(
                        net_profit_percent,
                        4
                    ),

                "profit_factor":
                    (

                        round(
                            profit_factor,
                            4
                        )

                        if math.isfinite(
                            profit_factor
                        )

                        else "infinite"
                    ),

                "expectancy_percent":
                    round(
                        expectancy,
                        4
                    ),

                "max_drawdown_percent":
                    round(
                        max_drawdown,
                        4
                    ),

                "average_mfe_percent":
                    round(
                        average_mfe,
                        4
                    ),

                "average_mae_percent":
                    round(
                        average_mae,
                        4
                    )
            },

            "signal_quality": {

                "average_probability":
                    round(
                        average_probability,
                        2
                    ),

                "average_score":
                    round(
                        average_score,
                        2
                    )
            },

            "recent_trades":
                trade_results[-20:],

            "warning":
                "Historical simulation only. "
                "Spread, slippage and execution "
                "differences are not included."
        })

    except Exception as exc:

        return jsonify({

            "status":
                "error",

            "error":
                str(exc)

        }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    send_startup_notification()

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port
    )

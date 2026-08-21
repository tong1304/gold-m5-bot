import os
import math
import threading
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

MIN_PROBABILITY = 70.0

MIN_SCORE = 65.0

MIN_MATCHES = 20

FORWARD_BARS = 12

RISK_REWARD = 1.5


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

STARTUP_LOCK = threading.Lock()


# ============================================================
# TIME
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# NUMBER
# ============================================================

def round_price(value):
    return round(float(value), 2)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


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

    values = data.get("values")

    if not values:
        raise RuntimeError(
            "No candle data received from Twelve Data"
        )

    candles = []

    for item in values:

        try:

            candles.append({
                "datetime": item["datetime"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
            })

        except Exception:
            continue

    candles.reverse()

    minimum_required = (
        PATTERN_LENGTH * 2 + 30
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

    for i in range(1, len(candles)):

        current = candles[i]
        previous = candles[i - 1]

        high = current["high"]
        low = current["low"]
        previous_close = previous["close"]

        tr1 = high - low
        tr2 = abs(high - previous_close)
        tr3 = abs(low - previous_close)

        true_range = max(
            tr1,
            tr2,
            tr3
        )

        true_ranges.append(
            true_range
        )

    recent = true_ranges[-period:]

    if not recent:
        return 0.0

    return (
        sum(recent)
        / len(recent)
    )


# ============================================================
# NORMALIZED PATTERN
# ============================================================

def make_pattern(candles):

    if len(candles) < PATTERN_LENGTH:
        return None

    window = candles[-PATTERN_LENGTH:]

    first_close = window[0]["close"]

    if first_close <= 0:
        return None

    pattern = []

    for candle in window:

        value = (
            candle["close"]
            / first_close
            - 1.0
        )

        pattern.append(value)

    return pattern


# ============================================================
# PATTERN SIMILARITY
# ============================================================

def pattern_similarity(
    pattern_a,
    pattern_b
):

    if not pattern_a or not pattern_b:
        return 0.0

    if len(pattern_a) != len(pattern_b):
        return 0.0

    squared = 0.0

    for a, b in zip(
        pattern_a,
        pattern_b
    ):

        difference = a - b

        squared += (
            difference
            * difference
        )

    mse = (
        squared
        / len(pattern_a)
    )

    distance = math.sqrt(mse)

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

def find_matches(candles):

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

        historical_pattern = make_pattern(
            historical_window
        )

        if historical_pattern is None:
            continue

        similarity = pattern_similarity(
            current_pattern,
            historical_pattern
        )

        if similarity < MIN_SIMILARITY:
            continue

        historical_close = candles[
            i - 1
        ]["close"]

        if historical_close <= 0:
            continue

        # ----------------------------------------------------
        # IMPORTANT
        #
        # Historical pattern ends at i-1.
        # We evaluate the NEXT candle(s), not the same candle.
        # ----------------------------------------------------

        future_end = min(
            i + FORWARD_BARS - 1,
            len(candles) - 1
        )

        future_close = candles[
            future_end
        ]["close"]

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

            "index": i,

            "similarity":
                similarity,

            "movement_percent":
                movement_percent,

            "direction":
                direction,

        })

    matches.sort(
        key=lambda x:
            x["similarity"],
        reverse=True
    )

    return matches[:MAX_MATCHES]


# ============================================================
# OUTCOME STATISTICS
# ============================================================

def calculate_direction_statistics(
    matches,
    direction
):

    selected = [
        x for x in matches
        if x["direction"] == direction
    ]

    total = len(matches)

    direction_count = len(selected)

    if total == 0:

        return {
            "sample_size": 0,
            "wins": 0,
            "losses": 0,
            "timeouts": 0,
            "win_probability": 0.0,
            "loss_probability": 0.0,
            "timeout_probability": 0.0,
            "weighted_win_probability": 0.0,
            "average_similarity": 0.0,
            "average_win_mfe": 0.0,
            "average_loss_mae": 0.0,
            "expected_pnl_percent": 0.0,
        }

    wins = 0
    losses = 0
    timeouts = 0

    win_mfe = []
    loss_mae = []

    pnl_values = []

    similarities = []

    for item in matches:

        movement = item[
            "movement_percent"
        ]

        similarity = item[
            "similarity"
        ]

        # ----------------------------------------------------
        # Direction-specific outcome
        # ----------------------------------------------------

        if direction == "BUY":

            pnl = movement

        else:

            pnl = -movement

        similarities.append(
            similarity
        )

        # ----------------------------------------------------
        # classify outcome
        # ----------------------------------------------------

        if pnl > 0.0:

            if item["direction"] == direction:
                wins += 1
                win_mfe.append(abs(pnl))
                pnl_values.append(pnl)

            else:
                losses += 1
                loss_mae.append(abs(pnl))
                pnl_values.append(pnl)

        elif pnl < 0.0:

            losses += 1
            loss_mae.append(abs(pnl))
            pnl_values.append(pnl)

        else:

            timeouts += 1

    if direction_count > 0:

        win_probability = (
            wins
            / direction_count
            * 100.0
        )

        loss_probability = (
            losses
            / direction_count
            * 100.0
        )

        timeout_probability = (
            timeouts
            / direction_count
            * 100.0
        )

    else:

        win_probability = 0.0
        loss_probability = 0.0
        timeout_probability = 0.0

    # --------------------------------------------------------
    # Weighted probability
    #
    # More similar historical patterns receive more weight.
    # --------------------------------------------------------

    weighted_win = 0.0
    weighted_total = 0.0

    for item in matches:

        movement = item[
            "movement_percent"
        ]

        similarity = item[
            "similarity"
        ]

        if direction == "BUY":
            pnl = movement
        else:
            pnl = -movement

        weighted_total += similarity

        if pnl > 0:
            weighted_win += similarity

    if weighted_total > 0:

        weighted_win_probability = (
            weighted_win
            / weighted_total
            * 100.0
        )

    else:

        weighted_win_probability = 0.0

    average_similarity = (
        sum(similarities)
        / len(similarities)
        if similarities
        else 0.0
    )

    average_win_mfe = (
        sum(win_mfe)
        / len(win_mfe)
        if win_mfe
        else 0.0
    )

    average_loss_mae = (
        sum(loss_mae)
        / len(loss_mae)
        if loss_mae
        else 0.0
    )

    expected_pnl = (
        sum(pnl_values)
        / len(pnl_values)
        if pnl_values
        else 0.0
    )

    return {

        "sample_size":
            total,

        "wins":
            wins,

        "losses":
            losses,

        "timeouts":
            timeouts,

        "win_probability":
            round(
                win_probability,
                2
            ),

        "loss_probability":
            round(
                loss_probability,
                2
            ),

        "timeout_probability":
            round(
                timeout_probability,
                2
            ),

        "weighted_win_probability":
            round(
                weighted_win_probability,
                2
            ),

        "average_similarity":
            round(
                average_similarity,
                4
            ),

        "average_win_mfe":
            round(
                average_win_mfe,
                4
            ),

        "average_loss_mae":
            round(
                average_loss_mae,
                4
            ),

        "expected_pnl_percent":
            round(
                expected_pnl,
                4
            ),
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
        probability_component * 0.60
        +
        sample_component * 0.15
        +
        similarity_component * 0.25
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
    atr
):

    if atr <= 0:

        atr = (
            entry
            * 0.001
        )

    sl_distance = atr

    tp_distance = (
        sl_distance
        * RISK_REWARD
    )

    if direction == "BUY":

        stop_loss = (
            entry
            - sl_distance
        )

        take_profit = (
            entry
            + tp_distance
        )

    else:

        stop_loss = (
            entry
            + sl_distance
        )

        take_profit = (
            entry
            - tp_distance
        )

    return (
        round_price(entry),
        round_price(stop_loss),
        round_price(take_profit)
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(candles):

    latest = candles[-1]

    entry = latest["close"]

    atr = calculate_atr(
        candles
    )

    matches = find_matches(
        candles
    )

    if not matches:

        return {

            "timestamp":
                latest["datetime"],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                "NO_TRADE",

            "candidate_direction":
                None,

            "probability":
                0.0,

            "score":
                0.0,

            "entry":
                round_price(entry),

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                RISK_REWARD,

            "atr":
                round(atr, 4),

            "matched_patterns":
                0,

            "historical_statistics":
                {},

            "method":
                "Outcome-Based M5 Historical Pattern Matching",

            "data_source":
                "Twelve Data XAU/USD",
        }

    buy_stats = calculate_direction_statistics(
        matches,
        "BUY"
    )

    sell_stats = calculate_direction_statistics(
        matches,
        "SELL"
    )

    buy_probability = (
        buy_stats[
            "weighted_win_probability"
        ]
    )

    sell_probability = (
        sell_stats[
            "weighted_win_probability"
        ]
    )

    buy_expected = (
        buy_stats[
            "expected_pnl_percent"
        ]
    )

    sell_expected = (
        sell_stats[
            "expected_pnl_percent"
        ]
    )

    # --------------------------------------------------------
    # Candidate selection
    # --------------------------------------------------------

    if (
        buy_probability > sell_probability
        and buy_expected >= sell_expected
    ):

        candidate_direction = "BUY"
        probability = buy_probability
        candidate_stats = buy_stats

    elif (
        sell_probability > buy_probability
        and sell_expected > buy_expected
    ):

        candidate_direction = "SELL"
        probability = sell_probability
        candidate_stats = sell_stats

    elif buy_expected > sell_expected:

        candidate_direction = "BUY"
        probability = buy_probability
        candidate_stats = buy_stats

    elif sell_expected > buy_expected:

        candidate_direction = "SELL"
        probability = sell_probability
        candidate_stats = sell_stats

    else:

        candidate_direction = "NO_TRADE"
        probability = 0.0
        candidate_stats = None

    average_similarity = (
        sum(
            x["similarity"]
            for x in matches
        )
        / len(matches)
    )

    score = calculate_score(
        probability,
        matches,
        average_similarity
    )

    valid = (

        candidate_direction
        in ["BUY", "SELL"]

        and probability
        >= MIN_PROBABILITY

        and score
        >= MIN_SCORE

        and len(matches)
        >= MIN_MATCHES

        and candidate_stats is not None

        and candidate_stats[
            "expected_pnl_percent"
        ] > 0
    )

    if not valid:

        return {

            "timestamp":
                latest["datetime"],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                "NO_TRADE",

            "candidate_direction":
                candidate_direction,

            "probability":
                round(
                    probability,
                    2
                ),

            "score":
                score,

            "entry":
                round_price(entry),

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                RISK_REWARD,

            "atr":
                round(
                    atr,
                    4
                ),

            "historical_statistics": {

                "sample_size":
                    len(matches),

                "buy":
                    buy_stats,

                "sell":
                    sell_stats,
            },

            "matched_patterns":
                len(matches),

            "method":
                "Outcome-Based M5 Historical Pattern Matching",

            "data_source":
                "Twelve Data XAU/USD",
        }

    (
        entry,
        stop_loss,
        take_profit
    ) = calculate_trade_levels(
        candidate_direction,
        entry,
        atr
    )

    return {

        "timestamp":
            latest["datetime"],

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "signal":
            candidate_direction,

        "candidate_direction":
            candidate_direction,

        "probability":
            round(
                probability,
                2
            ),

        "score":
            score,

        "entry":
            entry,

        "stop_loss":
            stop_loss,

        "take_profit":
            take_profit,

        "risk_reward":
            RISK_REWARD,

        "atr":
            round(
                atr,
                4
            ),

        "historical_statistics": {

            "sample_size":
                len(matches),

            "buy":
                buy_stats,

            "sell":
                sell_stats,
        },

        "matched_patterns":
            len(matches),

        "method":
            "Outcome-Based M5 Historical Pattern Matching",

        "data_source":
            "Twelve Data XAU/USD",
    }


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

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
            "HTML",

    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=20
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("ok", False):

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
# TELEGRAM STARTUP
# ============================================================

def send_startup_notification_once():

    global STARTUP_NOTIFICATION_SENT

    if STARTUP_NOTIFICATION_SENT:
        return

    with STARTUP_LOCK:

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

            "━━━━━━━━━━━━━━━━━━\n"

            "🚀 <b>ระบบเริ่มทำงานแล้ว</b>\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "\n"

            f"📊 <b>Symbol:</b> {SYMBOL}\n"

            "⏱ <b>Timeframe:</b> M5\n"

            "📡 <b>Data:</b> Twelve Data\n"
            "\n"

            "🧠 <b>Engine:</b>\n"

            "Outcome-Based Historical "
            "Pattern Matching\n"
            "\n"

            f"🎯 <b>Minimum Probability:</b> "
            f"{MIN_PROBABILITY:.0f}%\n"

            f"⭐ <b>Minimum Score:</b> "
            f"{MIN_SCORE:.0f}\n"

            f"📚 <b>Minimum Patterns:</b> "
            f"{MIN_MATCHES}\n"

            f"🔎 <b>Minimum Similarity:</b> "
            f"{MIN_SIMILARITY:.2f}\n"

            f"⚖️ <b>Risk / Reward:</b> "
            f"1:{RISK_REWARD:.1f}\n"

            "\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "✅ <b>พร้อมวิเคราะห์ตลาด</b>\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "\n"

            "ระบบจะส่ง Telegram เมื่อพบ\n"

            "<b>BUY / SELL</b> "
            "ที่ผ่านเกณฑ์ทั้งหมด"

        )

        ok, error = send_telegram(
            message
        )

        if ok:

            STARTUP_NOTIFICATION_SENT = True

            print(
                "Telegram welcome message "
                "sent successfully"
            )

        else:

            print(
                "Telegram welcome message failed:",
                error
            )


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def format_signal_message(signal):

    direction = signal["signal"]

    if direction == "BUY":

        emoji = "🟢"

    elif direction == "SELL":

        emoji = "🔴"

    else:

        return None

    stats = signal[
        "historical_statistics"
    ]

    selected = stats[
        direction.lower()
    ]

    return (

        f"{emoji} "
        "<b>XAUUSD M5 SIGNAL</b>\n"
        "\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>SIGNAL:</b> {direction}\n"

        f"<b>Probability:</b> "
        f"{signal['probability']:.2f}%\n"

        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"

        f"<b>Patterns:</b> "
        f"{signal['matched_patterns']}\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"

        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"

        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"

        f"<b>R:R:</b> "
        f"1:{signal['risk_reward']:.1f}\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>Win Probability:</b> "
        f"{selected['weighted_win_probability']:.2f}%\n"

        f"<b>Expected P/L:</b> "
        f"{selected['expected_pnl_percent']:.4f}%\n"

        f"<b>Average Similarity:</b> "
        f"{selected['average_similarity']:.4f}\n"

        f"<b>Wins:</b> "
        f"{selected['wins']}\n"

        f"<b>Losses:</b> "
        f"{selected['losses']}\n"

        f"<b>Timeouts:</b> "
        f"{selected['timeouts']}\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"

        "\n"

        "<i>Outcome-Based Historical "
        "Pattern Matching</i>"

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

    STATE["last_update"] = (
        utc_now().isoformat()
    )

    STATE["last_error"] = None

    # --------------------------------------------------------
    # Telegram only for valid BUY / SELL
    # --------------------------------------------------------

    if (
        send_notification
        and signal["signal"]
        in ["BUY", "SELL"]
    ):

        signal_key = (

            str(
                signal["timestamp"]
            )

            + "_"

            + signal["signal"]

        )

        if (
            STATE["last_signal_key"]
            != signal_key
        ):

            message = format_signal_message(
                signal
            )

            if message:

                ok, error = send_telegram(
                    message
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
# STARTUP BEFORE FIRST REQUEST
# ============================================================

@app.before_request
def startup_notification():

    send_startup_notification_once()


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

        "version":
            "2.0",

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
                MIN_SIMILARITY,

            "risk_reward":
                RISK_REWARD,

            "forward_bars":
                FORWARD_BARS,
        },

        "endpoints": [

            "/",
            "/health",
            "/test-telegram",
            "/test-data",
            "/signal",
            "/backtest",

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

        "service":
            "XAUUSD M5 Telegram Signal",

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

        "startup_notification":
            STARTUP_NOTIFICATION_SENT,

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
            ],

    })


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    if not TELEGRAM_BOT_TOKEN:

        return jsonify({

            "status":
                "error",

            "telegram":
                False,

            "error":
                "TELEGRAM_BOT_TOKEN is not configured"

        }), 500

    if not TELEGRAM_CHAT_ID:

        return jsonify({

            "status":
                "error",

            "telegram":
                False,

            "error":
                "TELEGRAM_CHAT_ID is not configured"

        }), 500

    message = (

        "🧪 <b>TELEGRAM TEST</b>\n"
        "\n"

        "✅ Telegram connection is working\n"
        "\n"

        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"

        f"<b>Time:</b> "
        f"{utc_now().isoformat()}"

    )

    ok, error = send_telegram(
        message
    )

    if not ok:

        return jsonify({

            "status":
                "error",

            "telegram":
                True,

            "error":
                error

        }), 500

    return jsonify({

        "status":
            "success",

        "message":
            "Telegram test message sent successfully",

        "telegram":
            True

    })


# ============================================================
# TEST DATA
# ============================================================

@app.route("/test-data")
def test_data():

    try:

        candles = get_candles()

        latest = candles[-1]

        return jsonify({

            "status":
                "success",

            "message":
                "Twelve Data connection is working",

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "candles":
                len(candles),

            "latest":
                latest,

        })

    except Exception as exc:

        STATE[
            "last_error"
        ] = str(exc)

        return jsonify({

            "status":
                "error",

            "error":
                str(exc)

        }), 500


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

            "status":
                "error",

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
            PATTERN_LENGTH * 2 + 30,
            100
        )

        end = (
            total_candles - 1
        )

        max_test_points = min(
            150,
            end - start
        )

        if max_test_points <= 0:

            return jsonify({

                "status":
                    "error",

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

        # ----------------------------------------------------
        # Historical test
        # ----------------------------------------------------

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

            probability = safe_float(
                signal.get(
                    "probability",
                    0
                )
            )

            score = safe_float(
                signal.get(
                    "score",
                    0
                )
            )

            if (
                entry is None
                or stop_loss is None
                or take_profit is None
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

            entry = float(entry)
            stop_loss = float(stop_loss)
            take_profit = float(take_profit)

            max_index = min(
                i + FORWARD_BARS,
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

                # ------------------------------------------------
                # BUY
                # ------------------------------------------------

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

                    # Conservative assumption:
                    # if TP and SL happen inside same candle,
                    # SL is considered first.
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

                # ------------------------------------------------
                # SELL
                # ------------------------------------------------

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

            # ----------------------------------------------------
            # TIMEOUT
            # ----------------------------------------------------

            if result == "TIMEOUT":

                exit_index = max_index

                exit_price = float(
                    candles[
                        exit_index
                    ]["close"]
                )

            # ----------------------------------------------------
            # PNL
            # ----------------------------------------------------

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
                        if exit_index is not None
                        else None
                    ),

            })

        # ========================================================
        # PERFORMANCE
        # ========================================================

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

        # ========================================================
        # MAX DRAWDOWN
        # ========================================================

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

        # ========================================================
        # RESPONSE
        # ========================================================

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
                    FORWARD_BARS,

                "risk_reward":
                    RISK_REWARD,
            },

            "signals": {

                "total":
                    signals,

                "buy":
                    buy_signals,

                "sell":
                    sell_signals,
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
                    sl_hits,
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
                    ),
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
                    ),
            },

            "recent_trades":
                trade_results[-20:],

            "warning":
                "Historical simulation only. "
                "Spread, slippage and execution "
                "differences are not included.",

        })

    except Exception as exc:

        STATE[
            "last_error"
        ] = str(exc)

        return jsonify({

            "status":
                "error",

            "error":
                str(exc)

        }), 500


# ============================================================
# ERROR HANDLER
# ============================================================

@app.errorhandler(Exception)
def handle_exception(error):

    STATE[
        "last_error"
    ] = str(error)

    return jsonify({

        "status":
            "error",

        "error":
            str(error),

    }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # For local Python execution.
    # Render/Gunicorn will use before_request instead.
    # --------------------------------------------------------

    send_startup_notification_once()

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

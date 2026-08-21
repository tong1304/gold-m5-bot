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
# TRADE SETTINGS
# ============================================================

ATR_PERIOD = 14

SL_ATR_MULTIPLIER = 1.0

TP_ATR_MULTIPLIER = 1.5

FORWARD_BARS = 12


# ============================================================
# SCORE WEIGHTS
# ============================================================

WEIGHT_PROBABILITY = 0.50

WEIGHT_SIMILARITY = 0.25

WEIGHT_SAMPLE = 0.10

WEIGHT_RISK_REWARD = 0.15


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
    "startup_notification_sent": False,
}


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

        "symbol":
            SYMBOL,

        "interval":
            TIMEFRAME,

        "outputsize":
            CANDLE_LIMIT,

        "apikey":
            TWELVE_DATA_API_KEY,

        "format":
            "JSON",

        "timezone":
            "UTC",
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Twelve Data request failed: {exc}"
        )

    try:

        data = response.json()

    except Exception:

        raise RuntimeError(
            "Twelve Data returned invalid JSON"
        )

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
            "No candle data received from Twelve Data"
        )

    candles = []

    for item in values:

        try:

            candle = {

                "datetime":
                    item["datetime"],

                "open":
                    float(item["open"]),

                "high":
                    float(item["high"]),

                "low":
                    float(item["low"]),

                "close":
                    float(item["close"]),
            }

            candles.append(
                candle
            )

        except Exception:

            continue

    # Twelve Data normally returns newest first.
    # We want oldest -> newest.
    candles.reverse()

    minimum_required = max(

        PATTERN_LENGTH * 2 + ATR_PERIOD + FORWARD_BARS,

        100
    )

    if len(candles) < minimum_required:

        raise RuntimeError(
            "Not enough M5 candles received"
        )

    return candles


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=ATR_PERIOD
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

        tr1 = (
            high
            - low
        )

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
# PATTERN
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

        ) - 1.0

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

    if not pattern_a:

        return 0.0

    if not pattern_b:

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
# HISTORICAL TRADE SIMULATION
# ============================================================

def simulate_historical_trade(
    candles,
    entry_index,
    direction,
    atr,
    forward_bars=FORWARD_BARS
):

    if (
        entry_index < 1
        or entry_index >= len(candles)
    ):

        return None

    entry = candles[
        entry_index - 1
    ]["close"]

    if entry <= 0:

        return None

    if atr <= 0:

        atr = (
            entry
            * 0.001
        )

    sl_distance = (
        atr
        * SL_ATR_MULTIPLIER
    )

    tp_distance = (
        atr
        * TP_ATR_MULTIPLIER
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

    elif direction == "SELL":

        stop_loss = (
            entry
            + sl_distance
        )

        take_profit = (
            entry
            - tp_distance
        )

    else:

        return None

    max_index = min(
        entry_index + forward_bars - 1,
        len(candles) - 1
    )

    result = "TIMEOUT"

    exit_price = None

    exit_index = None

    mfe = 0.0

    mae = 0.0

    for j in range(
        entry_index,
        max_index + 1
    ):

        candle = candles[j]

        high = candle[
            "high"
        ]

        low = candle[
            "low"
        ]

        if direction == "BUY":

            favorable = (

                (
                    high
                    - entry
                )
                / entry
                * 100.0
            )

            adverse = (

                (
                    entry
                    - low
                )
                / entry
                * 100.0
            )

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

        else:

            favorable = (

                (
                    entry
                    - low
                )
                / entry
                * 100.0
            )

            adverse = (

                (
                    high
                    - entry
                )
                / entry
                * 100.0
            )

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

        # ----------------------------------------------------
        # Conservative assumption:
        # if both TP and SL are inside the same candle,
        # assume SL happened first.
        # ----------------------------------------------------

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

        exit_price = candles[
            exit_index
        ]["close"]

    if direction == "BUY":

        pnl_percent = (

            (
                exit_price
                - entry
            )
            / entry
            * 100.0
        )

    else:

        pnl_percent = (

            (
                entry
                - exit_price
            )
            / entry
            * 100.0
        )

    return {

        "result":
            result,

        "entry":
            entry,

        "stop_loss":
            stop_loss,

        "take_profit":
            take_profit,

        "exit_price":
            exit_price,

        "pnl_percent":
            pnl_percent,

        "mfe_percent":
            mfe,

        "mae_percent":
            mae,

        "bars_held":
            (
                exit_index
                - entry_index
                + 1
            )
            if exit_index is not None
            else 0,
    }


# ============================================================
# FIND HISTORICAL PATTERN MATCHES
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

    # --------------------------------------------------------
    # Important:
    #
    # candles[-PATTERN_LENGTH:]
    #
    # is the current pattern.
    #
    # Historical pattern must end BEFORE current pattern.
    # Therefore we reserve at least one future candle for
    # historical outcome simulation.
    # --------------------------------------------------------

    latest_pattern_start = (
        len(candles)
        - PATTERN_LENGTH
    )

    first_entry_index = (
        PATTERN_LENGTH
    )

    last_entry_index = (
        latest_pattern_start
    )

    for entry_index in range(
        first_entry_index,
        last_entry_index + 1
    ):

        pattern_start = (

            entry_index
            - PATTERN_LENGTH
        )

        pattern_end = entry_index

        historical_window = candles[
            pattern_start:
            pattern_end
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

        # ----------------------------------------------------
        # ATR at historical point
        # ----------------------------------------------------

        historical_candles = candles[
            :entry_index
        ]

        historical_atr = calculate_atr(
            historical_candles
        )

        if historical_atr <= 0:

            continue

        # ----------------------------------------------------
        # Simulate BUY and SELL separately.
        # This lets us calculate which direction had the
        # better historical TP/SL outcome.
        # ----------------------------------------------------

        buy_trade = (
            simulate_historical_trade(
                candles,
                entry_index,
                "BUY",
                historical_atr
            )
        )

        sell_trade = (
            simulate_historical_trade(
                candles,
                entry_index,
                "SELL",
                historical_atr
            )
        )

        if buy_trade is None:

            continue

        if sell_trade is None:

            continue

        matches.append({

            "index":
                entry_index,

            "similarity":
                similarity,

            "historical_atr":
                historical_atr,

            "buy_result":
                buy_trade["result"],

            "sell_result":
                sell_trade["result"],

            "buy_pnl_percent":
                buy_trade["pnl_percent"],

            "sell_pnl_percent":
                sell_trade["pnl_percent"],

            "buy_mfe_percent":
                buy_trade["mfe_percent"],

            "sell_mfe_percent":
                sell_trade["mfe_percent"],

            "buy_mae_percent":
                buy_trade["mae_percent"],

            "sell_mae_percent":
                sell_trade["mae_percent"],
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
# OUTCOME STATISTICS
# ============================================================

def calculate_direction_statistics(
    matches,
    direction
):

    if not matches:

        return {

            "sample_size":
                0,

            "wins":
                0,

            "losses":
                0,

            "timeouts":
                0,

            "win_probability":
                0.0,

            "loss_probability":
                0.0,

            "timeout_probability":
                0.0,

            "weighted_win_probability":
                0.0,

            "average_similarity":
                0.0,

            "average_win_mfe":
                0.0,

            "average_loss_mae":
                0.0,

            "expected_pnl_percent":
                0.0,
        }

    result_key = (
        f"{direction.lower()}_result"
    )

    pnl_key = (
        f"{direction.lower()}_pnl_percent"
    )

    mfe_key = (
        f"{direction.lower()}_mfe_percent"
    )

    mae_key = (
        f"{direction.lower()}_mae_percent"
    )

    wins = 0

    losses = 0

    timeouts = 0

    total_weight = 0.0

    weighted_wins = 0.0

    similarities = []

    win_mfe = []

    loss_mae = []

    pnl_values = []

    for match in matches:

        result = match[
            result_key
        ]

        similarity = match[
            "similarity"
        ]

        pnl = match[
            pnl_key
        ]

        mfe = match[
            mfe_key
        ]

        mae = match[
            mae_key
        ]

        similarities.append(
            similarity
        )

        pnl_values.append(
            pnl
        )

        # Similar patterns get greater influence.
        weight = max(
            similarity,
            0.01
        )

        total_weight += weight

        if result == "WIN":

            wins += 1

            weighted_wins += weight

            win_mfe.append(
                mfe
            )

        elif result == "LOSS":

            losses += 1

            loss_mae.append(
                mae
            )

        else:

            timeouts += 1

    total = len(matches)

    win_probability = (

        wins
        / total
        * 100.0
    )

    loss_probability = (

        losses
        / total
        * 100.0
    )

    timeout_probability = (

        timeouts
        / total
        * 100.0
    )

    weighted_win_probability = (

        weighted_wins
        / total_weight
        * 100.0

        if total_weight > 0

        else 0.0
    )

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

    sl_distance = (

        atr
        * SL_ATR_MULTIPLIER
    )

    tp_distance = (

        atr
        * TP_ATR_MULTIPLIER
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

    elif direction == "SELL":

        stop_loss = (
            entry
            + sl_distance
        )

        take_profit = (
            entry
            - tp_distance
        )

    else:

        return (
            round_price(entry),
            None,
            None
        )

    return (

        round_price(entry),

        round_price(stop_loss),

        round_price(take_profit)
    )


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    probability,
    similarity,
    sample_size,
    risk_reward
):

    probability_component = min(
        probability,
        100.0
    )

    similarity_component = (

        max(
            0.0,
            min(
                similarity,
                1.0
            )
        )
        * 100.0
    )

    sample_component = min(

        (
            sample_size
            / MAX_MATCHES
        )
        * 100.0,

        100.0
    )

    # --------------------------------------------------------
    # Risk / Reward score
    #
    # 1.5 R:R = 100
    # 1.0 R:R = 66.7
    # 2.0 R:R = 100 (capped)
    # --------------------------------------------------------

    rr_component = min(

        (
            risk_reward
            / 1.5
        )
        * 100.0,

        100.0
    )

    score = (

        probability_component
        * WEIGHT_PROBABILITY

        +

        similarity_component
        * WEIGHT_SIMILARITY

        +

        sample_component
        * WEIGHT_SAMPLE

        +

        rr_component
        * WEIGHT_RISK_REWARD
    )

    return round(
        score,
        2
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

    buy_stats = (
        calculate_direction_statistics(
            matches,
            "BUY"
        )
    )

    sell_stats = (
        calculate_direction_statistics(
            matches,
            "SELL"
        )
    )

    # --------------------------------------------------------
    # No matches
    # --------------------------------------------------------

    if len(matches) == 0:

        return {

            "timestamp":
                latest["datetime"],

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
                round_price(entry),

            "stop_loss":
                None,

            "take_profit":
                None,

            "atr":
                round(
                    atr,
                    4
                ),

            "historical_statistics": {

                "sample_size":
                    0,

                "buy":
                    buy_stats,

                "sell":
                    sell_stats,
            },

            "matched_patterns":
                0,

            "method":
                "Outcome-Based M5 Historical Pattern Matching",

            "data_source":
                "Twelve Data XAU/USD"
        }

    # --------------------------------------------------------
    # Direction probabilities
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Select direction
    # --------------------------------------------------------

    if buy_probability > sell_probability:

        direction = "BUY"

        probability = (
            buy_probability
        )

        selected_stats = (
            buy_stats
        )

    elif sell_probability > buy_probability:

        direction = "SELL"

        probability = (
            sell_probability
        )

        selected_stats = (
            sell_stats
        )

    else:

        direction = "NO_TRADE"

        probability = 0.0

        selected_stats = {
            "average_similarity":
                0.0
        }

    # --------------------------------------------------------
    # Trade levels
    # --------------------------------------------------------

    if direction in [
        "BUY",
        "SELL"
    ]:

        (
            entry_price,
            stop_loss,
            take_profit
        ) = calculate_trade_levels(

            direction,

            entry,

            atr
        )

        risk = abs(
            entry_price
            - stop_loss
        )

        reward = abs(
            take_profit
            - entry_price
        )

        risk_reward = (

            reward / risk

            if risk > 0

            else 0.0
        )

        score = calculate_score(

            probability,

            selected_stats[
                "average_similarity"
            ],

            len(matches),

            risk_reward
        )

    else:

        entry_price = round_price(
            entry
        )

        stop_loss = None

        take_profit = None

        risk_reward = 0.0

        score = 0.0

    # --------------------------------------------------------
    # Signal validation
    # --------------------------------------------------------

    valid = (

        direction
        in [
            "BUY",
            "SELL"
        ]

        and probability
        >= MIN_PROBABILITY

        and score
        >= MIN_SCORE

        and len(matches)
        >= MIN_MATCHES
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

            "score":
                round(
                    score,
                    2
                ),

            "probability":
                round(
                    probability,
                    2
                ),

            "candidate_direction":
                direction,

            "entry":
                entry_price,

            "stop_loss":
                None,

            "take_profit":
                None,

            "atr":
                round(
                    atr,
                    4
                ),

            "risk_reward":
                round(
                    risk_reward,
                    2
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

            "rules": {

                "minimum_probability":
                    MIN_PROBABILITY,

                "minimum_score":
                    MIN_SCORE,

                "minimum_patterns":
                    MIN_MATCHES,

                "minimum_similarity":
                    MIN_SIMILARITY,
            },

            "method":
                "Outcome-Based M5 Historical Pattern Matching",

            "data_source":
                "Twelve Data XAU/USD"
        }

    # --------------------------------------------------------
    # Valid signal
    # --------------------------------------------------------

    return {

        "timestamp":
            latest["datetime"],

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "signal":
            direction,

        "score":
            round(
                score,
                2
            ),

        "probability":
            round(
                probability,
                2
            ),

        "entry":
            entry_price,

        "stop_loss":
            stop_loss,

        "take_profit":
            take_profit,

        "atr":
            round(
                atr,
                4
            ),

        "risk_reward":
            round(
                risk_reward,
                2
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

        "rules": {

            "minimum_probability":
                MIN_PROBABILITY,

            "minimum_score":
                MIN_SCORE,

            "minimum_patterns":
                MIN_MATCHES,

            "minimum_similarity":
                MIN_SIMILARITY,
        },

        "method":
            "Outcome-Based M5 Historical Pattern Matching",

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
            "HTML",

        "disable_web_page_preview":
            True,
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
# TELEGRAM WELCOME
# ============================================================

def send_startup_notification():

    if STATE[
        "startup_notification_sent"
    ]:

        return

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram welcome skipped: "
            "TELEGRAM_BOT_TOKEN not configured"
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "Telegram welcome skipped: "
            "TELEGRAM_CHAT_ID not configured"
        )

        return

    message = (

        "🟢 <b>XAUUSD M5 BOT ONLINE</b>\n"

        "\n"

        "ระบบเริ่มทำงานเรียบร้อยแล้ว\n"

        "\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>Symbol:</b> {SYMBOL}\n"

        "<b>Timeframe:</b> M5\n"

        "<b>Data:</b> Twelve Data\n"

        "<b>Engine:</b> Historical Pattern + TP/SL Outcome\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "\n"

        f"<b>Minimum Probability:</b> "
        f"{MIN_PROBABILITY:.0f}%\n"

        f"<b>Minimum Score:</b> "
        f"{MIN_SCORE:.0f}\n"

        f"<b>Minimum Patterns:</b> "
        f"{MIN_MATCHES}\n"

        f"<b>Minimum Similarity:</b> "
        f"{MIN_SIMILARITY:.2f}\n"

        "\n"

        f"<b>SL:</b> {SL_ATR_MULTIPLIER:.2f} ATR\n"

        f"<b>TP:</b> {TP_ATR_MULTIPLIER:.2f} ATR\n"

        f"<b>Forward Bars:</b> {FORWARD_BARS}\n"

        "\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "ระบบพร้อมวิเคราะห์ BUY / SELL\n"

        "หากไม่ผ่านเกณฑ์จะเป็น NO_TRADE\n"

        "\n"

        "⚠️ <i>Signal เป็นข้อมูลเพื่อการวิเคราะห์ "
        "ไม่ใช่คำแนะนำการลงทุน</i>"
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        STATE[
            "startup_notification_sent"
        ] = True

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

    selected = stats[
        direction.lower()
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

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"

        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"

        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"

        f"<b>Risk/Reward:</b> "
        f"{signal['risk_reward']:.2f}\n"

        "\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"<b>Patterns:</b> "
        f"{signal['matched_patterns']}\n"

        f"<b>Weighted Win Probability:</b> "
        f"{selected['weighted_win_probability']:.2f}%\n"

        f"<b>Historical Wins:</b> "
        f"{selected['wins']}\n"

        f"<b>Historical Losses:</b> "
        f"{selected['losses']}\n"

        f"<b>Timeouts:</b> "
        f"{selected['timeouts']}\n"

        f"<b>Average Similarity:</b> "
        f"{selected['average_similarity']:.4f}\n"

        "\n"

        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"

        "\n"

        "<i>Outcome-Based Historical Pattern Matching</i>\n"

        "\n"

        "⚠️ <i>ข้อมูลนี้เป็นระบบวิเคราะห์ "
        "ไม่ใช่คำแนะนำการลงทุน</i>"
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

    # --------------------------------------------------------
    # Telegram Signal
    # --------------------------------------------------------

    if (

        send_notification

        and signal[
            "signal"
        ]
        in [
            "BUY",
            "SELL"
        ]
    ):

        signal_key = (

            str(
                signal[
                    "timestamp"
                ]
            )

            + "_"

            + signal[
                "signal"
            ]
        )

        if STATE[
            "last_signal_key"
        ] != signal_key:

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
# HOME
# ============================================================

@app.route("/")
def home():

    send_startup_notification()

    return jsonify({

        "name":
            "XAUUSD M5 Telegram Signal",

        "status":
            "online",

        "engine":
            "Outcome-Based Historical Pattern Matching",

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
        },

        "trade_settings": {

            "atr_period":
                ATR_PERIOD,

            "sl_atr_multiplier":
                SL_ATR_MULTIPLIER,

            "tp_atr_multiplier":
                TP_ATR_MULTIPLIER,

            "forward_bars":
                FORWARD_BARS,
        },

        "endpoints": [

            "/",

            "/health",

            "/signal",

            "/backtest",

            "/test-data",

            "/test-telegram"
        ]
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    send_startup_notification()

    return jsonify({

        "status":
            "healthy",

        "engine":
            "Outcome-Based Historical Pattern Matching",

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
# TEST DATA
# ============================================================

@app.route("/test-data")
def test_data():

    try:

        candles = get_candles()

        latest = candles[
            -1
        ]

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

                {

                    "datetime":
                        latest["datetime"],

                    "open":
                        latest["open"],

                    "high":
                        latest["high"],

                    "low":
                        latest["low"],

                    "close":
                        latest["close"],
                }
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
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (

        "🟢 <b>TELEGRAM TEST SUCCESS</b>\n"

        "\n"

        "ระบบ XAUUSD M5 สามารถส่งข้อความมายัง Telegram ได้แล้ว\n"

        "\n"

        f"<b>Symbol:</b> {SYMBOL}\n"

        "<b>Timeframe:</b> M5\n"

        f"<b>Server Time:</b> "
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
                False,

            "error":
                error
        }), 500

    return jsonify({

        "status":
            "success",

        "telegram":
            True,

        "message":
            "Telegram test message sent successfully"
    })


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        send_startup_notification()

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

        # ----------------------------------------------------
        # We need enough candles before each test point to
        # calculate ATR + pattern.
        # ----------------------------------------------------

        minimum_start = max(

            PATTERN_LENGTH
            + ATR_PERIOD
            + FORWARD_BARS,

            80
        )

        end = (
            total_candles
            - FORWARD_BARS
        )

        if end <= minimum_start:

            return jsonify({

                "status":
                    "error",

                "error":
                    "Not enough candles for backtest"
            }), 400

        requested_points = 150

        start = max(

            minimum_start,

            end
            - requested_points
        )

        test_points = (
            end
            - start
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
        # WALK FORWARD
        # ----------------------------------------------------

        for i in range(
            start,
            end
        ):

            historical_candles = (
                candles[
                    :i
                ]
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

            # ------------------------------------------------
            # IMPORTANT:
            #
            # Signal generated using candles[:i]
            #
            # Entry = candle i close
            #
            # Future simulation starts at candle i+1
            #
            # ------------------------------------------------

            entry_price = float(
                entry
            )

            stop_price = float(
                stop_loss
            )

            target_price = float(
                take_profit
            )

            result = "TIMEOUT"

            exit_price = None

            exit_index = None

            mfe = 0.0

            mae = 0.0

            future_start = i

            future_end = min(

                i
                + FORWARD_BARS,

                len(candles)
            )

            for j in range(
                future_start,
                future_end
            ):

                candle = candles[
                    j
                ]

                high = float(
                    candle["high"]
                )

                low = float(
                    candle["low"]
                )

                if direction == "BUY":

                    favorable = (

                        (
                            high
                            - entry_price
                        )
                        / entry_price
                        * 100.0
                    )

                    adverse = (

                        (
                            entry_price
                            - low
                        )
                        / entry_price
                        * 100.0
                    )

                    mfe = max(
                        mfe,
                        favorable
                    )

                    mae = max(
                        mae,
                        adverse
                    )

                    hit_sl = (
                        low
                        <= stop_price
                    )

                    hit_tp = (
                        high
                        >= target_price
                    )

                else:

                    favorable = (

                        (
                            entry_price
                            - low
                        )
                        / entry_price
                        * 100.0
                    )

                    adverse = (

                        (
                            high
                            - entry_price
                        )
                        / entry_price
                        * 100.0
                    )

                    mfe = max(
                        mfe,
                        favorable
                    )

                    mae = max(
                        mae,
                        adverse
                    )

                    hit_sl = (
                        high
                        >= stop_price
                    )

                    hit_tp = (
                        low
                        <= target_price
                    )

                # Conservative:
                # both TP and SL same candle => LOSS

                if hit_sl and hit_tp:

                    result = "LOSS"

                    exit_price = (
                        stop_price
                    )

                    exit_index = j

                    break

                if hit_sl:

                    result = "LOSS"

                    exit_price = (
                        stop_price
                    )

                    exit_index = j

                    break

                if hit_tp:

                    result = "WIN"

                    exit_price = (
                        target_price
                    )

                    exit_index = j

                    break

            if result == "TIMEOUT":

                exit_index = (
                    future_end
                    - 1
                )

                exit_price = float(
                    candles[
                        exit_index
                    ]["close"]
                )

            if direction == "BUY":

                pnl_percent = (

                    (
                        exit_price
                        - entry_price
                    )
                    / entry_price
                    * 100.0
                )

            else:

                pnl_percent = (

                    (
                        entry_price
                        - exit_price
                    )
                    / entry_price
                    * 100.0
                )

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

                    0.0
                )

            elif result == "LOSS":

                losses += 1

                sl_hits += 1

                total_loss_percent += abs(

                    min(
                        pnl_percent,
                        0.0
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
                        entry_price,
                        2
                    ),

                "stop_loss":
                    round(
                        stop_price,
                        2
                    ),

                "take_profit":
                    round(
                        target_price,
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
                        exit_index
                        - i
                        + 1
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

            sum(
                probability_values
            )
            / len(
                probability_values
            )

            if probability_values

            else 0.0
        )

        average_score = (

            sum(
                score_values
            )
            / len(
                score_values
            )

            if score_values

            else 0.0
        )

        # ----------------------------------------------------
        # Profit Factor
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Net
        # ----------------------------------------------------

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
        # DIRECTION PERFORMANCE
        # ====================================================

        buy_results = [

            trade

            for trade in trade_results

            if trade["signal"] == "BUY"
        ]

        sell_results = [

            trade

            for trade in trade_results

            if trade["signal"] == "SELL"
        ]

        def direction_summary(
            trades
        ):

            if not trades:

                return {

                    "trades":
                        0,

                    "wins":
                        0,

                    "losses":
                        0,

                    "timeouts":
                        0,

                    "win_rate_percent":
                        0.0,

                    "net_profit_percent":
                        0.0,
                }

            d_wins = sum(

                1

                for t in trades

                if t["result"] == "WIN"
            )

            d_losses = sum(

                1

                for t in trades

                if t["result"] == "LOSS"
            )

            d_timeouts = sum(

                1

                for t in trades

                if t["result"] == "TIMEOUT"
            )

            d_net = sum(

                t["pnl_percent"]

                for t in trades
            )

            return {

                "trades":
                    len(trades),

                "wins":
                    d_wins,

                "losses":
                    d_losses,

                "timeouts":
                    d_timeouts,

                "win_rate_percent":
                    round(

                        d_wins
                        / len(trades)
                        * 100.0,

                        2
                    ),

                "net_profit_percent":
                    round(
                        d_net,
                        4
                    ),
            }

        buy_summary = (
            direction_summary(
                buy_results
            )
        )

        sell_summary = (
            direction_summary(
                sell_results
            )
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

            "engine":
                "Outcome-Based Historical Pattern Matching",

            "data_source":
                "Twelve Data XAU/USD",

            "candles_available":
                total_candles,

            "test_points":
                test_points,

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
            },

            "trade_settings": {

                "atr_period":
                    ATR_PERIOD,

                "sl_atr_multiplier":
                    SL_ATR_MULTIPLIER,

                "tp_atr_multiplier":
                    TP_ATR_MULTIPLIER,

                "risk_reward":
                    round(
                        TP_ATR_MULTIPLIER
                        / SL_ATR_MULTIPLIER,
                        2
                    ),
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

            "direction_performance": {

                "BUY":
                    buy_summary,

                "SELL":
                    sell_summary,
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
                trade_results[
                    -20:
                ],

            "warning":
                "Historical simulation only. "
                "Spread, slippage, commission, "
                "market execution and broker-specific "
                "conditions are not included."
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

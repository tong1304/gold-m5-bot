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

# ------------------------------------------------------------
# SIGNAL REQUIREMENTS
# ------------------------------------------------------------

MIN_PROBABILITY = 70.0
MIN_SCORE = 65.0
MIN_MATCHES = 20

# ------------------------------------------------------------
# TRADE SETTINGS
# ------------------------------------------------------------

RISK_REWARD = 1.50

ATR_PERIOD = 14

SL_ATR_MULTIPLIER = 1.00

FORWARD_BARS = 12

# ------------------------------------------------------------
# HISTORICAL OUTCOME SETTINGS
# ------------------------------------------------------------

HISTORICAL_TP_ATR = 1.00
HISTORICAL_SL_ATR = 1.00

# ------------------------------------------------------------
# TREND SETTINGS
# ------------------------------------------------------------

FAST_EMA_PERIOD = 20
SLOW_EMA_PERIOD = 50

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
            "No candle data received"
        )

    candles = []

    for item in values:

        try:

            candles.append({

                "datetime":
                    item["datetime"],

                "open":
                    float(item["open"]),

                "high":
                    float(item["high"]),

                "low":
                    float(item["low"]),

                "close":
                    float(item["close"])

            })

        except Exception:

            continue

    # Twelve Data normally returns newest first.
    # Convert to oldest -> newest.

    candles.reverse()

    minimum_required = max(
        PATTERN_LENGTH * 2 + 20,
        SLOW_EMA_PERIOD + 20
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

        previous = candles[i - 1]

        high = current["high"]

        low = current["low"]

        previous_close = previous["close"]

        tr1 = high - low

        tr2 = abs(
            high - previous_close
        )

        tr3 = abs(
            low - previous_close
        )

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
# EMA
# ============================================================

def calculate_ema(
    candles,
    period
):

    if len(candles) < period:

        return 0.0

    closes = [
        candle["close"]
        for candle in candles
    ]

    multiplier = (
        2.0
        / (period + 1.0)
    )

    ema = (
        sum(
            closes[:period]
        )
        / period
    )

    for price in closes[period:]:

        ema = (
            (price - ema)
            * multiplier
            + ema
        )

    return ema


# ============================================================
# TREND
# ============================================================

def detect_trend(
    candles
):

    if len(candles) < SLOW_EMA_PERIOD:

        return {
            "direction": "UNKNOWN",
            "fast_ema": 0.0,
            "slow_ema": 0.0,
            "close": candles[-1]["close"]
        }

    fast_ema = calculate_ema(
        candles,
        FAST_EMA_PERIOD
    )

    slow_ema = calculate_ema(
        candles,
        SLOW_EMA_PERIOD
    )

    close = candles[-1]["close"]

    if (
        close > fast_ema
        and fast_ema > slow_ema
    ):

        direction = "BUY"

    elif (
        close < fast_ema
        and fast_ema < slow_ema
    ):

        direction = "SELL"

    else:

        direction = "NEUTRAL"

    return {

        "direction":
            direction,

        "fast_ema":
            round_price(fast_ema),

        "slow_ema":
            round_price(slow_ema),

        "close":
            round_price(close)
    }


# ============================================================
# NORMALIZED PATTERN
# ============================================================

def make_pattern(
    candles
):

    if len(candles) < PATTERN_LENGTH:

        return None

    window = candles[
        -PATTERN_LENGTH:
    ]

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
# HISTORICAL MATCH
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

        if historical_close <= 0:

            continue

        # ATR at historical point
        historical_candles = candles[:i]

        historical_atr = calculate_atr(
            historical_candles
        )

        if historical_atr <= 0:

            historical_atr = (
                historical_close
                * 0.001
            )

        tp_distance = (
            historical_atr
            * HISTORICAL_TP_ATR
        )

        sl_distance = (
            historical_atr
            * HISTORICAL_SL_ATR
        )

        buy_tp = (
            historical_close
            + tp_distance
        )

        buy_sl = (
            historical_close
            - sl_distance
        )

        sell_tp = (
            historical_close
            - tp_distance
        )

        sell_sl = (
            historical_close
            + sl_distance
        )

        result_buy = "TIMEOUT"
        result_sell = "TIMEOUT"

        max_index = min(
            i + FORWARD_BARS,
            len(candles) - 1
        )

        buy_mfe = 0.0
        buy_mae = 0.0

        sell_mfe = 0.0
        sell_mae = 0.0

        buy_exit = None
        sell_exit = None

        # ----------------------------------------------------
        # BUY / SELL OUTCOME
        # ----------------------------------------------------

        for j in range(
            i,
            max_index + 1
        ):

            candle = candles[j]

            high = candle["high"]

            low = candle["low"]

            # BUY MFE / MAE

            buy_favorable = (
                high
                - historical_close
            ) / historical_close * 100.0

            buy_adverse = (
                historical_close
                - low
            ) / historical_close * 100.0

            buy_mfe = max(
                buy_mfe,
                buy_favorable
            )

            buy_mae = max(
                buy_mae,
                buy_adverse
            )

            buy_hit_sl = (
                low <= buy_sl
            )

            buy_hit_tp = (
                high >= buy_tp
            )

            if (
                result_buy == "TIMEOUT"
                and (
                    buy_hit_sl
                    or buy_hit_tp
                )
            ):

                # Conservative:
                # if both happen in one candle,
                # SL is considered first.

                if (
                    buy_hit_sl
                    and buy_hit_tp
                ):

                    result_buy = "LOSS"

                    buy_exit = buy_sl

                elif buy_hit_sl:

                    result_buy = "LOSS"

                    buy_exit = buy_sl

                else:

                    result_buy = "WIN"

                    buy_exit = buy_tp

            # SELL MFE / MAE

            sell_favorable = (
                historical_close
                - low
            ) / historical_close * 100.0

            sell_adverse = (
                high
                - historical_close
            ) / historical_close * 100.0

            sell_mfe = max(
                sell_mfe,
                sell_favorable
            )

            sell_mae = max(
                sell_mae,
                sell_adverse
            )

            sell_hit_sl = (
                high >= sell_sl
            )

            sell_hit_tp = (
                low <= sell_tp
            )

            if (
                result_sell == "TIMEOUT"
                and (
                    sell_hit_sl
                    or sell_hit_tp
                )
            ):

                if (
                    sell_hit_sl
                    and sell_hit_tp
                ):

                    result_sell = "LOSS"

                    sell_exit = sell_sl

                elif sell_hit_sl:

                    result_sell = "LOSS"

                    sell_exit = sell_sl

                else:

                    result_sell = "WIN"

                    sell_exit = sell_tp

        # ----------------------------------------------------
        # TIMEOUT EXIT
        # ----------------------------------------------------

        if result_buy == "TIMEOUT":

            buy_exit = candles[
                max_index
            ]["close"]

        if result_sell == "TIMEOUT":

            sell_exit = candles[
                max_index
            ]["close"]

        # ----------------------------------------------------
        # BUY PNL
        # ----------------------------------------------------

        buy_pnl = (
            buy_exit
            - historical_close
        ) / historical_close * 100.0

        # ----------------------------------------------------
        # SELL PNL
        # ----------------------------------------------------

        sell_pnl = (
            historical_close
            - sell_exit
        ) / historical_close * 100.0

        matches.append({

            "index":
                i,

            "similarity":
                similarity,

            "buy_result":
                result_buy,

            "sell_result":
                result_sell,

            "buy_pnl":
                buy_pnl,

            "sell_pnl":
                sell_pnl,

            "buy_mfe":
                buy_mfe,

            "buy_mae":
                buy_mae,

            "sell_mfe":
                sell_mfe,

            "sell_mae":
                sell_mae

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

            "expected_pnl_percent":
                0.0,

            "average_similarity":
                0.0,

            "average_win_mfe":
                0.0,

            "average_loss_mae":
                0.0
        }

    wins = 0
    losses = 0
    timeouts = 0

    weighted_wins = 0.0
    weighted_total = 0.0

    pnl_values = []

    similarities = []

    win_mfe_values = []

    loss_mae_values = []

    for match in matches:

        similarity = float(
            match["similarity"]
        )

        similarities.append(
            similarity
        )

        if direction == "BUY":

            result = match[
                "buy_result"
            ]

            pnl = match[
                "buy_pnl"
            ]

            mfe = match[
                "buy_mfe"
            ]

            mae = match[
                "buy_mae"
            ]

        else:

            result = match[
                "sell_result"
            ]

            pnl = match[
                "sell_pnl"
            ]

            mfe = match[
                "sell_mfe"
            ]

            mae = match[
                "sell_mae"
            ]

        pnl_values.append(
            pnl
        )

        # Similarity weight
        weight = (
            similarity
            * similarity
        )

        weighted_total += weight

        if result == "WIN":

            wins += 1

            weighted_wins += weight

            win_mfe_values.append(
                mfe
            )

        elif result == "LOSS":

            losses += 1

            loss_mae_values.append(
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

    if weighted_total > 0:

        weighted_win_probability = (
            weighted_wins
            / weighted_total
            * 100.0
        )

    else:

        weighted_win_probability = 0.0

    expected_pnl = (
        sum(pnl_values)
        / len(pnl_values)
        if pnl_values
        else 0.0
    )

    average_similarity = (
        sum(similarities)
        / len(similarities)
    )

    average_win_mfe = (
        sum(win_mfe_values)
        / len(win_mfe_values)
        if win_mfe_values
        else 0.0
    )

    average_loss_mae = (
        sum(loss_mae_values)
        / len(loss_mae_values)
        if loss_mae_values
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

        "expected_pnl_percent":
            round(
                expected_pnl,
                4
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
            )
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
# SCORE
# ============================================================

def calculate_score(
    probability,
    matches,
    average_similarity,
    trend_ok,
    expected_pnl
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

    if trend_ok:

        trend_component = 100.0

    else:

        trend_component = 0.0

    # Positive expected PnL gets full credit.
    # Negative expected PnL gets reduced credit.

    if expected_pnl > 0:

        pnl_component = 100.0

    elif expected_pnl == 0:

        pnl_component = 50.0

    else:

        pnl_component = max(
            0.0,
            50.0
            + expected_pnl * 500.0
        )

    score = (

        probability_component
        * 0.40

        +

        sample_component
        * 0.10

        +

        similarity_component
        * 0.20

        +

        trend_component
        * 0.15

        +

        pnl_component
        * 0.15

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

    latest = candles[-1]

    entry = latest["close"]

    atr = calculate_atr(
        candles
    )

    trend = detect_trend(
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
                "NONE",

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
                round(atr, 4),

            "trend":
                trend,

            "historical_statistics":
                {},

            "matched_patterns":
                0,

            "risk_reward":
                RISK_REWARD,

            "method":
                "Outcome-Based M5 Historical Pattern Matching",

            "data_source":
                "Twelve Data XAU/USD"
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

    # --------------------------------------------------------
    # Candidate
    # --------------------------------------------------------

    if buy_probability > sell_probability:

        candidate = "BUY"

        probability = buy_probability

        expected_pnl = buy_stats[
            "expected_pnl_percent"
        ]

        average_similarity = buy_stats[
            "average_similarity"
        ]

    elif sell_probability > buy_probability:

        candidate = "SELL"

        probability = sell_probability

        expected_pnl = sell_stats[
            "expected_pnl_percent"
        ]

        average_similarity = sell_stats[
            "average_similarity"
        ]

    else:

        candidate = "NONE"

        probability = 0.0

        expected_pnl = 0.0

        average_similarity = (
            (
                buy_stats[
                    "average_similarity"
                ]
                +
                sell_stats[
                    "average_similarity"
                ]
            )
            / 2.0
        )

    # --------------------------------------------------------
    # Trend Filter
    # --------------------------------------------------------

    trend_ok = (

        candidate != "NONE"

        and

        (
            trend["direction"]
            == candidate
        )

    )

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    score = calculate_score(

        probability,

        matches,

        average_similarity,

        trend_ok,

        expected_pnl

    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    enough_patterns = (
        len(matches)
        >= MIN_MATCHES
    )

    probability_ok = (
        probability
        >= MIN_PROBABILITY
    )

    score_ok = (
        score
        >= MIN_SCORE
    )

    expected_pnl_ok = (
        expected_pnl
        > 0
    )

    valid = (

        candidate
        in ["BUY", "SELL"]

        and enough_patterns

        and probability_ok

        and score_ok

        and trend_ok

        and expected_pnl_ok

    )

    if not valid:

        final_signal = "NO_TRADE"

        stop_loss = None

        take_profit = None

    else:

        final_signal = candidate

        (
            entry,
            stop_loss,
            take_profit
        ) = calculate_trade_levels(

            candidate,

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
            final_signal,

        "candidate_direction":
            candidate,

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
            stop_loss,

        "take_profit":
            take_profit,

        "atr":
            round(
                atr,
                4
            ),

        "risk_reward":
            RISK_REWARD,

        "trend":
            trend,

        "filters": {

            "enough_patterns":
                enough_patterns,

            "probability_ok":
                probability_ok,

            "score_ok":
                score_ok,

            "trend_ok":
                trend_ok,

            "expected_pnl_ok":
                expected_pnl_ok
        },

        "expected_pnl_percent":
            round(
                expected_pnl,
                4
            ),

        "historical_statistics": {

            "buy":
                buy_stats,

            "sell":
                sell_stats,

            "sample_size":
                len(matches)
        },

        "matched_patterns":
            len(matches),

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
# TELEGRAM WELCOME
# ============================================================

def send_startup_notification():

    global STARTUP_NOTIFICATION_SENT

    if STARTUP_NOTIFICATION_SENT:

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
        "พร้อมวิเคราะห์ตลาด XAU/USD\n"
        "\n"

        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"
        "<b>Data:</b> Twelve Data\n"
        "\n"

        "<b>Signal Engine</b>\n"
        "Outcome-Based Historical Pattern\n"
        "Similarity Weighted Probability\n"
        "Trend Filter\n"
        "Expected PnL Filter\n"
        "\n"

        f"<b>Minimum Probability:</b> "
        f"{MIN_PROBABILITY:.0f}%\n"

        f"<b>Minimum Score:</b> "
        f"{MIN_SCORE:.0f}\n"

        f"<b>Minimum Patterns:</b> "
        f"{MIN_MATCHES}\n"

        f"<b>Minimum Similarity:</b> "
        f"{MIN_SIMILARITY:.2f}\n"

        f"<b>Risk / Reward:</b> "
        f"1:{RISK_REWARD:.2f}\n"

        "\n"

        "📊 ระบบจะส่ง BUY / SELL "
        "เมื่อผ่านเงื่อนไขทั้งหมด\n"

        "🛑 หากไม่ผ่านเกณฑ์ ระบบจะไม่ส่ง Signal"

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
# TELEGRAM SIGNAL
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

    buy = stats["buy"]

    sell = stats["sell"]

    return (

        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"

        f"<b>SIGNAL:</b> {direction}\n"

        f"<b>Probability:</b> "
        f"{signal['probability']:.2f}%\n"

        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"

        f"<b>Expected PnL:</b> "
        f"{signal['expected_pnl_percent']:.4f}%\n"

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

        f"<b>Trend:</b> "
        f"{signal['trend']['direction']}\n"

        f"<b>Fast EMA:</b> "
        f"{signal['trend']['fast_ema']:.2f}\n"

        f"<b>Slow EMA:</b> "
        f"{signal['trend']['slow_ema']:.2f}\n"

        "\n"

        f"<b>BUY Weighted Win:</b> "
        f"{buy['weighted_win_probability']:.2f}%\n"

        f"<b>SELL Weighted Win:</b> "
        f"{sell['weighted_win_probability']:.2f}%\n"

        "\n"

        f"<b>BUY Expected PnL:</b> "
        f"{buy['expected_pnl_percent']:.4f}%\n"

        f"<b>SELL Expected PnL:</b> "
        f"{sell['expected_pnl_percent']:.4f}%\n"

        "\n"

        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"

        "\n"

        "<i>Outcome-Based Historical Pattern Matching</i>"

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
    # TELEGRAM SIGNAL
    # --------------------------------------------------------

    if (

        send_notification

        and

        signal["signal"]
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

            STATE[
                "last_signal_key"
            ]

            != signal_key

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
            "2.0 Outcome-Based",

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
                RISK_REWARD

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
# TEST DATA
# ============================================================

@app.route("/test-data")
def test_data():

    try:

        candles = get_candles()

        latest = candles[-1]

        atr = calculate_atr(
            candles
        )

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

            "atr":
                round(
                    atr,
                    4
                )

        })

    except Exception as exc:

        return jsonify({

            "status":
                "error",

            "message":
                str(exc)

        }), 500


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (

        "🟢 <b>XAUUSD M5 BOT TEST</b>\n"
        "\n"
        "Telegram connection is working.\n"
        "\n"
        "ระบบสามารถส่งข้อความได้แล้ว"

    )

    ok, error = send_telegram(
        message
    )

    if ok:

        return jsonify({

            "status":
                "success",

            "message":
                "Telegram test message sent successfully",

            "telegram":
                True

        })

    return jsonify({

        "status":
            "error",

        "message":
            error,

        "telegram":
            False

    }), 500


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        # Ensure startup message
        # is sent if the service was started
        # before the first request.

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

        start = max(

            SLOW_EMA_PERIOD + 20,

            PATTERN_LENGTH * 2 + 20,

            80

        )

        end = (
            total_candles - FORWARD_BARS - 1
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

        total_profit_percent = 0.0

        total_loss_percent = 0.0

        probability_values = []

        score_values = []

        trade_results = []

        # ----------------------------------------------------
        # TEST EACH HISTORICAL POINT
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

            if (

                entry is None

                or stop_loss is None

                or take_profit is None

            ):

                continue

            signals += 1

            if direction == "BUY":

                buy_signals += 1

            else:

                sell_signals += 1

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

            probability_values.append(
                probability
            )

            score_values.append(
                score
            )

            entry = float(entry)

            stop_loss = float(
                stop_loss
            )

            take_profit = float(
                take_profit
            )

            max_index = min(

                i + FORWARD_BARS,

                len(candles) - 1

            )

            result = "TIMEOUT"

            exit_price = None

            exit_index = None

            mfe = 0.0

            mae = 0.0

            # ------------------------------------------------
            # FORWARD SIMULATION
            # ------------------------------------------------

            for j in range(
                i,
                max_index + 1
            ):

                candle = candles[j]

                high = candle["high"]

                low = candle["low"]

                if direction == "BUY":

                    favorable = (

                        high
                        - entry

                    ) / entry * 100.0

                    adverse = (

                        entry
                        - low

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

                    if (
                        hit_sl
                        and hit_tp
                    ):

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

                        entry
                        - low

                    ) / entry * 100.0

                    adverse = (

                        high
                        - entry

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

                    if (
                        hit_sl
                        and hit_tp
                    ):

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
            # TIMEOUT
            # ------------------------------------------------

            if result == "TIMEOUT":

                exit_index = max_index

                exit_price = float(
                    candles[
                        exit_index
                    ]["close"]
                )

            # ------------------------------------------------
            # PNL
            # ------------------------------------------------

            if direction == "BUY":

                pnl_percent = (

                    exit_price
                    - entry

                ) / entry * 100.0

            else:

                pnl_percent = (

                    entry
                    - exit_price

                ) / entry * 100.0

            # ------------------------------------------------
            # RESULTS
            # ------------------------------------------------

            if result == "WIN":

                wins += 1

                total_profit_percent += max(

                    pnl_percent,

                    0.0

                )

            elif result == "LOSS":

                losses += 1

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
                    candles[i]["datetime"],

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

        # ====================================================
        # DRAWDOWN
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
        # AVERAGES
        # ====================================================

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

        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "status":
                "completed",

            "version":
                "2.0 Outcome-Based",

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

                "risk_reward":
                    RISK_REWARD,

                "forward_bars":
                    FORWARD_BARS

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
                    timeouts

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

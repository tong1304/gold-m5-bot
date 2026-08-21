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

DISPLAY_TIMEFRAME = "M5"

CANDLE_LIMIT = 1000

REQUEST_TIMEOUT = 30


# ============================================================
# INDICATOR CONFIG
# ============================================================

EMA_FAST_PERIOD = 20

EMA_SLOW_PERIOD = 50

RSI_PERIOD = 14

ATR_PERIOD = 14

SR_LOOKBACK = 50


# ============================================================
# SIGNAL CONFIG
# ============================================================

MIN_SCORE = 70.0

MIN_RISK_REWARD = 1.30

MIN_ATR = 0.50

MAX_ENTRY_DISTANCE_ATR = 0.80

SIGNAL_COOLDOWN_BARS = 1


# ============================================================
# TRADE CONFIG
# ============================================================

SL_ATR_MULTIPLIER = 1.20

TP_ATR_MULTIPLIER = 1.80


# ============================================================
# STATE
# ============================================================

STATE = {
    "status": "starting",
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
    "startup_notification_sent": False,
    "telegram_last_error": None,
}


STARTUP_LOCK = threading.Lock()


# ============================================================
# TIME
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


# ============================================================
# HELPERS
# ============================================================

def round_price(value):

    if value is None:
        return None

    return round(
        float(value),
        2
    )


def clamp(
    value,
    minimum=0.0,
    maximum=100.0
):

    return max(
        minimum,
        min(
            maximum,
            float(value)
        )
    )


def safe_float(value):

    try:

        return float(value)

    except Exception:

        return 0.0


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
        timeout=REQUEST_TIMEOUT
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

                "datetime":
                    item["datetime"],

                "open":
                    float(
                        item["open"]
                    ),

                "high":
                    float(
                        item["high"]
                    ),

                "low":
                    float(
                        item["low"]
                    ),

                "close":
                    float(
                        item["close"]
                    )

            })

        except Exception:

            continue

    candles.reverse()

    minimum_required = max(
        100,
        EMA_SLOW_PERIOD + 30
    )

    if len(candles) < minimum_required:

        raise RuntimeError(
            "Not enough M5 candles"
        )

    return candles


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    values,
    period
):

    if not values:

        return []

    if len(values) < period:

        return [None] * len(values)

    multiplier = (
        2.0
        / (period + 1.0)
    )

    result = [None] * len(values)

    sma = sum(
        values[:period]
    ) / period

    result[
        period - 1
    ] = sma

    previous = sma

    for i in range(
        period,
        len(values)
    ):

        current = (
            values[i]
            * multiplier
            +
            previous
            * (1.0 - multiplier)
        )

        result[i] = current

        previous = current

    return result


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    values,
    period=14
):

    if len(values) <= period:

        return [None] * len(values)

    result = [None] * len(values)

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
            max(change, 0.0)
        )

        losses.append(
            max(-change, 0.0)
        )

    average_gain = (
        sum(gains)
        / period
    )

    average_loss = (
        sum(losses)
        / period
    )

    if average_loss == 0:

        result[period] = 100.0

    else:

        rs = (
            average_gain
            / average_loss
        )

        result[period] = (
            100.0
            -
            100.0
            / (1.0 + rs)
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
            0.0
        )

        loss = max(
            -change,
            0.0
        )

        average_gain = (
            (
                average_gain
                * (period - 1)
            )
            + gain
        ) / period

        average_loss = (
            (
                average_loss
                * (period - 1)
            )
            + loss
        ) / period

        if average_loss == 0:

            result[i] = 100.0

        else:

            rs = (
                average_gain
                / average_loss
            )

            result[i] = (
                100.0
                -
                100.0
                / (1.0 + rs)
            )

    return result


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

        high = current["high"]

        low = current["low"]

        previous_close = (
            previous["close"]
        )

        tr1 = (
            high - low
        )

        tr2 = abs(
            high
            - previous_close
        )

        tr3 = abs(
            low
            - previous_close
        )

        true_ranges.append(
            max(
                tr1,
                tr2,
                tr3
            )
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
# SUPPORT / RESISTANCE
# ============================================================

def calculate_support_resistance(
    candles,
    lookback=50
):

    if len(candles) < lookback:

        lookback = len(candles)

    window = candles[
        -lookback:
    ]

    support = min(
        candle["low"]
        for candle in window
    )

    resistance = max(
        candle["high"]
        for candle in window
    )

    return (
        support,
        resistance
    )


# ============================================================
# CANDLE UTILITIES
# ============================================================

def candle_body(candle):

    return abs(
        candle["close"]
        - candle["open"]
    )


def candle_range(candle):

    return (
        candle["high"]
        - candle["low"]
    )


def upper_wick(candle):

    return (
        candle["high"]
        -
        max(
            candle["open"],
            candle["close"]
        )
    )


def lower_wick(candle):

    return (
        min(
            candle["open"],
            candle["close"]
        )
        -
        candle["low"]
    )


def bullish(candle):

    return (
        candle["close"]
        > candle["open"]
    )


def bearish(candle):

    return (
        candle["close"]
        < candle["open"]
    )


# ============================================================
# PATTERN 1 - BULLISH ENGULFING
# ============================================================

def detect_bullish_engulfing(
    candles
):

    if len(candles) < 2:

        return False

    a = candles[-2]

    b = candles[-1]

    return (
        bearish(a)
        and
        bullish(b)
        and
        b["open"] <= a["close"]
        and
        b["close"] >= a["open"]
        and
        candle_body(b)
        > candle_body(a)
    )


# ============================================================
# PATTERN 2 - BEARISH ENGULFING
# ============================================================

def detect_bearish_engulfing(
    candles
):

    if len(candles) < 2:

        return False

    a = candles[-2]

    b = candles[-1]

    return (
        bullish(a)
        and
        bearish(b)
        and
        b["open"] >= a["close"]
        and
        b["close"] <= a["open"]
        and
        candle_body(b)
        > candle_body(a)
    )


# ============================================================
# PATTERN 3 - HAMMER
# ============================================================

def detect_hammer(
    candles
):

    if not candles:

        return False

    c = candles[-1]

    body = candle_body(c)

    rng = candle_range(c)

    if rng <= 0:

        return False

    lower = lower_wick(c)

    upper = upper_wick(c)

    return (
        lower >= body * 2.0
        and
        upper <= body * 0.8
        and
        body / rng <= 0.45
    )


# ============================================================
# PATTERN 4 - SHOOTING STAR
# ============================================================

def detect_shooting_star(
    candles
):

    if not candles:

        return False

    c = candles[-1]

    body = candle_body(c)

    rng = candle_range(c)

    if rng <= 0:

        return False

    lower = lower_wick(c)

    upper = upper_wick(c)

    return (
        upper >= body * 2.0
        and
        lower <= body * 0.8
        and
        body / rng <= 0.45
    )


# ============================================================
# PATTERN 5 - MORNING STAR
# ============================================================

def detect_morning_star(
    candles
):

    if len(candles) < 3:

        return False

    a = candles[-3]

    b = candles[-2]

    c = candles[-1]

    range_b = candle_range(b)

    if range_b <= 0:

        return False

    midpoint_a = (
        a["open"]
        + a["close"]
    ) / 2.0

    return (
        bearish(a)
        and
        candle_body(b)
        < candle_body(a) * 0.50
        and
        bullish(c)
        and
        c["close"]
        > midpoint_a
    )


# ============================================================
# PATTERN 6 - EVENING STAR
# ============================================================

def detect_evening_star(
    candles
):

    if len(candles) < 3:

        return False

    a = candles[-3]

    b = candles[-2]

    c = candles[-1]

    midpoint_a = (
        a["open"]
        + a["close"]
    ) / 2.0

    return (
        bullish(a)
        and
        candle_body(b)
        < candle_body(a) * 0.50
        and
        bearish(c)
        and
        c["close"]
        < midpoint_a
    )


# ============================================================
# PATTERN 7 - BREAKOUT
# ============================================================

def detect_breakout(
    candles
):

    if len(candles) < 25:

        return None

    previous = candles[
        -21:-1
    ]

    current = candles[-1]

    resistance = max(
        c["high"]
        for c in previous
    )

    support = min(
        c["low"]
        for c in previous
    )

    if current["close"] > resistance:

        return "BUY"

    if current["close"] < support:

        return "SELL"

    return None


# ============================================================
# PATTERN 8 - PULLBACK
# ============================================================

def detect_pullback(
    candles,
    ema_fast,
    ema_slow
):

    if len(candles) < 5:

        return None

    if (
        ema_fast is None
        or
        ema_slow is None
    ):

        return None

    current = candles[-1]

    previous = candles[-2]

    if (
        ema_fast > ema_slow
        and
        current["close"]
        > ema_fast
        and
        previous["low"]
        <= ema_fast
        and
        bullish(current)
    ):

        return "BUY"

    if (
        ema_fast < ema_slow
        and
        current["close"]
        < ema_fast
        and
        previous["high"]
        >= ema_fast
        and
        bearish(current)
    ):

        return "SELL"

    return None


# ============================================================
# PATTERN 9 - DOUBLE BOTTOM
# ============================================================

def detect_double_bottom(
    candles,
    atr
):

    if len(candles) < 30:

        return False

    recent = candles[
        -30:
    ]

    lows = [
        c["low"]
        for c in recent
    ]

    first_low = min(
        lows[:15]
    )

    second_low = min(
        lows[15:]
    )

    tolerance = max(
        atr * 0.50,
        first_low * 0.001
    )

    return (
        abs(
            first_low
            - second_low
        )
        <= tolerance
        and
        candles[-1]["close"]
        > second_low
    )


# ============================================================
# PATTERN 10 - DOUBLE TOP
# ============================================================

def detect_double_top(
    candles,
    atr
):

    if len(candles) < 30:

        return False

    recent = candles[
        -30:
    ]

    highs = [
        c["high"]
        for c in recent
    ]

    first_high = max(
        highs[:15]
    )

    second_high = max(
        highs[15:]
    )

    tolerance = max(
        atr * 0.50,
        first_high * 0.001
    )

    return (
        abs(
            first_high
            - second_high
        )
        <= tolerance
        and
        candles[-1]["close"]
        < second_high
    )


# ============================================================
# PATTERN RECOGNITION
# ============================================================

def recognize_patterns(
    candles,
    ema_fast,
    ema_slow,
    atr
):

    patterns = []

    directions = []

    if detect_bullish_engulfing(
        candles
    ):

        patterns.append(
            "Bullish Engulfing"
        )

        directions.append(
            "BUY"
        )

    if detect_bearish_engulfing(
        candles
    ):

        patterns.append(
            "Bearish Engulfing"
        )

        directions.append(
            "SELL"
        )

    if detect_hammer(
        candles
    ):

        patterns.append(
            "Hammer"
        )

        directions.append(
            "BUY"
        )

    if detect_shooting_star(
        candles
    ):

        patterns.append(
            "Shooting Star"
        )

        directions.append(
            "SELL"
        )

    if detect_morning_star(
        candles
    ):

        patterns.append(
            "Morning Star"
        )

        directions.append(
            "BUY"
        )

    if detect_evening_star(
        candles
    ):

        patterns.append(
            "Evening Star"
        )

        directions.append(
            "SELL"
        )

    breakout = detect_breakout(
        candles
    )

    if breakout == "BUY":

        patterns.append(
            "Bullish Breakout"
        )

        directions.append(
            "BUY"
        )

    elif breakout == "SELL":

        patterns.append(
            "Bearish Breakout"
        )

        directions.append(
            "SELL"
        )

    pullback = detect_pullback(
        candles,
        ema_fast,
        ema_slow
    )

    if pullback == "BUY":

        patterns.append(
            "Bullish Pullback"
        )

        directions.append(
            "BUY"
        )

    elif pullback == "SELL":

        patterns.append(
            "Bearish Pullback"
        )

        directions.append(
            "SELL"
        )

    if detect_double_bottom(
        candles,
        atr
    ):

        patterns.append(
            "Double Bottom"
        )

        directions.append(
            "BUY"
        )

    if detect_double_top(
        candles,
        atr
    ):

        patterns.append(
            "Double Top"
        )

        directions.append(
            "SELL"
        )

    buy_count = directions.count(
        "BUY"
    )

    sell_count = directions.count(
        "SELL"
    )

    if buy_count > sell_count:

        candidate = "BUY"

    elif sell_count > buy_count:

        candidate = "SELL"

    else:

        candidate = "NO_TRADE"

    return {
        "patterns": patterns,
        "directions": directions,
        "buy_patterns": buy_count,
        "sell_patterns": sell_count,
        "candidate_direction": candidate,
    }


# ============================================================
# TREND
# ============================================================

def determine_trend(
    close,
    ema_fast,
    ema_slow
):

    if (
        ema_fast is None
        or
        ema_slow is None
    ):

        return "UNKNOWN"

    if (
        close > ema_fast
        and
        ema_fast > ema_slow
    ):

        return "UPTREND"

    if (
        close < ema_fast
        and
        ema_fast < ema_slow
    ):

        return "DOWNTREND"

    return "SIDEWAYS"


# ============================================================
# MOMENTUM
# ============================================================

def determine_momentum(
    rsi
):

    if rsi is None:

        return "UNKNOWN"

    if rsi >= 60:

        return "BULLISH"

    if rsi <= 40:

        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# SCORE ENGINE
# ============================================================

def calculate_direction_score(
    direction,
    patterns,
    trend,
    momentum,
    rsi,
    close,
    support,
    resistance,
    atr
):

    score = 0.0

    reasons = []

    pattern_count = len(
        patterns
    )

    if pattern_count > 0:

        pattern_score = min(
            30.0,
            pattern_count * 12.0
        )

        score += pattern_score

        reasons.append(
            f"{pattern_count} pattern(s) detected"
        )

    if direction == "BUY":

        if trend == "UPTREND":

            score += 20

            reasons.append(
                "Uptrend"
            )

        elif trend == "SIDEWAYS":

            score += 8

            reasons.append(
                "Sideways market"
            )

        elif trend == "DOWNTREND":

            score -= 15

            reasons.append(
                "Against downtrend"
            )

        if momentum == "BULLISH":

            score += 20

            reasons.append(
                "Bullish momentum"
            )

        elif momentum == "NEUTRAL":

            score += 8

        elif momentum == "BEARISH":

            score -= 10

        if (
            rsi is not None
            and
            rsi < 70
        ):

            score += 5

        if atr > 0:

            distance_to_support = (
                close - support
            )

            if (
                distance_to_support
                <= atr * 1.5
            ):

                score += 10

                reasons.append(
                    "Near support"
                )

            if (
                resistance > close
                and
                (
                    resistance - close
                )
                <= atr * 1.0
            ):

                score -= 5

                reasons.append(
                    "Near resistance"
                )

    elif direction == "SELL":

        if trend == "DOWNTREND":

            score += 20

            reasons.append(
                "Downtrend"
            )

        elif trend == "SIDEWAYS":

            score += 8

        elif trend == "UPTREND":

            score -= 15

            reasons.append(
                "Against uptrend"
            )

        if momentum == "BEARISH":

            score += 20

            reasons.append(
                "Bearish momentum"
            )

        elif momentum == "NEUTRAL":

            score += 8

        elif momentum == "BULLISH":

            score -= 10

        if (
            rsi is not None
            and
            rsi > 30
        ):

            score += 5

        if atr > 0:

            distance_to_resistance = (
                resistance - close
            )

            if (
                distance_to_resistance
                <= atr * 1.5
            ):

                score += 10

                reasons.append(
                    "Near resistance"
                )

            if (
                close > support
                and
                (
                    close - support
                )
                <= atr * 1.0
            ):

                score -= 5

                reasons.append(
                    "Near support"
                )

    return (
        round(
            clamp(score),
            2
        ),
        reasons
    )


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    direction,
    entry,
    atr,
    support,
    resistance
):

    if atr <= 0:

        return (
            None,
            None,
            0.0
        )

    if direction == "BUY":

        atr_sl = (
            entry
            -
            atr * SL_ATR_MULTIPLIER
        )

        structural_sl = (
            support
            -
            atr * 0.15
        )

        stop_loss = min(
            atr_sl,
            structural_sl
        )

        risk = (
            entry
            - stop_loss
        )

        take_profit = (
            entry
            + risk
            * 1.50
        )

        if (
            resistance > entry
            and
            resistance
            < take_profit
        ):

            take_profit = resistance

    elif direction == "SELL":

        atr_sl = (
            entry
            +
            atr * SL_ATR_MULTIPLIER
        )

        structural_sl = (
            resistance
            +
            atr * 0.15
        )

        stop_loss = max(
            atr_sl,
            structural_sl
        )

        risk = (
            stop_loss
            - entry
        )

        take_profit = (
            entry
            - risk
            * 1.50
        )

        if (
            support < entry
            and
            support > take_profit
        ):

            take_profit = support

    else:

        return (
            None,
            None,
            0.0
        )

    if risk <= 0:

        return (
            None,
            None,
            0.0
        )

    reward = abs(
        take_profit
        - entry
    )

    risk_reward = (
        reward
        / risk
    )

    return (
        round_price(stop_loss),
        round_price(take_profit),
        round(
            risk_reward,
            2
        )
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(
    candles
):

    if len(candles) < 100:

        raise RuntimeError(
            "Not enough candles for analysis"
        )

    closes = [
        c["close"]
        for c in candles
    ]

    ema20_values = calculate_ema(
        closes,
        EMA_FAST_PERIOD
    )

    ema50_values = calculate_ema(
        closes,
        EMA_SLOW_PERIOD
    )

    rsi_values = calculate_rsi(
        closes,
        RSI_PERIOD
    )

    ema20 = ema20_values[-1]

    ema50 = ema50_values[-1]

    rsi = rsi_values[-1]

    atr = calculate_atr(
        candles,
        ATR_PERIOD
    )

    latest = candles[-1]

    entry = latest[
        "close"
    ]

    support, resistance = (
        calculate_support_resistance(
            candles,
            SR_LOOKBACK
        )
    )

    trend = determine_trend(
        entry,
        ema20,
        ema50
    )

    momentum = determine_momentum(
        rsi
    )

    recognition = recognize_patterns(
        candles,
        ema20,
        ema50,
        atr
    )

    candidate = recognition[
        "candidate_direction"
    ]

    patterns = recognition[
        "patterns"
    ]

    if candidate == "BUY":

        directional_patterns = [
            p
            for p in patterns
            if (
                "Bullish" in p
                or
                p in [
                    "Hammer",
                    "Morning Star",
                    "Double Bottom"
                ]
            )
        ]

    elif candidate == "SELL":

        directional_patterns = [
            p
            for p in patterns
            if (
                "Bearish" in p
                or
                p in [
                    "Shooting Star",
                    "Evening Star",
                    "Double Top"
                ]
            )
        ]

    else:

        directional_patterns = []

    score, reasons = (
        calculate_direction_score(
            candidate,
            directional_patterns,
            trend,
            momentum,
            rsi,
            entry,
            support,
            resistance,
            atr
        )
    )

    stop_loss = None

    take_profit = None

    risk_reward = 0.0

    if candidate in [
        "BUY",
        "SELL"
    ]:

        (
            stop_loss,
            take_profit,
            risk_reward
        ) = calculate_trade_levels(
            candidate,
            entry,
            atr,
            support,
            resistance
        )

    valid = (
        candidate in [
            "BUY",
            "SELL"
        ]
        and
        len(directional_patterns) > 0
        and
        score >= MIN_SCORE
        and
        atr >= MIN_ATR
        and
        risk_reward >= MIN_RISK_REWARD
    )

    if valid:

        final_signal = candidate

    else:

        final_signal = "NO_TRADE"

        stop_loss = None

        take_profit = None

    confidence = score

    return {

        "timestamp":
            latest["datetime"],

        "symbol":
            SYMBOL,

        "timeframe":
            DISPLAY_TIMEFRAME,

        "signal":
            final_signal,

        "candidate_direction":
            candidate,

        "confidence":
            round(
                confidence,
                2
            ),

        "score":
            round(
                score,
                2
            ),

        "entry":
            round_price(entry),

        "stop_loss":
            stop_loss,

        "take_profit":
            take_profit,

        "risk_reward":
            risk_reward,

        "atr":
            round(
                atr,
                4
            ),

        "rsi":
            (
                round(
                    rsi,
                    2
                )
                if rsi is not None
                else None
            ),

        "ema20":
            (
                round(
                    ema20,
                    2
                )
                if ema20 is not None
                else None
            ),

        "ema50":
            (
                round(
                    ema50,
                    2
                )
                if ema50 is not None
                else None
            ),

        "support":
            round_price(
                support
            ),

        "resistance":
            round_price(
                resistance
            ),

        "trend":
            trend,

        "momentum":
            momentum,

        "patterns":
            patterns,

        "directional_patterns":
            directional_patterns,

        "pattern_count":
            len(patterns),

        "reasons":
            reasons,

        "valid":
            valid,

        "method":
            "M5 Pattern Recognition + Trend + Momentum + Support/Resistance",

        "data_source":
            "Twelve Data XAU/USD",

        "rules": {

            "minimum_score":
                MIN_SCORE,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "minimum_atr":
                MIN_ATR
        }
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
            True
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

        STATE[
            "telegram_last_error"
        ] = None

        return (
            True,
            None
        )

    except Exception as exc:

        STATE[
            "telegram_last_error"
        ] = str(exc)

        return (
            False,
            str(exc)
        )


# ============================================================
# TELEGRAM STARTUP MESSAGE
# ============================================================

def send_startup_notification():

    with STARTUP_LOCK:

        if STATE[
            "startup_notification_sent"
        ]:

            return True

        if not TELEGRAM_BOT_TOKEN:

            print(
                "Telegram startup skipped: "
                "TELEGRAM_BOT_TOKEN not configured"
            )

            return False

        if not TELEGRAM_CHAT_ID:

            print(
                "Telegram startup skipped: "
                "TELEGRAM_CHAT_ID not configured"
            )

            return False

        message = (

            "🟢 <b>XAUUSD M5 BOT ONLINE</b>\n"
            "\n"

            "ระบบเริ่มทำงานเรียบร้อยแล้ว\n"
            "\n"

            f"<b>Symbol:</b> {SYMBOL}\n"
            "<b>Timeframe:</b> M5\n"
            "<b>Data:</b> Twelve Data\n"
            "\n"

            "<b>ระบบวิเคราะห์:</b>\n"
            "• Pattern Recognition\n"
            "• Trend / EMA20 / EMA50\n"
            "• RSI Momentum\n"
            "• Support / Resistance\n"
            "• Breakout / Pullback\n"
            "• Candlestick Patterns\n"
            "• Risk / Reward\n"
            "• Automatic TP / SL\n"
            "\n"

            "<b>Patterns:</b> 10 รูปแบบ\n"
            "\n"

            f"<b>Minimum Score:</b> "
            f"{MIN_SCORE:.0f}\n"

            f"<b>Minimum Risk/Reward:</b> "
            f"{MIN_RISK_REWARD:.2f}\n"
            "\n"

            "สถานะ: <b>READY</b> 🟢\n"
            "\n"

            "ระบบจะส่ง Telegram "
            "เมื่อพบจุดเข้าออเดอร์ที่ผ่านเงื่อนไข"
        )

        ok, error = send_telegram(
            message
        )

        if ok:

            STATE[
                "startup_notification_sent"
            ] = True

            print(
                "Telegram welcome message "
                "sent successfully"
            )

            return True

        print(
            "Telegram startup failed:",
            error
        )

        return False


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def format_signal_message(
    signal
):

    direction = signal[
        "signal"
    ]

    if direction not in [
        "BUY",
        "SELL"
    ]:

        return None

    if direction == "BUY":

        emoji = "🟢"

    else:

        emoji = "🔴"

    patterns = signal[
        "directional_patterns"
    ]

    pattern_text = (
        ", ".join(patterns)
        if patterns
        else "None"
    )

    reasons = signal[
        "reasons"
    ]

    reason_text = (
        "\n".join(
            "• " + str(x)
            for x in reasons
        )
        if reasons
        else "• Pattern confirmed"
    )

    return (

        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"

        f"<b>SIGNAL:</b> {direction}\n"

        f"<b>Confidence:</b> "
        f"{signal['confidence']:.2f}%\n"

        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"

        f"<b>Pattern:</b> "
        f"{pattern_text}\n"
        "\n"

        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"

        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"

        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"

        f"<b>R/R:</b> "
        f"{signal['risk_reward']:.2f}\n"
        "\n"

        f"<b>Trend:</b> "
        f"{signal['trend']}\n"

        f"<b>Momentum:</b> "
        f"{signal['momentum']}\n"

        f"<b>RSI:</b> "
        f"{signal['rsi']}\n"

        f"<b>EMA20:</b> "
        f"{signal['ema20']:.2f}\n"

        f"<b>EMA50:</b> "
        f"{signal['ema50']:.2f}\n"

        f"<b>ATR:</b> "
        f"{signal['atr']:.4f}\n"
        "\n"

        "<b>เหตุผล:</b>\n"
        f"{reason_text}\n"
        "\n"

        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"
        "\n"

        "<i>Pattern Recognition Trading System</i>"
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

    STATE[
        "status"
    ] = "online"

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
            "XAUUSD M5 Pattern Recognition Bot",

        "status":
            "online",

        "system":
            "Pattern Recognition",

        "data_source":
            "Twelve Data",

        "symbol":
            SYMBOL,

        "timeframe":
            DISPLAY_TIMEFRAME,

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and
                TELEGRAM_CHAT_ID
            ),

        "patterns": [

            "Bullish Engulfing",
            "Bearish Engulfing",
            "Hammer",
            "Shooting Star",
            "Morning Star",
            "Evening Star",
            "Bullish Breakout",
            "Bearish Breakout",
            "Pullback",
            "Double Bottom",
            "Double Top"

        ],

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
            STATE["status"],

        "service":
            "XAUUSD M5 Pattern Recognition Bot",

        "data_source":
            "Twelve Data",

        "symbol":
            SYMBOL,

        "timeframe":
            DISPLAY_TIMEFRAME,

        "twelve_data":
            bool(
                TWELVE_DATA_API_KEY
            ),

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and
                TELEGRAM_CHAT_ID
            ),

        "startup_notification":
            STATE[
                "startup_notification_sent"
            ],

        "last_update":
            STATE[
                "last_update"
            ],

        "last_signal":
            STATE[
                "last_signal"
            ],

        "last_error":
            STATE[
                "last_error"
            ],

        "telegram_error":
            STATE[
                "telegram_last_error"
            ]
    })


# ============================================================
# TEST TWELVE DATA
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
                DISPLAY_TIMEFRAME,

            "candles":
                len(candles),

            "latest":
                latest

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

        "Telegram connection ทำงานปกติ\n"
        "\n"

        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"
        "<b>Status:</b> ONLINE\n"
        "\n"

        "Pattern Recognition System พร้อมทำงาน"
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

        # พยายามส่ง welcome message
        # ถ้ายังไม่ได้ส่ง
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

        test_count = min(
            150,
            total_candles - 120
        )

        if test_count <= 0:

            return jsonify({

                "status":
                    "error",

                "error":
                    "Not enough candles"

            }), 400

        start_index = (
            total_candles
            - test_count
        )

        wins = 0

        losses = 0

        timeouts = 0

        buy_signals = 0

        sell_signals = 0

        total_profit = 0.0

        total_loss = 0.0

        trades = []

        forward_bars = 12

        for i in range(
            start_index,
            total_candles - 1
        ):

            historical = candles[
                :i
            ]

            if len(historical) < 100:

                continue

            try:

                signal = generate_signal(
                    historical
                )

            except Exception:

                continue

            direction = signal[
                "signal"
            ]

            if direction not in [
                "BUY",
                "SELL"
            ]:

                continue

            entry = signal[
                "entry"
            ]

            stop_loss = signal[
                "stop_loss"
            ]

            take_profit = signal[
                "take_profit"
            ]

            if (
                stop_loss is None
                or
                take_profit is None
            ):

                continue

            if direction == "BUY":

                buy_signals += 1

            else:

                sell_signals += 1

            max_index = min(
                i + forward_bars,
                total_candles - 1
            )

            result = "TIMEOUT"

            exit_price = None

            exit_index = max_index

            for j in range(
                i,
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

                    hit_sl = (
                        low
                        <= stop_loss
                    )

                    hit_tp = (
                        high
                        >= take_profit
                    )

                else:

                    hit_sl = (
                        high
                        >= stop_loss
                    )

                    hit_tp = (
                        low
                        <= take_profit
                    )

                # Conservative rule:
                # ถ้า TP และ SL เกิดในแท่งเดียวกัน
                # ถือว่า SL ก่อน
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

                exit_price = candles[
                    exit_index
                ]["close"]

            if direction == "BUY":

                pnl = (
                    exit_price
                    - entry
                ) / entry * 100.0

            else:

                pnl = (
                    entry
                    - exit_price
                ) / entry * 100.0

            if result == "WIN":

                wins += 1

                total_profit += max(
                    pnl,
                    0
                )

            elif result == "LOSS":

                losses += 1

                total_loss += abs(
                    min(
                        pnl,
                        0
                    )
                )

            else:

                timeouts += 1

            trades.append({

                "timestamp":
                    candles[i][
                        "datetime"
                    ],

                "signal":
                    direction,

                "pattern":
                    signal[
                        "directional_patterns"
                    ],

                "score":
                    signal[
                        "score"
                    ],

                "entry":
                    round_price(
                        entry
                    ),

                "stop_loss":
                    round_price(
                        stop_loss
                    ),

                "take_profit":
                    round_price(
                        take_profit
                    ),

                "result":
                    result,

                "exit_price":
                    round_price(
                        exit_price
                    ),

                "pnl_percent":
                    round(
                        pnl,
                        4
                    ),

                "bars_held":
                    exit_index
                    - i
                    + 1
            })

        total_trades = (
            wins
            + losses
            + timeouts
        )

        if total_trades > 0:

            win_rate = (
                wins
                / total_trades
                * 100.0
            )

            loss_rate = (
                losses
                / total_trades
                * 100.0
            )

            timeout_rate = (
                timeouts
                / total_trades
                * 100.0
            )

        else:

            win_rate = 0.0

            loss_rate = 0.0

            timeout_rate = 0.0

        net_profit = (
            total_profit
            - total_loss
        )

        expectancy = (
            net_profit
            / total_trades
            if total_trades > 0
            else 0.0
        )

        if total_loss > 0:

            profit_factor = (
                total_profit
                / total_loss
            )

        elif total_profit > 0:

            profit_factor = float(
                "inf"
            )

        else:

            profit_factor = 0.0

        # ====================================================
        # MAX DRAWDOWN
        # ====================================================

        equity = 0.0

        peak = 0.0

        max_drawdown = 0.0

        for trade in trades:

            equity += trade[
                "pnl_percent"
            ]

            peak = max(
                peak,
                equity
            )

            drawdown = (
                peak
                - equity
            )

            max_drawdown = max(
                max_drawdown,
                drawdown
            )

        return jsonify({

            "status":
                "completed",

            "symbol":
                SYMBOL,

            "timeframe":
                DISPLAY_TIMEFRAME,

            "method":
                "Pattern Recognition",

            "data_source":
                "Twelve Data XAU/USD",

            "candles_available":
                total_candles,

            "test_points":
                test_count,

            "rules": {

                "minimum_score":
                    MIN_SCORE,

                "minimum_risk_reward":
                    MIN_RISK_REWARD,

                "forward_bars":
                    forward_bars
            },

            "signals": {

                "total":
                    total_trades,

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
                        total_profit,
                        4
                    ),

                "total_loss_percent":
                    round(
                        total_loss,
                        4
                    ),

                "net_profit_percent":
                    round(
                        net_profit,
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

            "recent_trades":
                trades[-20:],

            "warning":
                "Historical simulation only. "
                "Spread, slippage, commission and "
                "execution differences are not included."
        })

    except Exception as exc:

        return jsonify({

            "status":
                "error",

            "error":
                str(exc)

        }), 500


# ============================================================
# STARTUP
# ============================================================

def initialize_application():

    print(
        "=" * 60
    )

    print(
        "XAUUSD M5 PATTERN RECOGNITION BOT"
    )

    print(
        "=" * 60
    )

    print(
        "Symbol:",
        SYMBOL
    )

    print(
        "Timeframe:",
        DISPLAY_TIMEFRAME
    )

    print(
        "Data:",
        "Twelve Data"
    )

    print(
        "Pattern Recognition:",
        "ENABLED"
    )

    print(
        "Telegram:",
        bool(
            TELEGRAM_BOT_TOKEN
            and
            TELEGRAM_CHAT_ID
        )
    )

    print(
        "=" * 60
    )

    STATE[
        "status"
    ] = "online"

    # สำคัญ:
    # ส่งข้อความต้อนรับทันทีตอน app โหลด
    send_startup_notification()


# ============================================================
# INITIALIZE
# ============================================================

initialize_application()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

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

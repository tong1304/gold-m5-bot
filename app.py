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
# CONFIG
# ============================================================

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"
DISPLAY_TIMEFRAME = "M5"

CANDLE_LIMIT = 1000

# Historical pattern
PATTERN_LENGTH = 12
MAX_MATCHES = 40
MIN_SIMILARITY = 0.60

# Signal requirements
MIN_PROBABILITY = 70.0
MIN_SCORE = 70.0
MIN_PATTERNS = 3

# Risk
RISK_REWARD = 1.50

# Analysis
SWING_LOOKBACK = 80
EMA_FAST_PERIOD = 20
EMA_SLOW_PERIOD = 50
ATR_PERIOD = 14

# Backtest
BACKTEST_POINTS = 150
FORWARD_BARS = 12


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
    "last_welcome": None,
}

WELCOME_SENT = False


# ============================================================
# TIME
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# NUMBER HELPERS
# ============================================================

def safe_float(value, default=0.0):

    try:
        return float(value)

    except Exception:
        return default


def round_price(value):

    return round(
        safe_float(value),
        2
    )


def clamp(value, minimum, maximum):

    return max(
        minimum,
        min(
            maximum,
            value
        )
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

    candles.reverse()

    minimum_required = max(
        100,
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

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

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

def calculate_ema_values(
    candles,
    period
):

    if not candles:
        return []

    closes = [
        c["close"]
        for c in candles
    ]

    if len(closes) < period:
        return []

    multiplier = (
        2.0
        / (period + 1.0)
    )

    ema = []

    initial = (
        sum(closes[:period])
        / period
    )

    ema.append(initial)

    previous = initial

    for price in closes[period:]:

        current = (
            (price - previous)
            * multiplier
            + previous
        )

        ema.append(current)

        previous = current

    return ema


def calculate_ema(
    candles,
    period
):

    values = calculate_ema_values(
        candles,
        period
    )

    if not values:
        return 0.0

    return values[-1]


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    candles,
    period=14
):

    if len(candles) <= period:
        return 50.0

    closes = [
        c["close"]
        for c in candles
    ]

    gains = []
    losses = []

    for i in range(
        1,
        len(closes)
    ):

        change = (
            closes[i]
            - closes[i - 1]
        )

        if change > 0:

            gains.append(change)
            losses.append(0.0)

        else:

            gains.append(0.0)
            losses.append(abs(change))

    recent_gains = gains[-period:]
    recent_losses = losses[-period:]

    avg_gain = (
        sum(recent_gains)
        / period
    )

    avg_loss = (
        sum(recent_losses)
        / period
    )

    if avg_loss == 0:

        return 100.0

    rs = (
        avg_gain
        / avg_loss
    )

    return (
        100.0
        - (
            100.0
            / (1.0 + rs)
        )
    )


# ============================================================
# CANDLE PROPERTIES
# ============================================================

def candle_body(candle):

    return abs(
        candle["close"]
        - candle["open"]
    )


def candle_range(candle):

    return max(
        candle["high"]
        - candle["low"],
        0.000001
    )


def upper_wick(candle):

    return (
        candle["high"]
        - max(
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
        - candle["low"]
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
# SWING HIGH / LOW
# ============================================================

def find_swing_highs(
    candles,
    window=2
):

    result = []

    for i in range(
        window,
        len(candles) - window
    ):

        high = candles[i]["high"]

        is_high = True

        for j in range(
            1,
            window + 1
        ):

            if high <= candles[
                i - j
            ]["high"]:

                is_high = False
                break

            if high <= candles[
                i + j
            ]["high"]:

                is_high = False
                break

        if is_high:

            result.append({
                "index": i,
                "price": high
            })

    return result


def find_swing_lows(
    candles,
    window=2
):

    result = []

    for i in range(
        window,
        len(candles) - window
    ):

        low = candles[i]["low"]

        is_low = True

        for j in range(
            1,
            window + 1
        ):

            if low >= candles[
                i - j
            ]["low"]:

                is_low = False
                break

            if low >= candles[
                i + j
            ]["low"]:

                is_low = False
                break

        if is_low:

            result.append({
                "index": i,
                "price": low
            })

    return result


# ============================================================
# TREND
# ============================================================

def detect_trend(
    candles
):

    ema_fast = calculate_ema(
        candles,
        EMA_FAST_PERIOD
    )

    ema_slow = calculate_ema(
        candles,
        EMA_SLOW_PERIOD
    )

    price = candles[-1]["close"]

    if (
        ema_fast <= 0
        or ema_slow <= 0
    ):

        return {
            "direction": "NEUTRAL",
            "strength": 0.0,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow
        }

    distance = (
        abs(
            ema_fast
            - ema_slow
        )
        / price
        * 100.0
    )

    strength = clamp(
        55.0
        + distance * 15.0,
        55.0,
        95.0
    )

    if (
        price > ema_fast
        and ema_fast > ema_slow
    ):

        direction = "BUY"

    elif (
        price < ema_fast
        and ema_fast < ema_slow
    ):

        direction = "SELL"

    else:

        direction = "NEUTRAL"

    return {
        "direction": direction,
        "strength": round(
            strength,
            2
        ),
        "ema_fast": round_price(
            ema_fast
        ),
        "ema_slow": round_price(
            ema_slow
        )
    }


# ============================================================
# PATTERN RESULT
# ============================================================

def pattern_result(
    name,
    direction,
    confidence,
    reason,
    entry_low=None,
    entry_high=None
):

    return {

        "name": name,

        "direction": direction,

        "confidence": round(
            clamp(
                confidence,
                0.0,
                100.0
            ),
            2
        ),

        "reason": reason,

        "entry_low":
            round_price(entry_low)
            if entry_low is not None
            else None,

        "entry_high":
            round_price(entry_high)
            if entry_high is not None
            else None
    }


# ============================================================
# 1. TREND CONTINUATION
# ============================================================

def detect_trend_continuation(
    candles
):

    trend = detect_trend(candles)

    direction = trend["direction"]

    if direction == "NEUTRAL":

        return pattern_result(
            "Trend Continuation",
            "NEUTRAL",
            0,
            "No clear trend"
        )

    price = candles[-1]["close"]

    ema_fast = trend["ema_fast"]

    confidence = trend["strength"]

    if direction == "BUY":

        if price > ema_fast:

            confidence += 5

        reason = (
            "Price above EMA20 and "
            "EMA20 above EMA50"
        )

    else:

        if price < ema_fast:

            confidence += 5

        reason = (
            "Price below EMA20 and "
            "EMA20 below EMA50"
        )

    return pattern_result(
        "Trend Continuation",
        direction,
        clamp(
            confidence,
            0,
            100
        ),
        reason,
        price - calculate_atr(candles) * 0.25,
        price + calculate_atr(candles) * 0.25
    )


# ============================================================
# 2. PULLBACK
# ============================================================

def detect_pullback(
    candles
):

    if len(candles) < 30:

        return pattern_result(
            "Pullback",
            "NEUTRAL",
            0,
            "Insufficient data"
        )

    trend = detect_trend(candles)

    if trend["direction"] == "NEUTRAL":

        return pattern_result(
            "Pullback",
            "NEUTRAL",
            0,
            "No trend"
        )

    price = candles[-1]["close"]
    atr = calculate_atr(candles)

    if atr <= 0:

        return pattern_result(
            "Pullback",
            "NEUTRAL",
            0,
            "ATR unavailable"
        )

    distance = abs(
        price
        - trend["ema_fast"]
    )

    near_ema = (
        distance
        <= atr * 0.8
    )

    recent = candles[-5:]

    if trend["direction"] == "BUY":

        bullish_recovery = (
            recent[-1]["close"]
            > recent[-1]["open"]
        )

        if near_ema and bullish_recovery:

            confidence = 76.0

            return pattern_result(
                "Pullback",
                "BUY",
                confidence,
                "Uptrend pullback near EMA20 with bullish recovery",
                price - atr * 0.20,
                price + atr * 0.20
            )

    else:

        bearish_recovery = (
            recent[-1]["close"]
            < recent[-1]["open"]
        )

        if near_ema and bearish_recovery:

            confidence = 76.0

            return pattern_result(
                "Pullback",
                "SELL",
                confidence,
                "Downtrend pullback near EMA20 with bearish recovery",
                price - atr * 0.20,
                price + atr * 0.20
            )

    return pattern_result(
        "Pullback",
        "NEUTRAL",
        0,
        "No valid pullback"
    )


# ============================================================
# 3. BREAKOUT
# ============================================================

def detect_breakout(
    candles
):

    if len(candles) < 25:

        return pattern_result(
            "Breakout",
            "NEUTRAL",
            0,
            "Insufficient data"
        )

    lookback = candles[-21:-1]

    resistance = max(
        c["high"]
        for c in lookback
    )

    support = min(
        c["low"]
        for c in lookback
    )

    latest = candles[-1]

    atr = calculate_atr(candles)

    if atr <= 0:

        return pattern_result(
            "Breakout",
            "NEUTRAL",
            0,
            "ATR unavailable"
        )

    if latest["close"] > resistance:

        strength = (
            latest["close"]
            - resistance
        ) / atr

        confidence = clamp(
            70.0
            + strength * 20.0,
            70.0,
            95.0
        )

        return pattern_result(
            "Breakout",
            "BUY",
            confidence,
            "Price closed above recent resistance",
            resistance - atr * 0.10,
            resistance + atr * 0.30
        )

    if latest["close"] < support:

        strength = (
            support
            - latest["close"]
        ) / atr

        confidence = clamp(
            70.0
            + strength * 20.0,
            70.0,
            95.0
        )

        return pattern_result(
            "Breakout",
            "SELL",
            confidence,
            "Price closed below recent support",
            support - atr * 0.30,
            support + atr * 0.10
        )

    return pattern_result(
        "Breakout",
        "NEUTRAL",
        0,
        "No breakout"
    )


# ============================================================
# 4. BREAKOUT RETEST
# ============================================================

def detect_breakout_retest(
    candles
):

    if len(candles) < 30:

        return pattern_result(
            "Breakout Retest",
            "NEUTRAL",
            0,
            "Insufficient data"
        )

    atr = calculate_atr(candles)

    if atr <= 0:

        return pattern_result(
            "Breakout Retest",
            "NEUTRAL",
            0,
            "ATR unavailable"
        )

    previous = candles[-4:-1]

    resistance = max(
        c["high"]
        for c in candles[-25:-4]
    )

    support = min(
        c["low"]
        for c in candles[-25:-4]
    )

    latest = candles[-1]

    broke_up = any(
        c["close"] > resistance
        for c in previous
    )

    broke_down = any(
        c["close"] < support
        for c in previous
    )

    if broke_up:

        retest = (
            latest["low"]
            <= resistance
            + atr * 0.25
            and latest["close"]
            > resistance
        )

        if retest:

            return pattern_result(
                "Breakout Retest",
                "BUY",
                82.0,
                "Resistance breakout followed by bullish retest",
                resistance - atr * 0.10,
                resistance + atr * 0.25
            )

    if broke_down:

        retest = (
            latest["high"]
            >= support
            - atr * 0.25
            and latest["close"]
            < support
        )

        if retest:

            return pattern_result(
                "Breakout Retest",
                "SELL",
                82.0,
                "Support breakout followed by bearish retest",
                support - atr * 0.25,
                support + atr * 0.10
            )

    return pattern_result(
        "Breakout Retest",
        "NEUTRAL",
        0,
        "No valid retest"
    )


# ============================================================
# 5. SUPPORT / RESISTANCE REVERSAL
# ============================================================

def detect_sr_reversal(
    candles
):

    if len(candles) < 30:

        return pattern_result(
            "Support/Resistance Reversal",
            "NEUTRAL",
            0,
            "Insufficient data"
        )

    atr = calculate_atr(candles)

    if atr <= 0:

        return pattern_result(
            "Support/Resistance Reversal",
            "NEUTRAL",
            0,
            "ATR unavailable"
        )

    recent = candles[-40:-1]

    support = min(
        c["low"]
        for c in recent
    )

    resistance = max(
        c["high"]
        for c in recent
    )

    latest = candles[-1]

    rsi = calculate_rsi(candles)

    near_support = (
        abs(
            latest["low"]
            - support
        )
        <= atr * 0.50
    )

    near_resistance = (
        abs(
            latest["high"]
            - resistance
        )
        <= atr * 0.50
    )

    if (
        near_support
        and bullish(latest)
        and rsi < 55
    ):

        return pattern_result(
            "Support/Resistance Reversal",
            "BUY",
            78.0,
            "Bullish rejection near support",
            latest["close"] - atr * 0.20,
            latest["close"] + atr * 0.20
        )

    if (
        near_resistance
        and bearish(latest)
        and rsi > 45
    ):

        return pattern_result(
            "Support/Resistance Reversal",
            "SELL",
            78.0,
            "Bearish rejection near resistance",
            latest["close"] - atr * 0.20,
            latest["close"] + atr * 0.20
        )

    return pattern_result(
        "Support/Resistance Reversal",
        "NEUTRAL",
        0,
        "No reversal"
    )


# ============================================================
# 6. DOUBLE TOP / BOTTOM
# ============================================================

def detect_double_top_bottom(
    candles
):

    highs = find_swing_highs(
        candles,
        2
    )

    lows = find_swing_lows(
        candles,
        2
    )

    tolerance = (
        calculate_atr(candles)
        * 0.70
    )

    if tolerance <= 0:

        return pattern_result(
            "Double Top/Bottom",
            "NEUTRAL",
            0,
            "ATR unavailable"
        )

    recent_highs = highs[-6:]
    recent_lows = lows[-6:]

    if len(recent_highs) >= 2:

        a = recent_highs[-2]
        b = recent_highs[-1]

        if (
            abs(
                a["price"]
                - b["price"]
            )
            <= tolerance
            and b["index"] > a["index"]
        ):

            current = candles[-1]["close"]

            if current < b["price"]:

                return pattern_result(
                    "Double Top/Bottom",
                    "SELL",
                    80.0,
                    "Two similar swing highs followed by rejection",
                    current - tolerance * 0.20,
                    current + tolerance * 0.20
                )

    if len(recent_lows) >= 2:

        a = recent_lows[-2]
        b = recent_lows[-1]

        if (
            abs(
                a["price"]
                - b["price"]
            )
            <= tolerance
            and b["index"] > a["index"]
        ):

            current = candles[-1]["close"]

            if current > b["price"]:

                return pattern_result(
                    "Double Top/Bottom",
                    "BUY",
                    80.0,
                    "Two similar swing lows followed by recovery",
                    current - tolerance * 0.20,
                    current + tolerance * 0.20
                )

    return pattern_result(
        "Double Top/Bottom",
        "NEUTRAL",
        0,
        "No double top/bottom"
    )


# ============================================================
# 7. HEAD AND SHOULDERS
# ============================================================

def detect_head_shoulders(
    candles
):

    highs = find_swing_highs(
        candles,
        2
    )

    lows = find_swing_lows(
        candles,
        2
    )

    if len(highs) >= 3:

        h1 = highs[-3]
        h2 = highs[-2]
        h3 = highs[-1]

        if (
            h2["price"] > h1["price"]
            and h2["price"] > h3["price"]
        ):

            shoulder_difference = abs(
                h1["price"]
                - h3["price"]
            )

            atr = calculate_atr(
                candles
            )

            if (
                atr > 0
                and shoulder_difference
                <= atr * 1.5
            ):

                return pattern_result(
                    "Head & Shoulders",
                    "SELL",
                    81.0,
                    "Left shoulder, higher head and similar right shoulder detected",
                    candles[-1]["close"]
                    - atr * 0.20,
                    candles[-1]["close"]
                    + atr * 0.20
                )

    if len(lows) >= 3:

        l1 = lows[-3]
        l2 = lows[-2]
        l3 = lows[-1]

        if (
            l2["price"] < l1["price"]
            and l2["price"] < l3["price"]
        ):

            shoulder_difference = abs(
                l1["price"]
                - l3["price"]
            )

            atr = calculate_atr(
                candles
            )

            if (
                atr > 0
                and shoulder_difference
                <= atr * 1.5
            ):

                return pattern_result(
                    "Head & Shoulders",
                    "BUY",
                    81.0,
                    "Inverse head and shoulders structure detected",
                    candles[-1]["close"]
                    - atr * 0.20,
                    candles[-1]["close"]
                    + atr * 0.20
                )

    return pattern_result(
        "Head & Shoulders",
        "NEUTRAL",
        0,
        "No head and shoulders structure"
    )


# ============================================================
# 8. CANDLESTICK REVERSAL
# ============================================================

def detect_candlestick(
    candles
):

    if len(candles) < 3:

        return pattern_result(
            "Candlestick Reversal",
            "NEUTRAL",
            0,
            "Insufficient data"
        )

    current = candles[-1]
    previous = candles[-2]

    body = candle_body(current)
    rng = candle_range(current)

    upper = upper_wick(current)
    lower = lower_wick(current)

    if body <= 0:

        body = rng * 0.05

    # Bullish engulfing
    bullish_engulfing = (
        bearish(previous)
        and bullish(current)
        and current["open"]
        <= previous["close"]
        and current["close"]
        >= previous["open"]
    )

    # Bearish engulfing
    bearish_engulfing = (
        bullish(previous)
        and bearish(current)
        and current["open"]
        >= previous["close"]
        and current["close"]
        <= previous["open"]
    )

    # Hammer
    hammer = (
        lower >= body * 2.0
        and upper <= body
        and body / rng <= 0.45
    )

    # Shooting star
    shooting_star = (
        upper >= body * 2.0
        and lower <= body
        and body / rng <= 0.45
    )

    price = current["close"]

    if (
        bullish_engulfing
        or hammer
    ):

        reason = (
            "Bullish engulfing"
            if bullish_engulfing
            else "Hammer rejection"
        )

        return pattern_result(
            "Candlestick Reversal",
            "BUY",
            79.0,
            reason,
            price - rng * 0.20,
            price + rng * 0.20
        )

    if (
        bearish_engulfing
        or shooting_star
    ):

        reason = (
            "Bearish engulfing"
            if bearish_engulfing
            else "Shooting star rejection"
        )

        return pattern_result(
            "Candlestick Reversal",
            "SELL",
            79.0,
            reason,
            price - rng * 0.20,
            price + rng * 0.20
        )

    return pattern_result(
        "Candlestick Reversal",
        "NEUTRAL",
        0,
        "No reversal candle"
    )


# ============================================================
# 9. RANGE / FALSE BREAKOUT
# ============================================================

def detect_range_false_breakout(
    candles
):

    if len(candles) < 25:

        return pattern_result(
            "Range/False Breakout",
            "NEUTRAL",
            0,
            "Insufficient data"
        )

    range_candles = candles[-21:-1]

    resistance = max(
        c["high"]
        for c in range_candles
    )

    support = min(
        c["low"]
        for c in range_candles
    )

    latest = candles[-1]

    atr = calculate_atr(candles)

    if atr <= 0:

        return pattern_result(
            "Range/False Breakout",
            "NEUTRAL",
            0,
            "ATR unavailable"
        )

    range_size = (
        resistance
        - support
    )

    # False breakout above
    if (
        latest["high"]
        > resistance
        and latest["close"]
        < resistance
    ):

        return pattern_result(
            "Range/False Breakout",
            "SELL",
            77.0,
            "Price broke resistance intrabar but closed back inside range",
            latest["close"] - atr * 0.20,
            latest["close"] + atr * 0.20
        )

    # False breakout below
    if (
        latest["low"]
        < support
        and latest["close"]
        > support
    ):

        return pattern_result(
            "Range/False Breakout",
            "BUY",
            77.0,
            "Price broke support intrabar but closed back inside range",
            latest["close"] - atr * 0.20,
            latest["close"] + atr * 0.20
        )

    # Range itself
    if range_size <= atr * 5:

        price = latest["close"]

        middle = (
            support
            + resistance
        ) / 2.0

        if price < middle:

            return pattern_result(
                "Range/False Breakout",
                "BUY",
                68.0,
                "Price trading in lower half of range",
                support,
                middle
            )

        if price > middle:

            return pattern_result(
                "Range/False Breakout",
                "SELL",
                68.0,
                "Price trading in upper half of range",
                middle,
                resistance
            )

    return pattern_result(
        "Range/False Breakout",
        "NEUTRAL",
        0,
        "No range setup"
    )


# ============================================================
# 10. HISTORICAL SIMILARITY
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

    return [
        (
            candle["close"]
            / first_close
            - 1.0
        )
        for candle in window
    ]


def pattern_similarity(
    pattern_a,
    pattern_b
):

    if (
        not pattern_a
        or not pattern_b
        or len(pattern_a)
        != len(pattern_b)
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

    return clamp(
        similarity,
        0.0,
        1.0
    )


def find_historical_matches(
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

        similarity = pattern_similarity(
            current_pattern,
            historical_pattern
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

        movement = (
            future_close
            - historical_close
        ) / historical_close * 100.0

        if movement > 0:
            direction = "BUY"

        elif movement < 0:
            direction = "SELL"

        else:
            direction = "FLAT"

        matches.append({

            "index": i,

            "similarity":
                similarity,

            "movement_percent":
                movement,

            "direction":
                direction

        })

    matches.sort(
        key=lambda x:
            x["similarity"],
        reverse=True
    )

    return matches[:MAX_MATCHES]


def detect_historical_pattern(
    candles
):

    matches = find_historical_matches(
        candles
    )

    if not matches:

        return (
            pattern_result(
                "Historical Similarity",
                "NEUTRAL",
                0,
                "No historical matches"
            ),
            {
                "sample_size": 0,
                "buy_probability": 0.0,
                "sell_probability": 0.0,
                "average_similarity": 0.0,
                "best_similarity": 0.0
            }
        )

    buy = 0
    sell = 0

    similarities = []

    for match in matches:

        similarities.append(
            match["similarity"]
        )

        if match["direction"] == "BUY":
            buy += 1

        elif match["direction"] == "SELL":
            sell += 1

    total = len(matches)

    buy_probability = (
        buy
        / total
        * 100.0
    )

    sell_probability = (
        sell
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

    if buy_probability > sell_probability:

        direction = "BUY"
        confidence = buy_probability

    elif sell_probability > buy_probability:

        direction = "SELL"
        confidence = sell_probability

    else:

        direction = "NEUTRAL"
        confidence = 0.0

    confidence *= (
        0.75
        + average_similarity * 0.25
    )

    result = pattern_result(
        "Historical Similarity",
        direction,
        confidence,
        f"{total} historical matches"
    )

    statistics = {

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

        "average_similarity":
            round(
                average_similarity,
                4
            ),

        "best_similarity":
            round(
                best_similarity,
                4
            )
    }

    return result, statistics


# ============================================================
# ALL 10 PATTERNS
# ============================================================

def analyze_all_patterns(
    candles
):

    results = []

    detectors = [

        detect_trend_continuation,

        detect_pullback,

        detect_breakout,

        detect_breakout_retest,

        detect_sr_reversal,

        detect_double_top_bottom,

        detect_head_shoulders,

        detect_candlestick,

        detect_range_false_breakout,

    ]

    for detector in detectors:

        try:

            result = detector(
                candles
            )

            results.append(result)

        except Exception as exc:

            results.append(
                pattern_result(
                    detector.__name__,
                    "NEUTRAL",
                    0,
                    str(exc)
                )
            )

    historical_result, historical_stats = (
        detect_historical_pattern(
            candles
        )
    )

    results.append(
        historical_result
    )

    return (
        results,
        historical_stats
    )


# ============================================================
# CONSENSUS
# ============================================================

def calculate_consensus(
    patterns
):

    buy_weight = 0.0
    sell_weight = 0.0

    buy_patterns = []
    sell_patterns = []

    for pattern in patterns:

        direction = pattern[
            "direction"
        ]

        confidence = pattern[
            "confidence"
        ]

        if direction == "BUY":

            buy_weight += confidence

            buy_patterns.append(
                pattern
            )

        elif direction == "SELL":

            sell_weight += confidence

            sell_patterns.append(
                pattern
            )

    if (
        buy_weight == 0
        and sell_weight == 0
    ):

        return {
            "direction": "NO_TRADE",
            "confidence": 0.0,
            "buy_score": 0.0,
            "sell_score": 0.0,
            "buy_count": 0,
            "sell_count": 0,
            "agreement": 0
        }

    if buy_weight > sell_weight:

        direction = "BUY"

        confidence = (
            buy_weight
            / (
                buy_weight
                + sell_weight
            )
            * 100.0
        )

    elif sell_weight > buy_weight:

        direction = "SELL"

        confidence = (
            sell_weight
            / (
                buy_weight
                + sell_weight
            )
            * 100.0
        )

    else:

        direction = "NO_TRADE"
        confidence = 0.0

    if direction == "BUY":

        agreement = len(
            buy_patterns
        )

    elif direction == "SELL":

        agreement = len(
            sell_patterns
        )

    else:

        agreement = 0

    return {

        "direction":
            direction,

        "confidence":
            round(
                confidence,
                2
            ),

        "buy_score":
            round(
                buy_weight,
                2
            ),

        "sell_score":
            round(
                sell_weight,
                2
            ),

        "buy_count":
            len(
                buy_patterns
            ),

        "sell_count":
            len(
                sell_patterns
            ),

        "agreement":
            agreement
    }


# ============================================================
# SCORE
# ============================================================

def calculate_signal_score(
    consensus,
    patterns,
    trend,
    risk_reward
):

    direction = consensus[
        "direction"
    ]

    confidence = consensus[
        "confidence"
    ]

    if direction == "NO_TRADE":
        return 0.0

    agreement = consensus[
        "agreement"
    ]

    agreement_score = clamp(
        agreement
        / 6.0
        * 100.0,
        0.0,
        100.0
    )

    if direction == trend["direction"]:

        trend_score = trend[
            "strength"
        ]

    else:

        trend_score = 40.0

    rr_score = clamp(
        risk_reward
        / 2.0
        * 100.0,
        0.0,
        100.0
    )

    score = (
        confidence * 0.50
        +
        agreement_score * 0.20
        +
        trend_score * 0.15
        +
        rr_score * 0.15
    )

    return round(
        clamp(
            score,
            0.0,
            100.0
        ),
        2
    )


# ============================================================
# ENTRY / SL / TP
# ============================================================

def calculate_trade_levels(
    candles,
    direction,
    patterns
):

    entry = candles[-1]["close"]

    atr = calculate_atr(candles)

    if atr <= 0:

        atr = (
            entry
            * 0.001
        )

    swing_highs = find_swing_highs(
        candles,
        2
    )

    swing_lows = find_swing_lows(
        candles,
        2
    )

    if direction == "BUY":

        recent_lows = [
            x["price"]
            for x in swing_lows
            if x["index"]
            >= len(candles) - 40
        ]

        if recent_lows:

            support = min(
                recent_lows[-3:]
            )

            stop_loss = min(
                entry - atr,
                support - atr * 0.15
            )

        else:

            stop_loss = (
                entry - atr
            )

        risk = (
            entry
            - stop_loss
        )

        take_profit = (
            entry
            + risk
            * RISK_REWARD
        )

    else:

        recent_highs = [
            x["price"]
            for x in swing_highs
            if x["index"]
            >= len(candles) - 40
        ]

        if recent_highs:

            resistance = max(
                recent_highs[-3:]
            )

            stop_loss = max(
                entry + atr,
                resistance + atr * 0.15
            )

        else:

            stop_loss = (
                entry + atr
            )

        risk = (
            stop_loss
            - entry
        )

        take_profit = (
            entry
            - risk
            * RISK_REWARD
        )

    risk = abs(
        entry
        - stop_loss
    )

    reward = abs(
        take_profit
        - entry
    )

    actual_rr = (
        reward / risk
        if risk > 0
        else 0.0
    )

    # Entry zone based on ATR
    entry_zone_low = (
        entry
        - atr * 0.20
    )

    entry_zone_high = (
        entry
        + atr * 0.20
    )

    return {

        "entry":
            round_price(entry),

        "entry_zone_low":
            round_price(
                entry_zone_low
            ),

        "entry_zone_high":
            round_price(
                entry_zone_high
            ),

        "stop_loss":
            round_price(
                stop_loss
            ),

        "take_profit":
            round_price(
                take_profit
            ),

        "risk_reward":
            round(
                actual_rr,
                2
            ),

        "risk_distance":
            round(
                risk,
                4
            ),

        "reward_distance":
            round(
                reward,
                4
            ),

        "atr":
            round(
                atr,
                4
            )
    }


# ============================================================
# MAIN SIGNAL ENGINE
# ============================================================

def generate_signal(
    candles
):

    latest = candles[-1]

    patterns, historical_stats = (
        analyze_all_patterns(
            candles
        )
    )

    trend = detect_trend(
        candles
    )

    provisional_consensus = (
        calculate_consensus(
            patterns
        )
    )

    direction = provisional_consensus[
        "direction"
    ]

    if direction in [
        "BUY",
        "SELL"
    ]:

        levels = calculate_trade_levels(
            candles,
            direction,
            patterns
        )

        score = calculate_signal_score(
            provisional_consensus,
            patterns,
            trend,
            levels["risk_reward"]
        )

        probability = (
            provisional_consensus[
                "confidence"
            ]
        )

        agreement = (
            provisional_consensus[
                "agreement"
            ]
        )

        valid = (
            probability
            >= MIN_PROBABILITY
            and score
            >= MIN_SCORE
            and agreement
            >= MIN_PATTERNS
            and levels[
                "risk_reward"
            ] >= 1.20
        )

        if valid:

            signal = direction

        else:

            signal = "NO_TRADE"

    else:

        levels = {

            "entry":
                round_price(
                    latest["close"]
                ),

            "entry_zone_low":
                None,

            "entry_zone_high":
                None,

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                0.0,

            "risk_distance":
                0.0,

            "reward_distance":
                0.0,

            "atr":
                round(
                    calculate_atr(
                        candles
                    ),
                    4
                )
        }

        probability = 0.0
        score = 0.0
        agreement = 0
        signal = "NO_TRADE"

    detected = []

    for pattern in patterns:

        if pattern["direction"] != "NEUTRAL":

            detected.append(
                pattern
            )

    return {

        "timestamp":
            latest["datetime"],

        "symbol":
            SYMBOL,

        "timeframe":
            DISPLAY_TIMEFRAME,

        "signal":
            signal,

        "candidate_direction":
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

        "pattern_agreement":
            agreement,

        "entry":
            levels["entry"],

        "entry_zone":
            {

                "low":
                    levels[
                        "entry_zone_low"
                    ],

                "high":
                    levels[
                        "entry_zone_high"
                    ]

            },

        "stop_loss":
            levels["stop_loss"],

        "take_profit":
            levels["take_profit"],

        "risk_reward":
            levels["risk_reward"],

        "atr":
            levels["atr"],

        "trend":
            trend,

        "patterns":
            patterns,

        "detected_patterns":
            detected,

        "historical_statistics":
            historical_stats,

        "rules": {

            "minimum_probability":
                MIN_PROBABILITY,

            "minimum_score":
                MIN_SCORE,

            "minimum_patterns":
                MIN_PATTERNS,

            "minimum_similarity":
                MIN_SIMILARITY,

            "risk_reward":
                RISK_REWARD

        },

        "method":
            "Multi-Pattern XAUUSD M5 Engine",

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

def send_welcome_message():

    global WELCOME_SENT

    if WELCOME_SENT:
        return

    message = (
        "🟢 <b>XAUUSD M5 MULTI-PATTERN BOT ONLINE</b>\n"
        "\n"
        "ระบบเริ่มทำงานเรียบร้อยแล้ว\n"
        "\n"
        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"
        "<b>Data:</b> Twelve Data\n"
        "\n"
        "<b>Pattern Engine:</b>\n"
        "1. Trend Continuation\n"
        "2. Pullback\n"
        "3. Breakout\n"
        "4. Breakout Retest\n"
        "5. Support/Resistance Reversal\n"
        "6. Double Top/Bottom\n"
        "7. Head & Shoulders\n"
        "8. Candlestick Reversal\n"
        "9. Range/False Breakout\n"
        "10. Historical Similarity\n"
        "\n"
        f"<b>Minimum Probability:</b> "
        f"{MIN_PROBABILITY:.0f}%\n"
        f"<b>Minimum Score:</b> "
        f"{MIN_SCORE:.0f}\n"
        f"<b>Minimum Agreement:</b> "
        f"{MIN_PATTERNS}\n"
        f"<b>Risk/Reward:</b> "
        f"1:{RISK_REWARD:.2f}\n"
        "\n"
        "ระบบพร้อมวิเคราะห์\n"
        "BUY / SELL / NO TRADE\n"
        "\n"
        "<i>Multi-Pattern Historical Trading Engine</i>"
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        WELCOME_SENT = True

        STATE[
            "last_welcome"
        ] = utc_now().isoformat()

        print(
            "Telegram welcome message sent successfully"
        )

    else:

        print(
            "Telegram welcome failed:",
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

    message = (
        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"
        f"<b>SIGNAL:</b> {direction}\n"
        f"<b>Probability:</b> "
        f"{signal['probability']:.2f}%\n"
        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"
        f"<b>Pattern Agreement:</b> "
        f"{signal['pattern_agreement']}\n"
        "\n"
        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"
        f"<b>ENTRY ZONE:</b> "
        f"{signal['entry_zone']['low']:.2f}"
        " - "
        f"{signal['entry_zone']['high']:.2f}\n"
        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"
        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"
        f"<b>RISK/REWARD:</b> "
        f"1:{signal['risk_reward']:.2f}\n"
        "\n"
        "<b>PATTERNS:</b>\n"
    )

    for pattern in signal[
        "patterns"
    ]:

        if pattern["direction"] == direction:

            message += (
                f"✓ {pattern['name']} "
                f"{pattern['confidence']:.0f}%\n"
            )

    message += (
        "\n"
        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"
        "\n"
        "<i>Multi-Pattern XAUUSD M5 Engine</i>"
    )

    return message


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
        and signal["signal"]
        in ["BUY", "SELL"]
    ):

        signal_key = (
            str(
                signal["timestamp"]
            )
            + "_"
            + signal["signal"]
            + "_"
            + str(
                signal["pattern_agreement"]
            )
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
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "name":
            "XAUUSD M5 Multi-Pattern Telegram Signal",

        "status":
            "online",

        "data_source":
            "Twelve Data",

        "symbol":
            SYMBOL,

        "timeframe":
            DISPLAY_TIMEFRAME,

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "engine":
            "Multi-Pattern Trading Engine",

        "patterns": [

            "Trend Continuation",
            "Pullback",
            "Breakout",
            "Breakout Retest",
            "Support/Resistance Reversal",
            "Double Top/Bottom",
            "Head & Shoulders",
            "Candlestick Reversal",
            "Range/False Breakout",
            "Historical Similarity"

        ],

        "rules": {

            "minimum_probability":
                MIN_PROBABILITY,

            "minimum_score":
                MIN_SCORE,

            "minimum_patterns":
                MIN_PATTERNS,

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
            DISPLAY_TIMEFRAME,

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

        "welcome_sent":
            WELCOME_SENT,

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

            "error":
                str(exc)

        }), 500


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (
        "🟢 <b>TELEGRAM TEST</b>\n"
        "\n"
        "XAUUSD M5 Multi-Pattern Bot\n"
        "Telegram connection is working.\n"
        "\n"
        f"<b>Time:</b> "
        f"{utc_now().isoformat()}"
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

        "telegram":
            False,

        "error":
            error

    }), 500


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        # Ensure welcome notification
        send_welcome_message()

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
            100,
            total_candles
            - BACKTEST_POINTS
            - FORWARD_BARS
        )

        end = (
            total_candles
            - FORWARD_BARS
            - 1
        )

        if end <= start:

            return jsonify({

                "status":
                    "error",

                "error":
                    "Not enough candles"

            }), 400

        trades = []

        for i in range(
            start,
            end
        ):

            historical_candles = (
                candles[:i + 1]
            )

            try:

                signal = generate_signal(
                    historical_candles
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

            entry = safe_float(
                signal["entry"]
            )

            stop_loss = safe_float(
                signal["stop_loss"]
            )

            take_profit = safe_float(
                signal["take_profit"]
            )

            if (
                entry <= 0
                or stop_loss <= 0
                or take_profit <= 0
            ):

                continue

            result = "TIMEOUT"

            exit_price = entry

            exit_index = min(
                i + FORWARD_BARS,
                len(candles) - 1
            )

            mfe = 0.0
            mae = 0.0

            for j in range(
                i + 1,
                exit_index + 1
            ):

                candle = candles[j]

                high = candle["high"]
                low = candle["low"]

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

                    # Conservative assumption
                    if hit_sl:

                        result = "LOSS"
                        exit_price = stop_loss
                        exit_index = j
                        break

                    if hit_tp:

                        result = "WIN"
                        exit_price = take_profit
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

                    if hit_sl:

                        result = "LOSS"
                        exit_price = stop_loss
                        exit_index = j
                        break

                    if hit_tp:

                        result = "WIN"
                        exit_price = take_profit
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

            trades.append({

                "timestamp":
                    candles[i]["datetime"],

                "signal":
                    direction,

                "probability":
                    signal["probability"],

                "score":
                    signal["score"],

                "pattern_agreement":
                    signal["pattern_agreement"],

                "entry":
                    round_price(entry),

                "stop_loss":
                    round_price(stop_loss),

                "take_profit":
                    round_price(take_profit),

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
                    exit_index - i

            })

        total = len(trades)

        wins = sum(
            1
            for t in trades
            if t["result"] == "WIN"
        )

        losses = sum(
            1
            for t in trades
            if t["result"] == "LOSS"
        )

        timeouts = sum(
            1
            for t in trades
            if t["result"] == "TIMEOUT"
        )

        buy_count = sum(
            1
            for t in trades
            if t["signal"] == "BUY"
        )

        sell_count = sum(
            1
            for t in trades
            if t["signal"] == "SELL"
        )

        total_profit = sum(
            max(
                t["pnl_percent"],
                0
            )
            for t in trades
        )

        total_loss = sum(
            abs(
                min(
                    t["pnl_percent"],
                    0
                )
            )
            for t in trades
        )

        net_profit = (
            total_profit
            - total_loss
        )

        if total > 0:

            win_rate = (
                wins
                / total
                * 100.0
            )

            loss_rate = (
                losses
                / total
                * 100.0
            )

            timeout_rate = (
                timeouts
                / total
                * 100.0
            )

        else:

            win_rate = 0.0
            loss_rate = 0.0
            timeout_rate = 0.0

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

        expectancy = (
            net_profit / total
            if total > 0
            else 0.0
        )

        # Max drawdown
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
                peak - equity
            )

            max_drawdown = max(
                max_drawdown,
                drawdown
            )

        average_probability = (
            sum(
                t["probability"]
                for t in trades
            ) / total
            if total > 0
            else 0.0
        )

        average_score = (
            sum(
                t["score"]
                for t in trades
            ) / total
            if total > 0
            else 0.0
        )

        average_mfe = (
            sum(
                t["mfe_percent"]
                for t in trades
            ) / total
            if total > 0
            else 0.0
        )

        average_mae = (
            sum(
                t["mae_percent"]
                for t in trades
            ) / total
            if total > 0
            else 0.0
        )

        return jsonify({

            "status":
                "completed",

            "symbol":
                SYMBOL,

            "timeframe":
                DISPLAY_TIMEFRAME,

            "data_source":
                "Twelve Data XAU/USD",

            "candles_available":
                total_candles,

            "test_points":
                BACKTEST_POINTS,

            "rules": {

                "minimum_probability":
                    MIN_PROBABILITY,

                "minimum_score":
                    MIN_SCORE,

                "minimum_patterns":
                    MIN_PATTERNS,

                "minimum_similarity":
                    MIN_SIMILARITY,

                "risk_reward":
                    RISK_REWARD,

                "forward_bars":
                    FORWARD_BARS

            },

            "signals": {

                "total":
                    total,

                "buy":
                    buy_count,

                "sell":
                    sell_count

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

def initialize():

    print("=" * 60)

    print(
        "XAUUSD M5 MULTI-PATTERN BOT"
    )

    print("=" * 60)

    print(
        "Symbol:",
        SYMBOL
    )

    print(
        "Timeframe:",
        DISPLAY_TIMEFRAME
    )

    print(
        "Twelve Data:",
        bool(
            TWELVE_DATA_API_KEY
        )
    )

    print(
        "Telegram:",
        bool(
            TELEGRAM_BOT_TOKEN
            and TELEGRAM_CHAT_ID
        )
    )

    print(
        "Patterns: 10"
    )

    print(
        "Minimum Probability:",
        MIN_PROBABILITY
    )

    print(
        "Minimum Score:",
        MIN_SCORE
    )

    print(
        "Minimum Pattern Agreement:",
        MIN_PATTERNS
    )

    print("=" * 60)

    # Send immediately when Gunicorn worker starts
    send_welcome_message()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    initialize()

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

else:

    # Gunicorn:
    # gunicorn app:app
    initialize()

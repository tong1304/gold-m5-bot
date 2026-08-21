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

CANDLE_LIMIT = 500

# Minimum confidence required before considering a trade
MIN_CONFIDENCE = 70.0

# Minimum risk/reward
MIN_RISK_REWARD = 1.50

# Minimum ATR
MIN_ATR = 0.50

# Number of candles used for structure analysis
STRUCTURE_LOOKBACK = 100

# Swing detection
SWING_LEFT = 2
SWING_RIGHT = 2

# Pattern tolerance
LEVEL_TOLERANCE_ATR = 0.35

# Breakout tolerance
BREAKOUT_BUFFER_ATR = 0.10

# Retest lookback
RETEST_LOOKBACK = 8

# Telegram notification
SEND_NO_TRADE_NOTIFICATION = False


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
    "last_pattern": None,
}

STARTUP_NOTIFICATION_SENT = False


# ============================================================
# TIME
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# NUMBER HELPERS
# ============================================================

def round_price(value):

    if value is None:
        return None

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

    # Twelve Data normally returns newest first.
    candles.reverse()

    if len(candles) < 100:

        raise RuntimeError(
            "Not enough M5 candles for analysis"
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

        tr2 = abs(
            high - previous_close
        )

        tr3 = abs(
            low - previous_close
        )

        true_ranges.append(
            max(
                tr1,
                tr2,
                tr3
            )
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
    values,
    period
):

    if not values:

        return 0.0

    if len(values) < period:

        return sum(values) / len(values)

    multiplier = 2.0 / (
        period + 1.0
    )

    ema = sum(
        values[:period]
    ) / period

    for value in values[period:]:

        ema = (
            (value - ema)
            * multiplier
            + ema
        )

    return ema


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
        candle["close"]
        for candle in candles
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

    average_gain = (
        sum(recent_gains)
        / period
    )

    average_loss = (
        sum(recent_losses)
        / period
    )

    if average_loss == 0:

        return 100.0

    rs = (
        average_gain
        / average_loss
    )

    rsi = (
        100.0
        - (
            100.0
            / (1.0 + rs)
        )
    )

    return rsi


# ============================================================
# CANDLE INFORMATION
# ============================================================

def candle_information(candle):

    open_price = candle["open"]
    high = candle["high"]
    low = candle["low"]
    close = candle["close"]

    body = abs(
        close - open_price
    )

    total_range = (
        high - low
    )

    if total_range <= 0:

        return {
            "body": 0.0,
            "range": 0.0,
            "body_ratio": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "bullish": False,
            "bearish": False,
        }

    upper_wick = (
        high
        - max(
            open_price,
            close
        )
    )

    lower_wick = (
        min(
            open_price,
            close
        )
        - low
    )

    return {
        "body": body,
        "range": total_range,
        "body_ratio": body / total_range,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "bullish": close > open_price,
        "bearish": close < open_price,
    }


# ============================================================
# MARKET STRUCTURE
# ============================================================

def find_swing_highs(
    candles
):

    highs = []

    start = SWING_LEFT
    end = (
        len(candles)
        - SWING_RIGHT
    )

    for i in range(
        start,
        end
    ):

        current = candles[i]["high"]

        left = [
            candles[j]["high"]
            for j in range(
                i - SWING_LEFT,
                i
            )
        ]

        right = [
            candles[j]["high"]
            for j in range(
                i + 1,
                i + SWING_RIGHT + 1
            )
        ]

        if (
            current > max(left)
            and current >= max(right)
        ):

            highs.append({
                "index": i,
                "price": current,
                "datetime":
                    candles[i]["datetime"]
            })

    return highs


def find_swing_lows(
    candles
):

    lows = []

    start = SWING_LEFT
    end = (
        len(candles)
        - SWING_RIGHT
    )

    for i in range(
        start,
        end
    ):

        current = candles[i]["low"]

        left = [
            candles[j]["low"]
            for j in range(
                i - SWING_LEFT,
                i
            )
        ]

        right = [
            candles[j]["low"]
            for j in range(
                i + 1,
                i + SWING_RIGHT + 1
            )
        ]

        if (
            current < min(left)
            and current <= min(right)
        ):

            lows.append({
                "index": i,
                "price": current,
                "datetime":
                    candles[i]["datetime"]
            })

    return lows


# ============================================================
# TREND
# ============================================================

def detect_trend(
    candles
):

    closes = [
        candle["close"]
        for candle in candles
    ]

    if len(closes) < 50:

        return {
            "direction": "NEUTRAL",
            "strength": 0.0,
            "ema20": closes[-1],
            "ema50": closes[-1],
        }

    ema20 = calculate_ema(
        closes,
        20
    )

    ema50 = calculate_ema(
        closes,
        50
    )

    current = closes[-1]

    recent_change = (
        closes[-1]
        - closes[-20]
    )

    atr = calculate_atr(
        candles
    )

    if atr <= 0:
        atr = 1.0

    if (
        ema20 > ema50
        and current > ema20
        and recent_change > atr * 0.50
    ):

        strength = min(
            100.0,
            65.0
            + (
                abs(recent_change)
                / atr
            ) * 5.0
        )

        return {
            "direction": "BULLISH",
            "strength": round(
                strength,
                2
            ),
            "ema20": ema20,
            "ema50": ema50,
        }

    if (
        ema20 < ema50
        and current < ema20
        and recent_change < -atr * 0.50
    ):

        strength = min(
            100.0,
            65.0
            + (
                abs(recent_change)
                / atr
            ) * 5.0
        )

        return {
            "direction": "BEARISH",
            "strength": round(
                strength,
                2
            ),
            "ema20": ema20,
            "ema50": ema50,
        }

    if ema20 > ema50:

        return {
            "direction": "BULLISH",
            "strength": 55.0,
            "ema20": ema20,
            "ema50": ema50,
        }

    if ema20 < ema50:

        return {
            "direction": "BEARISH",
            "strength": 55.0,
            "ema20": ema20,
            "ema50": ema50,
        }

    return {
        "direction": "NEUTRAL",
        "strength": 50.0,
        "ema20": ema20,
        "ema50": ema50,
    }


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def detect_levels(
    candles,
    atr
):

    swing_highs = find_swing_highs(
        candles
    )

    swing_lows = find_swing_lows(
        candles
    )

    recent_highs = [
        x["price"]
        for x in swing_highs[-10:]
    ]

    recent_lows = [
        x["price"]
        for x in swing_lows[-10:]
    ]

    current_price = candles[-1]["close"]

    resistance_candidates = [
        x
        for x in recent_highs
        if x > current_price
    ]

    support_candidates = [
        x
        for x in recent_lows
        if x < current_price
    ]

    if resistance_candidates:

        resistance = min(
            resistance_candidates
        )

    elif recent_highs:

        resistance = max(
            recent_highs
        )

    else:

        resistance = max(
            candle["high"]
            for candle in candles[-20:]
        )

    if support_candidates:

        support = max(
            support_candidates
        )

    elif recent_lows:

        support = min(
            recent_lows
        )

    else:

        support = min(
            candle["low"]
            for candle in candles[-20:]
        )

    return {
        "support": support,
        "resistance": resistance,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


# ============================================================
# MOMENTUM
# ============================================================

def detect_momentum(
    candles
):

    rsi = calculate_rsi(
        candles
    )

    recent = candles[-5:]

    bullish_count = 0
    bearish_count = 0

    for candle in recent:

        if candle["close"] > candle["open"]:

            bullish_count += 1

        elif candle["close"] < candle["open"]:

            bearish_count += 1

    if (
        rsi >= 55
        and bullish_count >= 3
    ):

        direction = "BULLISH"

    elif (
        rsi <= 45
        and bearish_count >= 3
    ):

        direction = "BEARISH"

    else:

        direction = "NEUTRAL"

    return {
        "direction": direction,
        "rsi": round(
            rsi,
            2
        ),
        "bullish_candles":
            bullish_count,
        "bearish_candles":
            bearish_count,
    }


# ============================================================
# PATTERN: BREAKOUT
# ============================================================

def detect_breakout(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    current = candles[-1]
    previous = candles[-2]

    resistance = levels["resistance"]
    support = levels["support"]

    buffer = (
        atr
        * BREAKOUT_BUFFER_ATR
    )

    candle = candle_information(
        current
    )

    # Bullish breakout
    if (
        current["close"]
        > resistance + buffer
        and previous["close"]
        <= resistance + buffer
        and candle["bullish"]
        and candle["body_ratio"] >= 0.45
    ):

        confidence = 70.0

        if trend["direction"] == "BULLISH":
            confidence += 10.0

        if momentum["direction"] == "BULLISH":
            confidence += 10.0

        if candle["body_ratio"] >= 0.65:
            confidence += 5.0

        return {
            "pattern":
                "BREAKOUT",
            "direction":
                "BUY",
            "confidence":
                min(
                    confidence,
                    95.0
                ),
            "level":
                resistance,
            "reason": [
                "ราคาทะลุ Resistance",
                "แท่ง Breakout เป็น Bullish",
                "แท่งมี Body แข็งแรง",
            ]
        }

    # Bearish breakout
    if (
        current["close"]
        < support - buffer
        and previous["close"]
        >= support - buffer
        and candle["bearish"]
        and candle["body_ratio"] >= 0.45
    ):

        confidence = 70.0

        if trend["direction"] == "BEARISH":
            confidence += 10.0

        if momentum["direction"] == "BEARISH":
            confidence += 10.0

        if candle["body_ratio"] >= 0.65:
            confidence += 5.0

        return {
            "pattern":
                "BREAKOUT",
            "direction":
                "SELL",
            "confidence":
                min(
                    confidence,
                    95.0
                ),
            "level":
                support,
            "reason": [
                "ราคาหลุด Support",
                "แท่ง Breakout เป็น Bearish",
                "แท่งมี Body แข็งแรง",
            ]
        }

    return None


# ============================================================
# PATTERN: BREAKOUT RETEST
# ============================================================

def detect_breakout_retest(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    if len(candles) < 15:

        return None

    current = candles[-1]

    resistance = levels["resistance"]
    support = levels["support"]

    tolerance = (
        atr
        * LEVEL_TOLERANCE_ATR
    )

    recent = candles[
        -RETEST_LOOKBACK:
    ]

    # --------------------------------------------------------
    # Bullish breakout + retest
    # --------------------------------------------------------

    bullish_breakout = False

    for candle in candles[
        -RETEST_LOOKBACK - 5:
        -1
    ]:

        if (
            candle["close"]
            > resistance
            + atr * 0.10
        ):

            bullish_breakout = True
            break

    retested = False

    if bullish_breakout:

        for candle in recent:

            if (
                candle["low"]
                <= resistance + tolerance
                and candle["low"]
                >= resistance - tolerance
            ):

                retested = True
                break

    if (
        bullish_breakout
        and retested
        and current["close"]
        > resistance
        and current["close"]
        > current["open"]
    ):

        confidence = 78.0

        if trend["direction"] == "BULLISH":
            confidence += 7.0

        if momentum["direction"] == "BULLISH":
            confidence += 7.0

        return {
            "pattern":
                "BREAKOUT + RETEST",
            "direction":
                "BUY",
            "confidence":
                min(
                    confidence,
                    95.0
                ),
            "level":
                resistance,
            "reason": [
                "เกิด Breakout",
                "ราคากลับมา Retest",
                "Retest ไม่หลุดระดับ Breakout",
                "ราคากลับมายืนเหนือระดับ",
            ]
        }

    # --------------------------------------------------------
    # Bearish breakout + retest
    # --------------------------------------------------------

    bearish_breakout = False

    for candle in candles[
        -RETEST_LOOKBACK - 5:
        -1
    ]:

        if (
            candle["close"]
            < support
            - atr * 0.10
        ):

            bearish_breakout = True
            break

    retested = False

    if bearish_breakout:

        for candle in recent:

            if (
                candle["high"]
                >= support - tolerance
                and candle["high"]
                <= support + tolerance
            ):

                retested = True
                break

    if (
        bearish_breakout
        and retested
        and current["close"]
        < support
        and current["close"]
        < current["open"]
    ):

        confidence = 78.0

        if trend["direction"] == "BEARISH":
            confidence += 7.0

        if momentum["direction"] == "BEARISH":
            confidence += 7.0

        return {
            "pattern":
                "BREAKOUT + RETEST",
            "direction":
                "SELL",
            "confidence":
                min(
                    confidence,
                    95.0
                ),
            "level":
                support,
            "reason": [
                "เกิด Breakdown",
                "ราคากลับมา Retest",
                "Retest ไม่กลับเข้า Range",
                "ราคากลับมายืนใต้ระดับ",
            ]
        }

    return None


# ============================================================
# PATTERN: PULLBACK
# ============================================================

def detect_pullback(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    if len(candles) < 20:

        return None

    current = candles[-1]

    recent = candles[-8:]

    recent_high = max(
        x["high"]
        for x in recent
    )

    recent_low = min(
        x["low"]
        for x in recent
    )

    current_info = candle_information(
        current
    )

    # Bullish pullback
    if trend["direction"] == "BULLISH":

        pullback_size = (
            recent_high
            - current["low"]
        )

        if (
            pullback_size >= atr * 0.50
            and current_info["bullish"]
            and current["close"]
            > candles[-2]["close"]
        ):

            confidence = 72.0

            if momentum["direction"] == "BULLISH":
                confidence += 10.0

            return {
                "pattern":
                    "PULLBACK",
                "direction":
                    "BUY",
                "confidence":
                    min(
                        confidence,
                        90.0
                    ),
                "level":
                    levels["support"],
                "reason": [
                    "Trend หลักเป็นขาขึ้น",
                    "ราคามี Pullback",
                    "แท่งล่าสุดเริ่มกลับตัวขึ้น",
                ]
            }

    # Bearish pullback
    if trend["direction"] == "BEARISH":

        pullback_size = (
            current["high"]
            - recent_low
        )

        if (
            pullback_size >= atr * 0.50
            and current_info["bearish"]
            and current["close"]
            < candles[-2]["close"]
        ):

            confidence = 72.0

            if momentum["direction"] == "BEARISH":
                confidence += 10.0

            return {
                "pattern":
                    "PULLBACK",
                "direction":
                    "SELL",
                "confidence":
                    min(
                        confidence,
                        90.0
                    ),
                "level":
                    levels["resistance"],
                "reason": [
                    "Trend หลักเป็นขาลง",
                    "ราคามี Pullback",
                    "แท่งล่าสุดเริ่มกลับตัวลง",
                ]
            }

    return None


# ============================================================
# PATTERN: TREND CONTINUATION
# ============================================================

def detect_trend_continuation(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    if len(candles) < 15:

        return None

    current = candles[-1]

    recent = candles[-6:]

    bullish = sum(
        1
        for x in recent
        if x["close"] > x["open"]
    )

    bearish = sum(
        1
        for x in recent
        if x["close"] < x["open"]
    )

    current_info = candle_information(
        current
    )

    if (
        trend["direction"] == "BULLISH"
        and momentum["direction"] == "BULLISH"
        and bullish >= 4
        and current_info["bullish"]
    ):

        confidence = 74.0

        if trend["strength"] >= 70:
            confidence += 8.0

        return {
            "pattern":
                "TREND CONTINUATION",
            "direction":
                "BUY",
            "confidence":
                min(
                    confidence,
                    92.0
                ),
            "level":
                levels["support"],
            "reason": [
                "Trend เป็น Bullish",
                "Momentum สนับสนุน",
                "แท่งส่วนใหญ่เป็น Bullish",
                "ราคาเดินหน้าตาม Trend",
            ]
        }

    if (
        trend["direction"] == "BEARISH"
        and momentum["direction"] == "BEARISH"
        and bearish >= 4
        and current_info["bearish"]
    ):

        confidence = 74.0

        if trend["strength"] >= 70:
            confidence += 8.0

        return {
            "pattern":
                "TREND CONTINUATION",
            "direction":
                "SELL",
            "confidence":
                min(
                    confidence,
                    92.0
                ),
            "level":
                levels["resistance"],
            "reason": [
                "Trend เป็น Bearish",
                "Momentum สนับสนุน",
                "แท่งส่วนใหญ่เป็น Bearish",
                "ราคาเดินหน้าตาม Trend",
            ]
        }

    return None


# ============================================================
# PATTERN: DOUBLE TOP / DOUBLE BOTTOM
# ============================================================

def detect_double_pattern(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    swing_highs = levels[
        "swing_highs"
    ]

    swing_lows = levels[
        "swing_lows"
    ]

    tolerance = (
        atr * 0.50
    )

    current = candles[-1]

    # --------------------------------------------------------
    # Double Top
    # --------------------------------------------------------

    if len(swing_highs) >= 2:

        first = swing_highs[-2]
        second = swing_highs[-1]

        if (
            abs(
                first["price"]
                - second["price"]
            )
            <= tolerance
        ):

            neckline = min(
                candle["low"]
                for candle in candles[
                    first["index"]:
                    second["index"] + 1
                ]
            )

            if (
                current["close"]
                < neckline
                and current["close"]
                < current["open"]
            ):

                confidence = 76.0

                if momentum["direction"] == "BEARISH":
                    confidence += 8.0

                return {
                    "pattern":
                        "DOUBLE TOP",
                    "direction":
                        "SELL",
                    "confidence":
                        min(
                            confidence,
                            92.0
                        ),
                    "level":
                        neckline,
                    "reason": [
                        "พบ Swing High สองยอดใกล้เคียงกัน",
                        "ราคา Break Neckline",
                        "แท่งล่าสุดเป็น Bearish",
                    ]
                }

    # --------------------------------------------------------
    # Double Bottom
    # --------------------------------------------------------

    if len(swing_lows) >= 2:

        first = swing_lows[-2]
        second = swing_lows[-1]

        if (
            abs(
                first["price"]
                - second["price"]
            )
            <= tolerance
        ):

            neckline = max(
                candle["high"]
                for candle in candles[
                    first["index"]:
                    second["index"] + 1
                ]
            )

            if (
                current["close"]
                > neckline
                and current["close"]
                > current["open"]
            ):

                confidence = 76.0

                if momentum["direction"] == "BULLISH":
                    confidence += 8.0

                return {
                    "pattern":
                        "DOUBLE BOTTOM",
                    "direction":
                        "BUY",
                    "confidence":
                        min(
                            confidence,
                            92.0
                        ),
                    "level":
                        neckline,
                    "reason": [
                        "พบ Swing Low สองฐานใกล้เคียงกัน",
                        "ราคา Break Neckline",
                        "แท่งล่าสุดเป็น Bullish",
                    ]
                }

    return None


# ============================================================
# PATTERN: HEAD AND SHOULDERS
# ============================================================

def detect_head_shoulders(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    highs = levels[
        "swing_highs"
    ]

    lows = levels[
        "swing_lows"
    ]

    if len(highs) < 3:

        return None

    h1 = highs[-3]
    h2 = highs[-2]
    h3 = highs[-1]

    shoulder_tolerance = (
        atr * 1.0
    )

    # Regular H&S
    if (
        h2["price"] > h1["price"]
        and h2["price"] > h3["price"]
        and abs(
            h1["price"]
            - h3["price"]
        ) <= shoulder_tolerance
    ):

        between_lows = [
            candle["low"]
            for candle in candles[
                h1["index"]:
                h3["index"] + 1
            ]
        ]

        if between_lows:

            neckline = min(
                between_lows
            )

            current = candles[-1]

            if (
                current["close"]
                < neckline
            ):

                confidence = 82.0

                if momentum["direction"] == "BEARISH":
                    confidence += 7.0

                return {
                    "pattern":
                        "HEAD & SHOULDERS",
                    "direction":
                        "SELL",
                    "confidence":
                        min(
                            confidence,
                            95.0
                        ),
                    "level":
                        neckline,
                    "reason": [
                        "พบไหล่ซ้าย",
                        "พบ Head สูงกว่าไหล่",
                        "พบไหล่ขวาใกล้เคียงไหล่ซ้าย",
                        "ราคา Break Neckline",
                    ]
                }

    # Inverse H&S
    if len(lows) >= 3:

        l1 = lows[-3]
        l2 = lows[-2]
        l3 = lows[-1]

        if (
            l2["price"] < l1["price"]
            and l2["price"] < l3["price"]
            and abs(
                l1["price"]
                - l3["price"]
            ) <= shoulder_tolerance
        ):

            between_highs = [
                candle["high"]
                for candle in candles[
                    l1["index"]:
                    l3["index"] + 1
                ]
            ]

            if between_highs:

                neckline = max(
                    between_highs
                )

                current = candles[-1]

                if (
                    current["close"]
                    > neckline
                ):

                    confidence = 82.0

                    if momentum["direction"] == "BULLISH":
                        confidence += 7.0

                    return {
                        "pattern":
                            "INVERSE HEAD & SHOULDERS",
                        "direction":
                            "BUY",
                        "confidence":
                            min(
                                confidence,
                                95.0
                            ),
                        "level":
                            neckline,
                        "reason": [
                            "พบไหล่ซ้าย",
                            "พบ Head ต่ำกว่าไหล่",
                            "พบไหล่ขวาใกล้เคียงไหล่ซ้าย",
                            "ราคา Break Neckline",
                        ]
                    }

    return None


# ============================================================
# PATTERN: SUPPORT / RESISTANCE REVERSAL
# ============================================================

def detect_reversal(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    current = candles[-1]

    info = candle_information(
        current
    )

    support = levels["support"]
    resistance = levels["resistance"]

    tolerance = (
        atr
        * LEVEL_TOLERANCE_ATR
    )

    # --------------------------------------------------------
    # Support reversal
    # --------------------------------------------------------

    near_support = (
        abs(
            current["low"]
            - support
        )
        <= tolerance
    )

    if (
        near_support
        and info["bullish"]
        and info["lower_wick"]
        > info["body"] * 0.80
        and current["close"]
        > candles[-2]["close"]
    ):

        confidence = 74.0

        if momentum["direction"] == "BULLISH":
            confidence += 8.0

        return {
            "pattern":
                "SUPPORT REVERSAL",
            "direction":
                "BUY",
            "confidence":
                min(
                    confidence,
                    90.0
                ),
            "level":
                support,
            "reason": [
                "ราคาแตะ Support",
                "เกิดแรงซื้อกลับ",
                "มี Lower Wick",
                "แท่งล่าสุดปิดสูงขึ้น",
            ]
        }

    # --------------------------------------------------------
    # Resistance reversal
    # --------------------------------------------------------

    near_resistance = (
        abs(
            current["high"]
            - resistance
        )
        <= tolerance
    )

    if (
        near_resistance
        and info["bearish"]
        and info["upper_wick"]
        > info["body"] * 0.80
        and current["close"]
        < candles[-2]["close"]
    ):

        confidence = 74.0

        if momentum["direction"] == "BEARISH":
            confidence += 8.0

        return {
            "pattern":
                "RESISTANCE REVERSAL",
            "direction":
                "SELL",
            "confidence":
                min(
                    confidence,
                    90.0
                ),
            "level":
                resistance,
            "reason": [
                "ราคาแตะ Resistance",
                "เกิดแรงขายกลับ",
                "มี Upper Wick",
                "แท่งล่าสุดปิดต่ำลง",
            ]
        }

    return None


# ============================================================
# PATTERN: RANGE / FALSE BREAKOUT
# ============================================================

def detect_range_false_breakout(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    if len(candles) < 20:

        return None

    recent = candles[-15:]

    range_high = max(
        x["high"]
        for x in recent
    )

    range_low = min(
        x["low"]
        for x in recent
    )

    range_size = (
        range_high
        - range_low
    )

    if range_size > atr * 4.0:

        return None

    current = candles[-1]

    previous = candles[-2]

    # False breakout above range
    if (
        previous["high"]
        > range_high
        and current["close"]
        < range_high
        and current["bearish"]
        if False
        else False
    ):

        pass

    previous_info = candle_information(
        previous
    )

    current_info = candle_information(
        current
    )

    if (
        previous["high"]
        >= range_high
        and current["close"]
        < range_high
        and current_info["bearish"]
        and previous_info["upper_wick"]
        > previous_info["body"]
    ):

        return {
            "pattern":
                "FALSE BREAKOUT",
            "direction":
                "SELL",
            "confidence":
                78.0,
            "level":
                range_high,
            "reason": [
                "ตลาดอยู่ใน Range",
                "ราคา Break High",
                "Break ไม่สำเร็จ",
                "ราคากลับเข้า Range",
            ]
        }

    if (
        previous["low"]
        <= range_low
        and current["close"]
        > range_low
        and current_info["bullish"]
        and previous_info["lower_wick"]
        > previous_info["body"]
    ):

        return {
            "pattern":
                "FALSE BREAKOUT",
            "direction":
                "BUY",
            "confidence":
                78.0,
            "level":
                range_low,
            "reason": [
                "ตลาดอยู่ใน Range",
                "ราคา Break Low",
                "Break ไม่สำเร็จ",
                "ราคากลับเข้า Range",
            ]
        }

    return None


# ============================================================
# CANDLESTICK REVERSAL
# ============================================================

def detect_candlestick_reversal(
    candles,
    trend,
    momentum,
    atr
):

    if len(candles) < 3:

        return None

    current = candles[-1]

    previous = candles[-2]

    info = candle_information(
        current
    )

    previous_info = candle_information(
        previous
    )

    # Bullish engulfing
    bullish_engulfing = (
        previous_info["bearish"]
        and info["bullish"]
        and current["open"]
        <= previous["close"]
        and current["close"]
        >= previous["open"]
    )

    if bullish_engulfing:

        confidence = 73.0

        if momentum["direction"] == "BULLISH":
            confidence += 8.0

        return {
            "pattern":
                "BULLISH ENGULFING",
            "direction":
                "BUY",
            "confidence":
                min(
                    confidence,
                    90.0
                ),
            "level":
                current["low"],
            "reason": [
                "พบ Bullish Engulfing",
                "แรงซื้อกลืนแท่งก่อนหน้า",
            ]
        }

    # Bearish engulfing
    bearish_engulfing = (
        previous_info["bullish"]
        and info["bearish"]
        and current["open"]
        >= previous["close"]
        and current["close"]
        <= previous["open"]
    )

    if bearish_engulfing:

        confidence = 73.0

        if momentum["direction"] == "BEARISH":
            confidence += 8.0

        return {
            "pattern":
                "BEARISH ENGULFING",
            "direction":
                "SELL",
            "confidence":
                min(
                    confidence,
                    90.0
                ),
            "level":
                current["high"],
            "reason": [
                "พบ Bearish Engulfing",
                "แรงขายกลืนแท่งก่อนหน้า",
            ]
        }

    # Hammer
    if (
        info["lower_wick"]
        >= info["body"] * 2.0
        and info["upper_wick"]
        <= info["body"] * 0.75
    ):

        return {
            "pattern":
                "HAMMER",
            "direction":
                "BUY",
            "confidence":
                72.0,
            "level":
                current["low"],
            "reason": [
                "พบ Hammer",
                "มีแรงซื้อกลับจากด้านล่าง",
            ]
        }

    # Shooting star
    if (
        info["upper_wick"]
        >= info["body"] * 2.0
        and info["lower_wick"]
        <= info["body"] * 0.75
    ):

        return {
            "pattern":
                "SHOOTING STAR",
            "direction":
                "SELL",
            "confidence":
                72.0,
            "level":
                current["high"],
            "reason": [
                "พบ Shooting Star",
                "มีแรงขายกลับจากด้านบน",
            ]
        }

    return None


# ============================================================
# DETECT ALL PATTERNS
# ============================================================

def detect_patterns(
    candles,
    levels,
    trend,
    momentum,
    atr
):

    candidates = []

    detectors = [

        detect_breakout_retest,

        detect_breakout,

        detect_head_shoulders,

        detect_double_pattern,

        detect_range_false_breakout,

        detect_reversal,

        detect_pullback,

        detect_candlestick_reversal,

        detect_trend_continuation,

    ]

    for detector in detectors:

        try:

            result = detector(
                candles,
                levels,
                trend,
                momentum,
                atr
            )

            if result:

                candidates.append(
                    result
                )

        except Exception:

            continue

    if not candidates:

        return []

    # Highest confidence first
    candidates.sort(
        key=lambda x:
            x["confidence"],
        reverse=True
    )

    return candidates


# ============================================================
# ENTRY ANALYSIS
# ============================================================

def calculate_trade_plan(
    direction,
    candles,
    pattern,
    levels,
    atr
):

    current = candles[-1]

    entry = current["close"]

    pattern_level = safe_float(
        pattern.get("level"),
        entry
    )

    recent_lows = [
        x["low"]
        for x in candles[-8:]
    ]

    recent_highs = [
        x["high"]
        for x in candles[-8:]
    ]

    recent_low = min(
        recent_lows
    )

    recent_high = max(
        recent_highs
    )

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if direction == "BUY":

        structural_sl = min(
            pattern_level,
            recent_low
        )

        stop_loss = (
            structural_sl
            - atr * 0.15
        )

        risk = (
            entry
            - stop_loss
        )

        if risk <= 0:

            return None

        take_profit = (
            entry
            + risk * MIN_RISK_REWARD
        )

        # Use resistance when there is enough room
        resistance = levels[
            "resistance"
        ]

        if (
            resistance > entry
            and resistance
            > entry + risk * 1.20
        ):

            candidate_tp = resistance

            candidate_rr = (
                candidate_tp - entry
            ) / risk

            if candidate_rr >= MIN_RISK_REWARD:

                take_profit = candidate_tp

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    else:

        structural_sl = max(
            pattern_level,
            recent_high
        )

        stop_loss = (
            structural_sl
            + atr * 0.15
        )

        risk = (
            stop_loss
            - entry
        )

        if risk <= 0:

            return None

        take_profit = (
            entry
            - risk * MIN_RISK_REWARD
        )

        support = levels[
            "support"
        ]

        if (
            support < entry
            and support
            < entry - risk * 1.20
        ):

            candidate_tp = support

            candidate_rr = (
                entry - candidate_tp
            ) / risk

            if candidate_rr >= MIN_RISK_REWARD:

                take_profit = candidate_tp

    if direction == "BUY":

        risk = (
            entry
            - stop_loss
        )

        reward = (
            take_profit
            - entry
        )

    else:

        risk = (
            stop_loss
            - entry
        )

        reward = (
            entry
            - take_profit
        )

    if risk <= 0 or reward <= 0:

        return None

    risk_reward = (
        reward / risk
    )

    return {
        "entry":
            round_price(entry),

        "stop_loss":
            round_price(stop_loss),

        "take_profit":
            round_price(take_profit),

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

        "risk_reward":
            round(
                risk_reward,
                2
            )
    }


# ============================================================
# ENTRY CONFIRMATION
# ============================================================

def confirm_entry(
    direction,
    candles,
    trend,
    momentum,
    pattern,
    trade_plan
):

    if not trade_plan:

        return {
            "valid": False,
            "reasons": [
                "ไม่สามารถคำนวณ Trade Plan"
            ]
        }

    reasons = []

    current = candles[-1]

    info = candle_information(
        current
    )

    confidence = float(
        pattern["confidence"]
    )

    # Pattern confidence
    if confidence >= MIN_CONFIDENCE:

        reasons.append(
            "Pattern confidence ผ่านเกณฑ์"
        )

    else:

        return {
            "valid": False,
            "reasons": [
                "Pattern confidence ต่ำกว่าเกณฑ์"
            ]
        }

    # Direction confirmation
    if direction == "BUY":

        if trend["direction"] == "BULLISH":

            reasons.append(
                "Trend สนับสนุน BUY"
            )

        elif pattern["pattern"] in [
            "DOUBLE BOTTOM",
            "INVERSE HEAD & SHOULDERS",
            "SUPPORT REVERSAL",
            "FALSE BREAKOUT",
            "BULLISH ENGULFING",
            "HAMMER",
        ]:

            reasons.append(
                "เป็น Reversal Pattern"
            )

        else:

            return {
                "valid": False,
                "reasons": [
                    "Trend ไม่สนับสนุน BUY"
                ]
            }

        if momentum["direction"] == "BULLISH":

            reasons.append(
                "Momentum สนับสนุน BUY"
            )

        elif pattern["pattern"] in [
            "SUPPORT REVERSAL",
            "DOUBLE BOTTOM",
            "HAMMER",
            "BULLISH ENGULFING",
        ]:

            reasons.append(
                "Momentum อยู่ในโซนกลับตัว"
            )

        else:

            return {
                "valid": False,
                "reasons": [
                    "Momentum ไม่ยืนยัน BUY"
                ]
            }

        if not info["bullish"]:

            return {
                "valid": False,
                "reasons": [
                    "แท่งล่าสุดยังไม่ยืนยัน Bullish"
                ]
            }

    else:

        if trend["direction"] == "BEARISH":

            reasons.append(
                "Trend สนับสนุน SELL"
            )

        elif pattern["pattern"] in [
            "DOUBLE TOP",
            "HEAD & SHOULDERS",
            "RESISTANCE REVERSAL",
            "FALSE BREAKOUT",
            "BEARISH ENGULFING",
            "SHOOTING STAR",
        ]:

            reasons.append(
                "เป็น Reversal Pattern"
            )

        else:

            return {
                "valid": False,
                "reasons": [
                    "Trend ไม่สนับสนุน SELL"
                ]
            }

        if momentum["direction"] == "BEARISH":

            reasons.append(
                "Momentum สนับสนุน SELL"
            )

        elif pattern["pattern"] in [
            "RESISTANCE REVERSAL",
            "DOUBLE TOP",
            "SHOOTING STAR",
            "BEARISH ENGULFING",
        ]:

            reasons.append(
                "Momentum อยู่ในโซนกลับตัว"
            )

        else:

            return {
                "valid": False,
                "reasons": [
                    "Momentum ไม่ยืนยัน SELL"
                ]
            }

        if not info["bearish"]:

            return {
                "valid": False,
                "reasons": [
                    "แท่งล่าสุดยังไม่ยืนยัน Bearish"
                ]
            }

    # Risk / Reward
    if (
        trade_plan["risk_reward"]
        >= MIN_RISK_REWARD
    ):

        reasons.append(
            "Risk/Reward ผ่านเกณฑ์"
        )

    else:

        return {
            "valid": False,
            "reasons": [
                "Risk/Reward ต่ำกว่าเกณฑ์"
            ]
        }

    return {
        "valid": True,
        "reasons": reasons
    }


# ============================================================
# SCORE
# ============================================================

def calculate_signal_score(
    pattern,
    trend,
    momentum,
    trade_plan,
    confirmation
):

    score = float(
        pattern["confidence"]
    )

    # Trend
    if (
        (
            pattern["direction"] == "BUY"
            and trend["direction"] == "BULLISH"
        )
        or
        (
            pattern["direction"] == "SELL"
            and trend["direction"] == "BEARISH"
        )
    ):

        score += 5.0

    # Momentum
    if (
        (
            pattern["direction"] == "BUY"
            and momentum["direction"] == "BULLISH"
        )
        or
        (
            pattern["direction"] == "SELL"
            and momentum["direction"] == "BEARISH"
        )
    ):

        score += 5.0

    # RR
    rr = trade_plan[
        "risk_reward"
    ]

    if rr >= 2.0:

        score += 5.0

    elif rr >= 1.5:

        score += 3.0

    # Confirmation
    if confirmation["valid"]:

        score += 5.0

    return round(
        min(
            score,
            100.0
        ),
        2
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(
    candles
):

    latest = candles[-1]

    atr = calculate_atr(
        candles
    )

    if atr < MIN_ATR:

        return {
            "timestamp":
                latest["datetime"],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                "NO_TRADE",

            "status":
                "WAIT",

            "reason":
                "ATR ต่ำเกินไป",

            "atr":
                round(
                    atr,
                    4
                ),

            "pattern":
                None,

            "confidence":
                0.0,

            "entry":
                round_price(
                    latest["close"]
                ),

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                0.0,

            "method":
                "Current Market Pattern Detection",

            "data_source":
                "Twelve Data XAU/USD"
        }

    trend = detect_trend(
        candles
    )

    momentum = detect_momentum(
        candles
    )

    levels = detect_levels(
        candles,
        atr
    )

    candidates = detect_patterns(
        candles,
        levels,
        trend,
        momentum,
        atr
    )

    # No pattern found
    if not candidates:

        return {
            "timestamp":
                latest["datetime"],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                "NO_TRADE",

            "status":
                "WAIT",

            "reason":
                "ยังไม่พบ Pattern ที่มีคุณภาพเพียงพอ",

            "pattern":
                None,

            "confidence":
                0.0,

            "entry":
                round_price(
                    latest["close"]
                ),

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                0.0,

            "atr":
                round(
                    atr,
                    4
                ),

            "market":
                {
                    "trend":
                        trend,

                    "momentum":
                        momentum,

                    "support":
                        round_price(
                            levels["support"]
                        ),

                    "resistance":
                        round_price(
                            levels["resistance"]
                        )
                },

            "candidates":
                [],

            "method":
                "Current Market Pattern Detection",

            "data_source":
                "Twelve Data XAU/USD"
        }

    # Only use the strongest current pattern
    selected_pattern = candidates[0]

    direction = selected_pattern[
        "direction"
    ]

    trade_plan = calculate_trade_plan(
        direction,
        candles,
        selected_pattern,
        levels,
        atr
    )

    confirmation = confirm_entry(
        direction,
        candles,
        trend,
        momentum,
        selected_pattern,
        trade_plan
    )

    if trade_plan:

        score = calculate_signal_score(
            selected_pattern,
            trend,
            momentum,
            trade_plan,
            confirmation
        )

    else:

        score = 0.0

    # --------------------------------------------------------
    # Valid signal
    # --------------------------------------------------------

    if (
        confirmation["valid"]
        and trade_plan
        and score >= MIN_CONFIDENCE
    ):

        return {
            "timestamp":
                latest["datetime"],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                direction,

            "status":
                "READY",

            "pattern":
                selected_pattern["pattern"],

            "confidence":
                round(
                    selected_pattern[
                        "confidence"
                    ],
                    2
                ),

            "score":
                score,

            "entry":
                trade_plan["entry"],

            "stop_loss":
                trade_plan["stop_loss"],

            "take_profit":
                trade_plan["take_profit"],

            "risk_reward":
                trade_plan["risk_reward"],

            "atr":
                round(
                    atr,
                    4
                ),

            "pattern_analysis":
                {
                    "level":
                        round_price(
                            selected_pattern[
                                "level"
                            ]
                        ),

                    "reason":
                        selected_pattern[
                            "reason"
                        ]
                },

            "market":
                {
                    "trend":
                        trend,

                    "momentum":
                        momentum,

                    "support":
                        round_price(
                            levels["support"]
                        ),

                    "resistance":
                        round_price(
                            levels["resistance"]
                        )
                },

            "entry_confirmation":
                confirmation,

            "other_detected_patterns":
                [
                    {
                        "pattern":
                            x["pattern"],

                        "direction":
                            x["direction"],

                        "confidence":
                            round(
                                x["confidence"],
                                2
                            )
                    }
                    for x in candidates[1:6]
                ],

            "method":
                "Current Market Pattern Detection",

            "data_source":
                "Twelve Data XAU/USD"
        }

    # --------------------------------------------------------
    # Pattern found but no entry
    # --------------------------------------------------------

    return {
        "timestamp":
            latest["datetime"],

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "signal":
            "NO_TRADE",

        "status":
            "WAIT",

        "reason":
            confirmation["reasons"],

        "candidate_direction":
            direction,

        "pattern":
            selected_pattern["pattern"],

        "confidence":
            round(
                selected_pattern[
                    "confidence"
                ],
                2
            ),

        "score":
            score,

        "entry":
            (
                trade_plan["entry"]
                if trade_plan
                else round_price(
                    latest["close"]
                )
            ),

        "stop_loss":
            None,

        "take_profit":
            None,

        "risk_reward":
            (
                trade_plan["risk_reward"]
                if trade_plan
                else 0.0
            ),

        "atr":
            round(
                atr,
                4
            ),

        "pattern_analysis":
            {
                "level":
                    round_price(
                        selected_pattern[
                            "level"
                        ]
                    ),

                "reason":
                    selected_pattern[
                        "reason"
                    ]
            },

        "market":
            {
                "trend":
                    trend,

                "momentum":
                    momentum,

                "support":
                    round_price(
                        levels["support"]
                    ),

                "resistance":
                    round_price(
                        levels["resistance"]
                    )
            },

        "entry_confirmation":
            confirmation,

        "other_detected_patterns":
            [
                {
                    "pattern":
                        x["pattern"],

                    "direction":
                        x["direction"],

                    "confidence":
                        round(
                            x["confidence"],
                            2
                        )
                }
                for x in candidates[1:6]
            ],

        "method":
            "Current Market Pattern Detection",

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
# TELEGRAM STARTUP
# ============================================================

def send_startup_notification():

    global STARTUP_NOTIFICATION_SENT

    if STARTUP_NOTIFICATION_SENT:

        return True

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram welcome skipped: "
            "TELEGRAM_BOT_TOKEN not configured"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "Telegram welcome skipped: "
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
        "Current Market Pattern Detection\n"
        "\n"
        "ระบบจะทำงานตามลำดับ:\n"
        "1️⃣ วิเคราะห์กราฟปัจจุบัน\n"
        "2️⃣ ค้นหา Pattern ที่ตรงกับกราฟ\n"
        "3️⃣ วิเคราะห์เฉพาะ Pattern ที่พบ\n"
        "4️⃣ ตรวจ Entry Confirmation\n"
        "5️⃣ คำนวณ SL / TP\n"
        "6️⃣ ตรวจ Risk/Reward\n"
        "7️⃣ ส่ง BUY / SELL เมื่อผ่านเกณฑ์\n"
        "\n"
        f"<b>Minimum Confidence:</b> "
        f"{MIN_CONFIDENCE:.0f}%\n"
        f"<b>Minimum RR:</b> "
        f"1:{MIN_RISK_REWARD:.2f}\n"
        "\n"
        "🟢 พร้อมวิเคราะห์ตลาด"
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        STARTUP_NOTIFICATION_SENT = True

        print(
            "Telegram welcome message sent successfully"
        )

        return True

    print(
        "Telegram welcome failed:",
        error
    )

    return False


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def format_signal_message(
    signal
):

    direction = signal.get(
        "signal"
    )

    if direction == "BUY":

        emoji = "🟢"

    elif direction == "SELL":

        emoji = "🔴"

    else:

        return None

    pattern = signal.get(
        "pattern",
        "UNKNOWN"
    )

    market = signal.get(
        "market",
        {}
    )

    trend = market.get(
        "trend",
        {}
    )

    momentum = market.get(
        "momentum",
        {}
    )

    reasons = signal.get(
        "pattern_analysis",
        {}
    ).get(
        "reason",
        []
    )

    reason_text = "\n".join(
        f"✓ {x}"
        for x in reasons
    )

    return (
        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"
        f"<b>SIGNAL:</b> {direction}\n"
        f"<b>PATTERN:</b> {pattern}\n"
        f"<b>CONFIDENCE:</b> "
        f"{signal['confidence']:.2f}%\n"
        f"<b>SCORE:</b> "
        f"{signal['score']:.2f}\n"
        "\n"
        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"
        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"
        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"
        f"<b>RISK/REWARD:</b> "
        f"1:{signal['risk_reward']:.2f}\n"
        "\n"
        f"<b>TREND:</b> "
        f"{trend.get('direction', 'N/A')}\n"
        f"<b>MOMENTUM:</b> "
        f"{momentum.get('direction', 'N/A')}\n"
        f"<b>RSI:</b> "
        f"{momentum.get('rsi', 0):.2f}\n"
        "\n"
        "<b>PATTERN ANALYSIS</b>\n"
        f"{reason_text}\n"
        "\n"
        f"<b>SUPPORT:</b> "
        f"{market.get('support', 0):.2f}\n"
        f"<b>RESISTANCE:</b> "
        f"{market.get('resistance', 0):.2f}\n"
        "\n"
        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"
        "\n"
        "<i>Current Market Pattern Detection</i>"
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

    STATE["last_pattern"] = (
        signal.get("pattern")
    )

    # --------------------------------------------------------
    # Send signal only once per candle + direction + pattern
    # --------------------------------------------------------

    if send_notification:

        direction = signal.get(
            "signal"
        )

        if direction in [
            "BUY",
            "SELL"
        ]:

            signal_key = (
                str(
                    signal.get(
                        "timestamp"
                    )
                )
                + "_"
                + str(direction)
                + "_"
                + str(
                    signal.get(
                        "pattern"
                    )
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

                    ok, error = (
                        send_telegram(
                            message
                        )
                    )

                    if not ok:

                        STATE[
                            "last_error"
                        ] = error

                    else:

                        STATE[
                            "last_signal_key"
                        ] = signal_key

        elif (
            SEND_NO_TRADE_NOTIFICATION
            and direction == "NO_TRADE"
        ):

            pass

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
            "XAUUSD M5 Current Market Pattern Bot",

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

        "strategy":
            "Current Market Pattern Detection",

        "rules": {

            "minimum_confidence":
                MIN_CONFIDENCE,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "minimum_atr":
                MIN_ATR
        },

        "patterns": [

            "BREAKOUT",

            "BREAKOUT + RETEST",

            "PULLBACK",

            "TREND CONTINUATION",

            "DOUBLE TOP",

            "DOUBLE BOTTOM",

            "HEAD & SHOULDERS",

            "INVERSE HEAD & SHOULDERS",

            "SUPPORT REVERSAL",

            "RESISTANCE REVERSAL",

            "FALSE BREAKOUT",

            "BULLISH ENGULFING",

            "BEARISH ENGULFING",

            "HAMMER",

            "SHOOTING STAR"

        ],

        "endpoints": [

            "/",

            "/health",

            "/test-telegram",

            "/test-data",

            "/signal"

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

        "strategy":
            "Current Market Pattern Detection",

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

        "twelve_data":
            bool(
                TWELVE_DATA_API_KEY
            ),

        "last_update":
            STATE[
                "last_update"
            ],

        "last_pattern":
            STATE[
                "last_pattern"
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
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (
        "🟢 <b>TELEGRAM TEST SUCCESS</b>\n"
        "\n"
        "ระบบ XAUUSD M5 สามารถส่งข้อความ "
        "เข้า Telegram ได้แล้ว\n"
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

        "message":
            "Telegram test failed",

        "error":
            error,

        "telegram":
            False

    }), 500


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
                "M5",

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
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        # Make sure startup message is sent
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

            "status":
                "error",

            "error":
                str(exc)

        }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Send welcome message immediately
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

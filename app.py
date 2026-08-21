import os
import math
import traceback
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

EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14
ATR_PERIOD = 14

MIN_ATR = 0.50

MIN_RISK_REWARD = 1.30

MIN_SCORE = 70.0

FORWARD_BARS = 12

SIGNAL_COOLDOWN = True


# ============================================================
# PATTERNS
# ============================================================

PATTERN_NAMES = [
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
    "Double Top",
]


# ============================================================
# STATE
# ============================================================

STATE = {
    "started_at": None,
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
    "startup_sent": False,
}


# ============================================================
# TIME
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# NUMBER HELPERS
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
    """
    Download XAU/USD M5 candles from Twelve Data.
    """

    if not TWELVE_DATA_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY is not configured"
        )

    url = "https://api.twelvedata.com/time_series"

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
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") == "error":
        raise RuntimeError(
            data.get(
                "message",
                "Twelve Data API error",
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
            "Not enough M5 candles"
        )

    return candles


# ============================================================
# EMA
# ============================================================

def calculate_ema(values, period):
    """
    Calculate EMA series.
    """

    if not values:
        return []

    if len(values) < period:
        return [None] * len(values)

    multiplier = 2.0 / (period + 1.0)

    ema = [None] * len(values)

    initial = sum(
        values[:period]
    ) / period

    ema[period - 1] = initial

    for i in range(
        period,
        len(values),
    ):

        ema[i] = (
            values[i] - ema[i - 1]
        ) * multiplier + ema[i - 1]

    return ema


# ============================================================
# RSI
# ============================================================

def calculate_rsi_series(
    closes,
    period=14,
):
    """
    Wilder-style RSI.
    """

    result = [None] * len(closes)

    if len(closes) <= period:
        return result

    gains = []
    losses = []

    for i in range(1, len(closes)):

        change = (
            closes[i] - closes[i - 1]
        )

        gains.append(
            max(change, 0.0)
        )

        losses.append(
            max(-change, 0.0)
        )

    avg_gain = (
        sum(gains[:period])
        / period
    )

    avg_loss = (
        sum(losses[:period])
        / period
    )

    if avg_loss == 0:
        result[period] = 100.0

    else:

        rs = avg_gain / avg_loss

        result[period] = (
            100.0
            - (
                100.0
                / (1.0 + rs)
            )
        )

    for i in range(
        period + 1,
        len(closes),
    ):

        avg_gain = (
            (
                avg_gain * (period - 1)
            )
            + gains[i - 1]
        ) / period

        avg_loss = (
            (
                avg_loss * (period - 1)
            )
            + losses[i - 1]
        ) / period

        if avg_loss == 0:

            result[i] = 100.0

        else:

            rs = (
                avg_gain
                / avg_loss
            )

            result[i] = (
                100.0
                - (
                    100.0
                    / (1.0 + rs)
                )
            )

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr_series(
    candles,
    period=14,
):
    """
    ATR series.
    """

    result = [None] * len(candles)

    if len(candles) <= period:
        return result

    true_ranges = []

    for i in range(
        len(candles)
    ):

        candle = candles[i]

        high = candle["high"]
        low = candle["low"]

        if i == 0:

            tr = high - low

        else:

            previous_close = (
                candles[i - 1]["close"]
            )

            tr = max(
                high - low,
                abs(
                    high
                    - previous_close
                ),
                abs(
                    low
                    - previous_close
                ),
            )

        true_ranges.append(tr)

    atr = (
        sum(
            true_ranges[:period]
        )
        / period
    )

    result[period - 1] = atr

    for i in range(
        period,
        len(candles),
    ):

        atr = (
            (
                atr * (period - 1)
            )
            + true_ranges[i]
        ) / period

        result[i] = atr

    return result


# ============================================================
# CANDLE HELPERS
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
        - max(
            candle["open"],
            candle["close"],
        )
    )


def lower_wick(candle):
    return (
        min(
            candle["open"],
            candle["close"],
        )
        - candle["low"]
    )


def is_bullish(candle):
    return (
        candle["close"]
        > candle["open"]
    )


def is_bearish(candle):
    return (
        candle["close"]
        < candle["open"]
    )


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_support_resistance(
    candles,
    lookback=50,
):
    if len(candles) < 10:
        return None, None

    recent = candles[
        -lookback:
    ]

    support = min(
        c["low"]
        for c in recent
    )

    resistance = max(
        c["high"]
        for c in recent
    )

    return support, resistance


# ============================================================
# PATTERN DETECTION
# ============================================================

def detect_bullish_engulfing(
    candles,
):
    if len(candles) < 2:
        return False

    prev = candles[-2]
    curr = candles[-1]

    if not (
        is_bearish(prev)
        and is_bullish(curr)
    ):
        return False

    return (
        curr["open"] <= prev["close"]
        and curr["close"] >= prev["open"]
        and candle_body(curr)
        >= candle_body(prev)
    )


def detect_bearish_engulfing(
    candles,
):
    if len(candles) < 2:
        return False

    prev = candles[-2]
    curr = candles[-1]

    if not (
        is_bullish(prev)
        and is_bearish(curr)
    ):
        return False

    return (
        curr["open"] >= prev["close"]
        and curr["close"] <= prev["open"]
        and candle_body(curr)
        >= candle_body(prev)
    )


def detect_hammer(candles):
    if len(candles) < 1:
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
        and upper <= max(
            body * 0.75,
            rng * 0.20,
        )
        and body / rng <= 0.45
    )


def detect_shooting_star(candles):
    if len(candles) < 1:
        return False

    c = candles[-1]

    body = candle_body(c)
    rng = candle_range(c)

    if rng <= 0:
        return False

    upper = upper_wick(c)
    lower = lower_wick(c)

    return (
        upper >= body * 2.0
        and lower <= max(
            body * 0.75,
            rng * 0.20,
        )
        and body / rng <= 0.45
    )


def detect_morning_star(candles):
    if len(candles) < 3:
        return False

    a = candles[-3]
    b = candles[-2]
    c = candles[-1]

    body_a = candle_body(a)
    body_b = candle_body(b)
    body_c = candle_body(c)

    if body_a <= 0:
        return False

    midpoint_a = (
        a["open"]
        + a["close"]
    ) / 2.0

    return (
        is_bearish(a)
        and body_b <= body_a * 0.50
        and is_bullish(c)
        and body_c >= body_a * 0.50
        and c["close"] > midpoint_a
    )


def detect_evening_star(candles):
    if len(candles) < 3:
        return False

    a = candles[-3]
    b = candles[-2]
    c = candles[-1]

    body_a = candle_body(a)
    body_b = candle_body(b)
    body_c = candle_body(c)

    if body_a <= 0:
        return False

    midpoint_a = (
        a["open"]
        + a["close"]
    ) / 2.0

    return (
        is_bullish(a)
        and body_b <= body_a * 0.50
        and is_bearish(c)
        and body_c >= body_a * 0.50
        and c["close"] < midpoint_a
    )


def detect_bullish_breakout(
    candles,
    lookback=20,
):
    if len(candles) < lookback + 1:
        return False

    current = candles[-1]

    previous = candles[
        -lookback - 1:-1
    ]

    resistance = max(
        c["high"]
        for c in previous
    )

    return (
        current["close"]
        > resistance
    )


def detect_bearish_breakout(
    candles,
    lookback=20,
):
    if len(candles) < lookback + 1:
        return False

    current = candles[-1]

    previous = candles[
        -lookback - 1:-1
    ]

    support = min(
        c["low"]
        for c in previous
    )

    return (
        current["close"]
        < support
    )


def detect_pullback(
    candles,
    ema20,
    ema50,
):
    if len(candles) < 5:
        return None

    if ema20 is None or ema50 is None:
        return None

    recent = candles[-5:]

    last = recent[-1]

    # Uptrend pullback
    if ema20 > ema50:

        touched = any(
            c["low"]
            <= ema20 * 1.002
            and c["high"]
            >= ema20 * 0.998
            for c in recent[:-1]
        )

        bullish_reaction = (
            is_bullish(last)
            and last["close"]
            > ema20
        )

        if (
            touched
            and bullish_reaction
        ):
            return "BUY"

    # Downtrend pullback
    if ema20 < ema50:

        touched = any(
            c["high"]
            >= ema20 * 0.998
            and c["low"]
            <= ema20 * 1.002
            for c in recent[:-1]
        )

        bearish_reaction = (
            is_bearish(last)
            and last["close"]
            < ema20
        )

        if (
            touched
            and bearish_reaction
        ):
            return "SELL"

    return None


def detect_double_bottom(
    candles,
):
    if len(candles) < 20:
        return False

    recent = candles[-20:]

    lows = [
        c["low"]
        for c in recent
    ]

    first_low_index = lows.index(
        min(lows[:10])
    )

    second_low_index = (
        10
        + lows[10:].index(
            min(lows[10:])
        )
    )

    first_low = lows[
        first_low_index
    ]

    second_low = lows[
        second_low_index
    ]

    tolerance = (
        max(
            first_low,
            second_low,
        )
        * 0.0015
    )

    if abs(
        first_low
        - second_low
    ) > tolerance:
        return False

    middle_high = max(
        c["high"]
        for c in recent[
            first_low_index:
            second_low_index + 1
        ]
    )

    return (
        candles[-1]["close"]
        > middle_high
    )


def detect_double_top(
    candles,
):
    if len(candles) < 20:
        return False

    recent = candles[-20:]

    highs = [
        c["high"]
        for c in recent
    ]

    first_high_index = highs.index(
        max(highs[:10])
    )

    second_high_index = (
        10
        + highs[10:].index(
            max(highs[10:])
        )
    )

    first_high = highs[
        first_high_index
    ]

    second_high = highs[
        second_high_index
    ]

    tolerance = (
        max(
            first_high,
            second_high,
        )
        * 0.0015
    )

    if abs(
        first_high
        - second_high
    ) > tolerance:
        return False

    middle_low = min(
        c["low"]
        for c in recent[
            first_high_index:
            second_high_index + 1
        ]
    )

    return (
        candles[-1]["close"]
        < middle_low
    )


# ============================================================
# PATTERN RECOGNITION ENGINE
# ============================================================

def detect_patterns(
    candles,
    ema20,
    ema50,
):
    patterns = []
    directional_patterns = []

    directions = []

    if detect_bullish_engulfing(candles):
        patterns.append(
            "Bullish Engulfing"
        )
        directional_patterns.append(
            "Bullish Engulfing"
        )
        directions.append("BUY")

    if detect_bearish_engulfing(candles):
        patterns.append(
            "Bearish Engulfing"
        )
        directional_patterns.append(
            "Bearish Engulfing"
        )
        directions.append("SELL")

    if detect_hammer(candles):
        patterns.append("Hammer")
        directional_patterns.append(
            "Hammer"
        )
        directions.append("BUY")

    if detect_shooting_star(candles):
        patterns.append(
            "Shooting Star"
        )
        directional_patterns.append(
            "Shooting Star"
        )
        directions.append("SELL")

    if detect_morning_star(candles):
        patterns.append(
            "Morning Star"
        )
        directional_patterns.append(
            "Morning Star"
        )
        directions.append("BUY")

    if detect_evening_star(candles):
        patterns.append(
            "Evening Star"
        )
        directional_patterns.append(
            "Evening Star"
        )
        directions.append("SELL")

    if detect_bullish_breakout(candles):
        patterns.append(
            "Bullish Breakout"
        )
        directional_patterns.append(
            "Bullish Breakout"
        )
        directions.append("BUY")

    if detect_bearish_breakout(candles):
        patterns.append(
            "Bearish Breakout"
        )
        directional_patterns.append(
            "Bearish Breakout"
        )
        directions.append("SELL")

    pullback = detect_pullback(
        candles,
        ema20,
        ema50,
    )

    if pullback == "BUY":

        patterns.append("Pullback")
        directional_patterns.append(
            "Pullback"
        )
        directions.append("BUY")

    elif pullback == "SELL":

        patterns.append("Pullback")
        directional_patterns.append(
            "Pullback"
        )
        directions.append("SELL")

    if detect_double_bottom(candles):

        patterns.append(
            "Double Bottom"
        )

        directional_patterns.append(
            "Double Bottom"
        )

        directions.append("BUY")

    if detect_double_top(candles):

        patterns.append(
            "Double Top"
        )

        directional_patterns.append(
            "Double Top"
        )

        directions.append("SELL")

    buy_count = directions.count("BUY")
    sell_count = directions.count("SELL")

    if buy_count > sell_count:
        candidate_direction = "BUY"

    elif sell_count > buy_count:
        candidate_direction = "SELL"

    else:
        candidate_direction = None

    return {
        "patterns": patterns,
        "directional_patterns":
            directional_patterns,
        "directions": directions,
        "candidate_direction":
            candidate_direction,
        "buy_pattern_count":
            buy_count,
        "sell_pattern_count":
            sell_count,
    }


# ============================================================
# MARKET ANALYSIS
# ============================================================

def analyze_market(
    candles,
):
    closes = [
        c["close"]
        for c in candles
    ]

    ema20_series = calculate_ema(
        closes,
        EMA_FAST,
    )

    ema50_series = calculate_ema(
        closes,
        EMA_SLOW,
    )

    rsi_series = calculate_rsi_series(
        closes,
        RSI_PERIOD,
    )

    atr_series = calculate_atr_series(
        candles,
        ATR_PERIOD,
    )

    ema20 = ema20_series[-1]
    ema50 = ema50_series[-1]
    rsi = rsi_series[-1]
    atr = atr_series[-1]

    if ema20 is None:
        ema20 = closes[-1]

    if ema50 is None:
        ema50 = closes[-1]

    if rsi is None:
        rsi = 50.0

    if atr is None:
        atr = 0.0

    current_close = closes[-1]

    previous_close = (
        closes[-2]
        if len(closes) >= 2
        else current_close
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if (
        ema20 > ema50
        and current_close > ema20
    ):

        trend = "UPTREND"

    elif (
        ema20 < ema50
        and current_close < ema20
    ):

        trend = "DOWNTREND"

    else:

        trend = "SIDEWAYS"

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum_change = (
        current_close
        - previous_close
    )

    if momentum_change > 0:
        momentum = "BULLISH"

    elif momentum_change < 0:
        momentum = "BEARISH"

    else:
        momentum = "NEUTRAL"

    support, resistance = (
        calculate_support_resistance(
            candles,
            50,
        )
    )

    patterns = detect_patterns(
        candles,
        ema20,
        ema50,
    )

    return {
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "atr": atr,
        "trend": trend,
        "momentum": momentum,
        "support": support,
        "resistance": resistance,
        "patterns": patterns,
    }


# ============================================================
# PATTERN WEIGHTS
# ============================================================

PATTERN_WEIGHTS = {
    "Bullish Engulfing": 18,
    "Bearish Engulfing": 18,
    "Hammer": 15,
    "Shooting Star": 15,
    "Morning Star": 20,
    "Evening Star": 20,
    "Bullish Breakout": 22,
    "Bearish Breakout": 22,
    "Pullback": 20,
    "Double Bottom": 20,
    "Double Top": 20,
}


# ============================================================
# CONFIRMATION
# ============================================================

def confirmation_analysis(
    candles,
    analysis,
):
    patterns_data = analysis["patterns"]

    candidate = (
        patterns_data[
            "candidate_direction"
        ]
    )

    patterns = (
        patterns_data["patterns"]
    )

    if candidate not in [
        "BUY",
        "SELL",
    ]:
        return {
            "valid": False,
            "candidate_direction":
                None,
            "score": 0.0,
            "reasons": [
                "No clear directional pattern"
            ],
            "checks": {},
        }

    score = 0.0

    reasons = []

    checks = {
        "pattern": False,
        "trend": False,
        "momentum": False,
        "rsi": False,
        "location": False,
        "volatility": False,
        "trigger": False,
    }

    # --------------------------------------------------------
    # PATTERN SCORE
    # --------------------------------------------------------

    directional_patterns = (
        patterns_data[
            "directional_patterns"
        ]
    )

    pattern_score = 0

    for pattern in directional_patterns:

        if (
            pattern
            in PATTERN_WEIGHTS
        ):
            pattern_score += (
                PATTERN_WEIGHTS[
                    pattern
                ]
            )

    pattern_score = min(
        pattern_score,
        30,
    )

    if pattern_score > 0:

        checks["pattern"] = True

        score += pattern_score

        reasons.append(
            f"{len(patterns)} pattern(s) detected"
        )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    trend = analysis["trend"]

    if candidate == "BUY":

        if trend == "UPTREND":

            checks["trend"] = True
            score += 20

            reasons.append(
                "Aligned with uptrend"
            )

        elif trend == "DOWNTREND":

            score -= 10

            reasons.append(
                "Against downtrend"
            )

        else:

            score += 5

            reasons.append(
                "Sideways market"
            )

    else:

        if trend == "DOWNTREND":

            checks["trend"] = True
            score += 20

            reasons.append(
                "Aligned with downtrend"
            )

        elif trend == "UPTREND":

            score -= 10

            reasons.append(
                "Against uptrend"
            )

        else:

            score += 5

            reasons.append(
                "Sideways market"
            )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum = analysis["momentum"]

    if (
        candidate == "BUY"
        and momentum == "BULLISH"
    ):

        checks["momentum"] = True
        score += 15

        reasons.append(
            "Bullish momentum confirmed"
        )

    elif (
        candidate == "SELL"
        and momentum == "BEARISH"
    ):

        checks["momentum"] = True
        score += 15

        reasons.append(
            "Bearish momentum confirmed"
        )

    else:

        score -= 5

        reasons.append(
            "Momentum not confirmed"
        )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi = analysis["rsi"]

    if candidate == "BUY":

        if (
            45 <= rsi <= 70
        ):

            checks["rsi"] = True
            score += 10

            reasons.append(
                "RSI supports BUY"
            )

        elif rsi < 30:

            checks["rsi"] = True
            score += 7

            reasons.append(
                "RSI oversold"
            )

        else:

            reasons.append(
                "RSI weak for BUY"
            )

    else:

        if (
            30 <= rsi <= 55
        ):

            checks["rsi"] = True
            score += 10

            reasons.append(
                "RSI supports SELL"
            )

        elif rsi > 70:

            checks["rsi"] = True
            score += 7

            reasons.append(
                "RSI overbought"
            )

        else:

            reasons.append(
                "RSI weak for SELL"
            )

    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    close = candles[-1]["close"]

    support = analysis["support"]
    resistance = analysis["resistance"]
    atr = analysis["atr"]

    if atr <= 0:
        atr = close * 0.001

    if candidate == "BUY":

        if (
            resistance
            and close >= resistance - atr * 0.5
        ):

            checks["location"] = True
            score += 10

            reasons.append(
                "Near resistance / breakout zone"
            )

        elif (
            support
            and close <= support + atr * 1.5
        ):

            checks["location"] = True
            score += 10

            reasons.append(
                "Near support"
            )

        else:

            score += 3

            reasons.append(
                "Neutral price location"
            )

    else:

        if (
            resistance
            and close >= resistance - atr * 1.5
        ):

            checks["location"] = True
            score += 10

            reasons.append(
                "Near resistance"
            )

        elif (
            support
            and close <= support + atr * 0.5
        ):

            checks["location"] = True
            score += 10

            reasons.append(
                "Near support / breakdown zone"
            )

        else:

            score += 3

            reasons.append(
                "Neutral price location"
            )

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    if atr >= MIN_ATR:

        checks["volatility"] = True
        score += 5

        reasons.append(
            "ATR sufficient"
        )

    else:

        reasons.append(
            "ATR too low"
        )

    # --------------------------------------------------------
    # TRIGGER
    # --------------------------------------------------------

    current = candles[-1]

    previous = (
        candles[-2]
        if len(candles) >= 2
        else current
    )

    if candidate == "BUY":

        bullish_trigger = (
            is_bullish(current)
            and current["close"]
            > previous["high"]
        )

        breakout = (
            resistance is not None
            and current["close"]
            > resistance
        )

        engulfing_trigger = (
            "Bullish Engulfing"
            in patterns
            or "Morning Star"
            in patterns
            or "Hammer"
            in patterns
        )

        if (
            bullish_trigger
            or breakout
            or engulfing_trigger
        ):

            checks["trigger"] = True
            score += 10

            reasons.append(
                "BUY entry trigger confirmed"
            )

        else:

            reasons.append(
                "Waiting for BUY trigger"
            )

    else:

        bearish_trigger = (
            is_bearish(current)
            and current["close"]
            < previous["low"]
        )

        breakdown = (
            support is not None
            and current["close"]
            < support
        )

        reversal_trigger = (
            "Bearish Engulfing"
            in patterns
            or "Evening Star"
            in patterns
            or "Shooting Star"
            in patterns
        )

        if (
            bearish_trigger
            or breakdown
            or reversal_trigger
        ):

            checks["trigger"] = True
            score += 10

            reasons.append(
                "SELL entry trigger confirmed"
            )

        else:

            reasons.append(
                "Waiting for SELL trigger"
            )

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    score = max(
        0.0,
        min(
            score,
            100.0,
        ),
    )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    mandatory = (
        checks["pattern"]
        and checks["volatility"]
        and checks["trigger"]
    )

    valid = (
        mandatory
        and score >= MIN_SCORE
    )

    return {
        "valid": valid,
        "candidate_direction":
            candidate,
        "score": round(
            score,
            2,
        ),
        "reasons": reasons,
        "checks": checks,
    }


# ============================================================
# ENTRY / TP / SL
# ============================================================

def calculate_trade_levels(
    candles,
    direction,
    atr,
    support,
    resistance,
):
    """
    Structure + ATR based trade levels.
    """

    entry = candles[-1]["close"]

    if atr <= 0:
        atr = entry * 0.001

    minimum_distance = max(
        atr,
        entry * 0.0005,
    )

    if direction == "BUY":

        structure_sl = None

        if support is not None:
            structure_sl = (
                support
                - atr * 0.20
            )

        atr_sl = (
            entry
            - minimum_distance
        )

        if structure_sl is not None:
            stop_loss = min(
                atr_sl,
                structure_sl,
            )
        else:
            stop_loss = atr_sl

        risk = (
            entry
            - stop_loss
        )

        if risk <= 0:
            risk = minimum_distance
            stop_loss = (
                entry - risk
            )

        take_profit = (
            entry
            + risk * MIN_RISK_REWARD
        )

    else:

        structure_sl = None

        if resistance is not None:
            structure_sl = (
                resistance
                + atr * 0.20
            )

        atr_sl = (
            entry
            + minimum_distance
        )

        if structure_sl is not None:
            stop_loss = max(
                atr_sl,
                structure_sl,
            )
        else:
            stop_loss = atr_sl

        risk = (
            stop_loss
            - entry
        )

        if risk <= 0:
            risk = minimum_distance
            stop_loss = (
                entry + risk
            )

        take_profit = (
            entry
            - risk * MIN_RISK_REWARD
        )

    risk_distance = abs(
        entry - stop_loss
    )

    reward_distance = abs(
        take_profit - entry
    )

    if risk_distance <= 0:
        risk_reward = 0.0
    else:
        risk_reward = (
            reward_distance
            / risk_distance
        )

    return {
        "entry": round_price(entry),
        "stop_loss":
            round_price(stop_loss),
        "take_profit":
            round_price(take_profit),
        "risk_distance":
            round(
                risk_distance,
                4,
            ),
        "reward_distance":
            round(
                reward_distance,
                4,
            ),
        "risk_reward":
            round(
                risk_reward,
                2,
            ),
    }


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(
    candles,
):
    latest = candles[-1]

    analysis = analyze_market(
        candles
    )

    patterns_data = analysis[
        "patterns"
    ]

    patterns = patterns_data[
        "patterns"
    ]

    candidate = patterns_data[
        "candidate_direction"
    ]

    confirmation = (
        confirmation_analysis(
            candles,
            analysis,
        )
    )

    # --------------------------------------------------------
    # NO PATTERN
    # --------------------------------------------------------

    if not patterns:

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
                "NO_PATTERN",
            "valid":
                False,
            "patterns": [],
            "directional_patterns": [],
            "candidate_direction":
                None,
            "score":
                0.0,
            "confidence":
                0.0,
            "confirmation":
                confirmation,
            "entry":
                None,
            "stop_loss":
                None,
            "take_profit":
                None,
            "risk_reward":
                0.0,
            "atr":
                round(
                    analysis["atr"],
                    4,
                ),
            "ema20":
                round(
                    analysis["ema20"],
                    2,
                ),
            "ema50":
                round(
                    analysis["ema50"],
                    2,
                ),
            "rsi":
                round(
                    analysis["rsi"],
                    2,
                ),
            "trend":
                analysis["trend"],
            "momentum":
                analysis["momentum"],
            "support":
                round_price(
                    analysis["support"]
                )
                if analysis["support"]
                else None,
            "resistance":
                round_price(
                    analysis["resistance"]
                )
                if analysis["resistance"]
                else None,
            "reasons":
                [
                    "No recognized pattern"
                ],
            "method":
                "Pattern Recognition + Confirmation + Entry",
            "data_source":
                "Twelve Data XAU/USD",
        }

    # --------------------------------------------------------
    # PATTERN FOUND BUT NOT CONFIRMED
    # --------------------------------------------------------

    if not confirmation["valid"]:

        return {
            "timestamp":
                latest["datetime"],
            "symbol":
                SYMBOL,
            "timeframe":
                "M5",
            "signal":
                "WAIT_CONFIRMATION",
            "status":
                "PATTERN_DETECTED",
            "valid":
                False,
            "patterns":
                patterns,
            "directional_patterns":
                patterns_data[
                    "directional_patterns"
                ],
            "candidate_direction":
                candidate,
            "score":
                confirmation["score"],
            "confidence":
                confirmation["score"],
            "confirmation":
                confirmation,
            "entry":
                None,
            "stop_loss":
                None,
            "take_profit":
                None,
            "risk_reward":
                0.0,
            "atr":
                round(
                    analysis["atr"],
                    4,
                ),
            "ema20":
                round(
                    analysis["ema20"],
                    2,
                ),
            "ema50":
                round(
                    analysis["ema50"],
                    2,
                ),
            "rsi":
                round(
                    analysis["rsi"],
                    2,
                ),
            "trend":
                analysis["trend"],
            "momentum":
                analysis["momentum"],
            "support":
                round_price(
                    analysis["support"]
                )
                if analysis["support"]
                else None,
            "resistance":
                round_price(
                    analysis["resistance"]
                )
                if analysis["resistance"]
                else None,
            "reasons":
                confirmation[
                    "reasons"
                ],
            "method":
                "Pattern Recognition + Confirmation + Entry",
            "data_source":
                "Twelve Data XAU/USD",
        }

    # --------------------------------------------------------
    # CALCULATE TRADE
    # --------------------------------------------------------

    levels = calculate_trade_levels(
        candles,
        candidate,
        analysis["atr"],
        analysis["support"],
        analysis["resistance"],
    )

    # --------------------------------------------------------
    # RISK REWARD CHECK
    # --------------------------------------------------------

    if (
        levels["risk_reward"]
        < MIN_RISK_REWARD
    ):

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
                "BAD_RISK_REWARD",
            "valid":
                False,
            "patterns":
                patterns,
            "directional_patterns":
                patterns_data[
                    "directional_patterns"
                ],
            "candidate_direction":
                candidate,
            "score":
                confirmation["score"],
            "confidence":
                confirmation["score"],
            "confirmation":
                confirmation,
            "entry":
                levels["entry"],
            "stop_loss":
                levels["stop_loss"],
            "take_profit":
                levels["take_profit"],
            "risk_reward":
                levels["risk_reward"],
            "atr":
                round(
                    analysis["atr"],
                    4,
                ),
            "ema20":
                round(
                    analysis["ema20"],
                    2,
                ),
            "ema50":
                round(
                    analysis["ema50"],
                    2,
                ),
            "rsi":
                round(
                    analysis["rsi"],
                    2,
                ),
            "trend":
                analysis["trend"],
            "momentum":
                analysis["momentum"],
            "support":
                round_price(
                    analysis["support"]
                )
                if analysis["support"]
                else None,
            "resistance":
                round_price(
                    analysis["resistance"]
                )
                if analysis["resistance"]
                else None,
            "reasons":
                confirmation[
                    "reasons"
                ]
                + [
                    "Risk/Reward below minimum"
                ],
            "method":
                "Pattern Recognition + Confirmation + Entry",
            "data_source":
                "Twelve Data XAU/USD",
        }

    # --------------------------------------------------------
    # FINAL SIGNAL
    # --------------------------------------------------------

    return {
        "timestamp":
            latest["datetime"],
        "symbol":
            SYMBOL,
        "timeframe":
            "M5",
        "signal":
            candidate,
        "status":
            "SIGNAL_CONFIRMED",
        "valid":
            True,
        "patterns":
            patterns,
        "directional_patterns":
            patterns_data[
                "directional_patterns"
            ],
        "candidate_direction":
            candidate,
        "score":
            confirmation["score"],
        "confidence":
            confirmation["score"],
        "confirmation":
            confirmation,
        "entry":
            levels["entry"],
        "stop_loss":
            levels["stop_loss"],
        "take_profit":
            levels["take_profit"],
        "risk_reward":
            levels["risk_reward"],
        "atr":
            round(
                analysis["atr"],
                4,
            ),
        "ema20":
            round(
                analysis["ema20"],
                2,
            ),
        "ema50":
            round(
                analysis["ema50"],
                2,
            ),
        "rsi":
            round(
                analysis["rsi"],
                2,
            ),
        "trend":
            analysis["trend"],
        "momentum":
            analysis["momentum"],
        "support":
            round_price(
                analysis["support"]
            )
            if analysis["support"]
            else None,
        "resistance":
            round_price(
                analysis["resistance"]
            )
            if analysis["resistance"]
            else None,
        "reasons":
            confirmation[
                "reasons"
            ],
        "method":
            "Pattern Recognition + Confirmation + Entry",
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
            "TELEGRAM_BOT_TOKEN is not configured",
        )

    if not TELEGRAM_CHAT_ID:
        return (
            False,
            "TELEGRAM_CHAT_ID is not configured",
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
            timeout=20,
        )

        response.raise_for_status()

        result = response.json()

        if not result.get(
            "ok",
            False,
        ):

            return (
                False,
                result.get(
                    "description",
                    "Telegram API error",
                ),
            )

        return (
            True,
            None,
        )

    except Exception as exc:

        return (
            False,
            str(exc),
        )


# ============================================================
# TELEGRAM STARTUP
# ============================================================

def send_startup_notification():
    """
    Send startup message once per running worker.
    """

    if STATE["startup_sent"]:
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
        "<b>System:</b>\n"
        "Pattern Recognition\n"
        "→ Confirmation\n"
        "→ Entry\n"
        "→ TP / SL\n"
        "\n"
        "<b>Patterns:</b> 11\n"
        "<b>Minimum Score:</b> "
        f"{MIN_SCORE:.0f}\n"
        "<b>Minimum RR:</b> "
        f"{MIN_RISK_REWARD:.2f}\n"
        "\n"
        "พร้อมวิเคราะห์ตลาดและส่งสัญญาณ"
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        STATE["startup_sent"] = True

        print(
            "Telegram startup notification "
            "sent successfully"
        )

        return True

    print(
        "Telegram startup notification failed:",
        error,
    )

    return False


# ============================================================
# TELEGRAM SIGNAL FORMAT
# ============================================================

def format_signal_message(
    signal,
):
    direction = signal["signal"]

    if direction == "BUY":
        emoji = "🟢"

    elif direction == "SELL":
        emoji = "🔴"

    else:
        return None

    patterns = ", ".join(
        signal["patterns"]
    )

    checks = signal[
        "confirmation"
    ]["checks"]

    return (
        f"{emoji} <b>XAUUSD M5 "
        f"{direction} SIGNAL</b>\n"
        "\n"
        f"<b>Pattern:</b> "
        f"{patterns}\n"
        f"<b>Direction:</b> "
        f"{direction}\n"
        "\n"
        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"
        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"
        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"
        f"<b>RR:</b> "
        f"1:{signal['risk_reward']:.2f}\n"
        "\n"
        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"
        f"<b>RSI:</b> "
        f"{signal['rsi']:.2f}\n"
        f"<b>Trend:</b> "
        f"{signal['trend']}\n"
        f"<b>Momentum:</b> "
        f"{signal['momentum']}\n"
        "\n"
        "<b>Confirmation</b>\n"
        f"{'✅' if checks['pattern'] else '❌'} Pattern\n"
        f"{'✅' if checks['trend'] else '❌'} Trend\n"
        f"{'✅' if checks['momentum'] else '❌'} Momentum\n"
        f"{'✅' if checks['rsi'] else '❌'} RSI\n"
        f"{'✅' if checks['location'] else '❌'} Location\n"
        f"{'✅' if checks['volatility'] else '❌'} ATR\n"
        f"{'✅' if checks['trigger'] else '❌'} Entry Trigger\n"
        "\n"
        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"
        "\n"
        "<i>Pattern Recognition System</i>"
    )


# ============================================================
# TELEGRAM WAIT MESSAGE
# ============================================================

def format_wait_message(
    signal,
):
    if signal["signal"] != "WAIT_CONFIRMATION":
        return None

    patterns = ", ".join(
        signal["patterns"]
    )

    return (
        "⚠️ <b>XAUUSD M5 "
        "PATTERN DETECTED</b>\n"
        "\n"
        f"<b>Pattern:</b> "
        f"{patterns}\n"
        f"<b>Candidate:</b> "
        f"{signal['candidate_direction']}\n"
        "\n"
        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"
        f"<b>Trend:</b> "
        f"{signal['trend']}\n"
        f"<b>Momentum:</b> "
        f"{signal['momentum']}\n"
        f"<b>RSI:</b> "
        f"{signal['rsi']:.2f}\n"
        "\n"
        "<b>STATUS:</b> "
        "WAIT CONFIRMATION\n"
        "\n"
        "ระบบยังไม่ส่ง Entry "
        "เพราะเงื่อนไขยังไม่ครบ"
    )


# ============================================================
# RUN SIGNAL
# ============================================================

def run_signal(
    send_notification=True,
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
    # TELEGRAM
    # --------------------------------------------------------

    if send_notification:

        direction = signal[
            "signal"
        ]

        if direction in [
            "BUY",
            "SELL",
        ]:

            signal_key = (
                str(
                    signal["timestamp"]
                )
                + "_"
                + direction
                + "_"
                + "_".join(
                    signal["patterns"]
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

                STATE[
                    "last_signal_key"
                ] = signal_key

        # WAIT_CONFIRMATION
        #
        # ไม่ส่งซ้ำทุก request
        # ส่งเฉพาะเมื่อสถานะ Pattern เปลี่ยน

        elif (
            direction
            == "WAIT_CONFIRMATION"
        ):

            wait_key = (
                str(
                    signal["timestamp"]
                )
                + "_WAIT_"
                + "_".join(
                    signal["patterns"]
                )
                + "_"
                + str(
                    signal[
                        "candidate_direction"
                    ]
                )
            )

            if (
                STATE[
                    "last_signal_key"
                ]
                != wait_key
            ):

                message = (
                    format_wait_message(
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
                ] = wait_key

    STATE["last_signal"] = signal

    return signal


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    # Ensure startup notification
    # is attempted when service receives
    # first request.
    send_startup_notification()

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
            "M5",

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "patterns":
            PATTERN_NAMES,

        "architecture":
            [
                "Pattern Recognition",
                "Confirmation",
                "Entry",
                "TP/SL",
                "Telegram",
            ],

        "rules":
            {
                "minimum_score":
                    MIN_SCORE,

                "minimum_risk_reward":
                    MIN_RISK_REWARD,

                "minimum_atr":
                    MIN_ATR,

                "forward_bars":
                    FORWARD_BARS,
            },

        "endpoints":
            [
                "/",
                "/health",
                "/signal",
                "/backtest",
                "/test-data",
                "/test-telegram",
            ],
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
            "XAUUSD M5 Pattern Recognition Bot",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "data_source":
            "Twelve Data",

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "twelve_data":
            bool(
                TWELVE_DATA_API_KEY
            ),

        "startup_sent":
            STATE["startup_sent"],

        "started_at":
            STATE["started_at"],

        "last_update":
            STATE["last_update"],

        "last_signal":
            STATE["last_signal"],

        "last_error":
            STATE["last_error"],
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

        return jsonify(signal)

    except Exception as exc:

        STATE["last_error"] = str(
            exc
        )

        print(
            traceback.format_exc()
        )

        return jsonify({

            "status":
                "error",

            "signal":
                "ERROR",

            "error":
                str(exc),

        }), 500


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

        return jsonify({

            "status":
                "error",

            "message":
                str(exc),

        }), 500


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (
        "🟢 <b>TELEGRAM TEST</b>\n"
        "\n"
        "XAUUSD M5 Pattern Recognition Bot\n"
        "\n"
        "Telegram connection is working.\n"
        "\n"
        "Pattern → Confirmation → "
        "Entry → TP/SL"
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
                True,

        })

    return jsonify({

        "status":
            "error",

        "message":
            error,

        "telegram":
            False,

    }), 500


# ============================================================
# BACKTEST
# ============================================================

@app.route("/backtest")
def backtest():

    try:

        candles = get_candles()

        total = len(candles)

        # ----------------------------------------------------
        # Start after enough indicator data
        # ----------------------------------------------------

        start = max(
            EMA_SLOW + 20,
            RSI_PERIOD + 20,
            ATR_PERIOD + 20,
            80,
        )

        end = total - FORWARD_BARS - 1

        if end <= start:

            return jsonify({

                "status":
                    "error",

                "error":
                    "Not enough candles",

            }), 400

        # Keep runtime reasonable
        max_points = min(
            200,
            end - start,
        )

        start = (
            end
            - max_points
        )

        signals = 0
        wins = 0
        losses = 0
        timeouts = 0

        buy_signals = 0
        sell_signals = 0

        total_profit = 0.0
        total_loss = 0.0

        trade_results = []

        score_values = []

        rr_values = []

        pattern_counts = {}

        # ----------------------------------------------------
        # Walk forward
        # ----------------------------------------------------

        for i in range(
            start,
            end,
        ):

            historical = (
                candles[: i + 1]
            )

            try:

                signal = generate_signal(
                    historical
                )

            except Exception:

                continue

            direction = signal.get(
                "signal"
            )

            if direction not in [
                "BUY",
                "SELL",
            ]:
                continue

            if not signal.get(
                "valid",
                False,
            ):
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

            score_values.append(
                signal["score"]
            )

            rr_values.append(
                signal["risk_reward"]
            )

            for pattern in signal[
                "patterns"
            ]:

                pattern_counts[
                    pattern
                ] = (
                    pattern_counts.get(
                        pattern,
                        0,
                    )
                    + 1
                )

            result = "TIMEOUT"

            exit_price = None
            exit_index = None

            mfe = 0.0
            mae = 0.0

            # ------------------------------------------------
            # Future candles
            # ------------------------------------------------

            for j in range(
                i + 1,
                min(
                    i
                    + 1
                    + FORWARD_BARS,
                    total,
                ),
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
                        high - entry
                    ) / entry * 100.0

                    adverse = (
                        entry - low
                    ) / entry * 100.0

                    mfe = max(
                        mfe,
                        favorable,
                    )

                    mae = max(
                        mae,
                        adverse,
                    )

                    hit_sl = (
                        low
                        <= stop_loss
                    )

                    hit_tp = (
                        high
                        >= take_profit
                    )

                    # Conservative:
                    # If both occur inside
                    # one candle, SL first.
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
                        favorable,
                    )

                    mae = max(
                        mae,
                        adverse,
                    )

                    hit_sl = (
                        high
                        >= stop_loss
                    )

                    hit_tp = (
                        low
                        <= take_profit
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

            # ------------------------------------------------
            # Timeout
            # ------------------------------------------------

            if result == "TIMEOUT":

                exit_index = min(
                    i
                    + FORWARD_BARS,
                    total - 1,
                )

                exit_price = candles[
                    exit_index
                ]["close"]

            # ------------------------------------------------
            # PNL
            # ------------------------------------------------

            if direction == "BUY":

                pnl = (
                    exit_price - entry
                ) / entry * 100.0

            else:

                pnl = (
                    entry - exit_price
                ) / entry * 100.0

            if result == "WIN":

                wins += 1

                total_profit += max(
                    pnl,
                    0,
                )

            elif result == "LOSS":

                losses += 1

                total_loss += abs(
                    min(
                        pnl,
                        0,
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

                "patterns":
                    signal[
                        "patterns"
                    ],

                "score":
                    round(
                        signal["score"],
                        2,
                    ),

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

                "risk_reward":
                    signal[
                        "risk_reward"
                    ],

                "result":
                    result,

                "exit_price":
                    round_price(
                        exit_price
                    ),

                "pnl_percent":
                    round(
                        pnl,
                        4,
                    ),

                "mfe_percent":
                    round(
                        mfe,
                        4,
                    ),

                "mae_percent":
                    round(
                        mae,
                        4,
                    ),

                "bars_held":
                    (
                        exit_index - i
                        if exit_index
                        is not None
                        else None
                    ),
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

        net_profit = (
            total_profit
            - total_loss
        )

        expectancy = (
            net_profit / signals
            if signals > 0
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
        # DRAWDOWN
        # ====================================================

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for trade in trade_results:

            equity += trade[
                "pnl_percent"
            ]

            peak = max(
                peak,
                equity,
            )

            drawdown = (
                peak - equity
            )

            max_drawdown = max(
                max_drawdown,
                drawdown,
            )

        # ====================================================
        # AVERAGES
        # ====================================================

        average_score = (
            sum(score_values)
            / len(score_values)
            if score_values
            else 0.0
        )

        average_rr = (
            sum(rr_values)
            / len(rr_values)
            if rr_values
            else 0.0
        )

        average_mfe = (
            sum(
                x["mfe_percent"]
                for x in trade_results
            )
            / len(trade_results)
            if trade_results
            else 0.0
        )

        average_mae = (
            sum(
                x["mae_percent"]
                for x in trade_results
            )
            / len(trade_results)
            if trade_results
            else 0.0
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "status":
                "completed",

            "system":
                "Pattern Recognition",

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "data_source":
                "Twelve Data XAU/USD",

            "candles_available":
                total,

            "test_points":
                max_points,

            "rules": {

                "minimum_score":
                    MIN_SCORE,

                "minimum_risk_reward":
                    MIN_RISK_REWARD,

                "minimum_atr":
                    MIN_ATR,

                "forward_bars":
                    FORWARD_BARS,
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
            },

            "performance": {

                "win_rate_percent":
                    round(
                        win_rate,
                        2,
                    ),

                "loss_rate_percent":
                    round(
                        loss_rate,
                        2,
                    ),

                "timeout_rate_percent":
                    round(
                        timeout_rate,
                        2,
                    ),

                "total_profit_percent":
                    round(
                        total_profit,
                        4,
                    ),

                "total_loss_percent":
                    round(
                        total_loss,
                        4,
                    ),

                "net_profit_percent":
                    round(
                        net_profit,
                        4,
                    ),

                "profit_factor":
                    (
                        round(
                            profit_factor,
                            4,
                        )
                        if math.isfinite(
                            profit_factor
                        )
                        else "infinite"
                    ),

                "expectancy_percent":
                    round(
                        expectancy,
                        4,
                    ),

                "max_drawdown_percent":
                    round(
                        max_drawdown,
                        4,
                    ),

                "average_mfe_percent":
                    round(
                        average_mfe,
                        4,
                    ),

                "average_mae_percent":
                    round(
                        average_mae,
                        4,
                    ),

                "average_score":
                    round(
                        average_score,
                        2,
                    ),

                "average_risk_reward":
                    round(
                        average_rr,
                        2,
                    ),
            },

            "pattern_frequency":
                pattern_counts,

            "recent_trades":
                trade_results[-20:],

            "warning":
                "Historical simulation only. "
                "Spread, slippage, execution delay "
                "and broker-specific pricing are "
                "not included.",
        })

    except Exception as exc:

        print(
            traceback.format_exc()
        )

        return jsonify({

            "status":
                "error",

            "error":
                str(exc),

        }), 500


# ============================================================
# STARTUP
# ============================================================

def initialize_application():

    STATE["started_at"] = (
        utc_now().isoformat()
    )

    print("=" * 60)
    print(
        "XAUUSD M5 PATTERN RECOGNITION BOT"
    )
    print("=" * 60)

    print(
        "System: Pattern Recognition"
    )

    print(
        "Pipeline:"
    )

    print(
        "Pattern → Confirmation → "
        "Entry → TP/SL → Telegram"
    )

    print(
        "Twelve Data:",
        bool(
            TWELVE_DATA_API_KEY
        ),
    )

    print(
        "Telegram:",
        bool(
            TELEGRAM_BOT_TOKEN
            and TELEGRAM_CHAT_ID
        ),
    )

    print("=" * 60)

    # Important:
    # This is executed when the worker starts.
    # It is intentionally attempted here so the
    # Telegram welcome message does not depend
    # exclusively on /signal being called.

    send_startup_notification()


# ============================================================
# MAIN
# ============================================================

# Gunicorn imports app.py.
# This executes startup initialization.
initialize_application()


if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
    )

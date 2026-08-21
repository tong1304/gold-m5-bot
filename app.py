import os
import math
import html
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request


# ============================================================
# APP
# ============================================================

app = Flask(__name__)


# ============================================================
# ENVIRONMENT
# ============================================================

TWELVE_DATA_API_KEY = os.getenv(
    "TWELVE_DATA_API_KEY",
    "",
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()


# ============================================================
# CONFIG
# ============================================================

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"

CANDLE_LIMIT = 1000


# ============================================================
# INDICATORS
# ============================================================

EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14
ATR_PERIOD = 14


# ============================================================
# SIGNAL QUALITY
# ============================================================

MIN_ATR = 0.50

MIN_SCORE = 70.0

MIN_PATTERN_QUALITY = 55.0

MIN_TRIGGER_QUALITY = 55.0


# ============================================================
# RISK
# ============================================================

MIN_RISK_REWARD = 1.30
RISK_REWARD = 1.50

MIN_STOP_ATR = 1.00
MAX_STOP_ATR = 3.00

STRUCTURE_BUFFER_ATR = 0.15


# ============================================================
# BACKTEST
# ============================================================

BACKTEST_POINTS = 200

# Maximum trade duration:
# 24 x M5 = 2 hours
FORWARD_BARS = 24


# ============================================================
# STRUCTURE
# ============================================================

SUPPORT_LOOKBACK = 30
RESISTANCE_LOOKBACK = 30

TRIGGER_LOOKBACK = 3

BREAKOUT_LOOKBACK = 20


# ============================================================
# REALISTIC EXECUTION
# ============================================================

# XAUUSD assumed spread in price units.
# Adjust to your broker if needed.
BACKTEST_SPREAD = 0.20

# Slippage in price units.
BACKTEST_SLIPPAGE = 0.05


# ============================================================
# TRADE MANAGEMENT
# ============================================================

ENABLE_BREAK_EVEN = True

BREAK_EVEN_R = 1.0

ENABLE_TRAILING = False

TRAILING_ATR = 1.5


# ============================================================
# PATTERNS
# ============================================================

PATTERNS = [
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


BULLISH_PATTERNS = {
    "Bullish Engulfing",
    "Hammer",
    "Morning Star",
    "Bullish Breakout",
    "Double Bottom",
    "Pullback",
}


BEARISH_PATTERNS = {
    "Bearish Engulfing",
    "Shooting Star",
    "Evening Star",
    "Bearish Breakout",
    "Double Top",
    "Pullback",
}


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_error": None,

    "startup_sent": False,

    "last_signal_key": None,

    "last_signal_sent_at": None,

    "pending_setup": None,
}

STARTUP_LOCK = threading.Lock()

SIGNAL_LOCK = threading.Lock()


# ============================================================
# TIME
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def now_iso():
    return utc_now().isoformat()


# ============================================================
# NUMBER HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def round_price(value):
    return round(safe_float(value), 2)


def clamp(value, low, high):
    return max(low, min(high, value))


# ============================================================
# CANDLE HELPERS
# ============================================================

def candle_range(candle):
    return max(
        candle["high"] - candle["low"],
        0.000001,
    )


def candle_body(candle):
    return abs(
        candle["close"] - candle["open"]
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
    return candle["close"] > candle["open"]


def is_bearish(candle):
    return candle["close"] < candle["open"]


# ============================================================
# TWELVE DATA
# ============================================================

def get_candles():

    if not TWELVE_DATA_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY is not configured"
        )

    url = (
        "https://api.twelvedata.com/time_series"
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
            "No candle data received from Twelve Data"
        )

    candles = []

    for item in values:

        try:

            candles.append(
                {
                    "datetime": item["datetime"],
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                }
            )

        except Exception:
            continue

    # Twelve Data returns newest first.
    # Convert to oldest -> newest.
    candles.reverse()

    if len(candles) < 100:
        raise RuntimeError(
            "Not enough candles"
        )

    return candles


# ============================================================
# EMA
# ============================================================

def calculate_ema(values, period):

    if not values:
        return 0.0

    if len(values) < period:
        return sum(values) / len(values)

    multiplier = 2.0 / (
        period + 1.0
    )

    ema = (
        sum(values[:period])
        / period
    )

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
    period=14,
):

    if len(candles) <= period:
        return 50.0

    closes = [
        c["close"]
        for c in candles
    ]

    gains = []
    losses = []

    for i in range(1, len(closes)):

        change = (
            closes[i]
            - closes[i - 1]
        )

        if change > 0:

            gains.append(change)
            losses.append(0.0)

        else:

            gains.append(0.0)
            losses.append(
                abs(change)
            )

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

        if avg_gain > 0:
            return 100.0

        return 50.0

    rs = avg_gain / avg_loss

    return (
        100.0
        - (
            100.0
            / (1.0 + rs)
        )
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=14,
):

    if len(candles) <= period:
        return 0.0

    true_ranges = []

    for i in range(1, len(candles)):

        current = candles[i]
        previous = candles[i - 1]

        tr1 = (
            current["high"]
            - current["low"]
        )

        tr2 = abs(
            current["high"]
            - previous["close"]
        )

        tr3 = abs(
            current["low"]
            - previous["close"]
        )

        true_ranges.append(
            max(
                tr1,
                tr2,
                tr3,
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
# SUPPORT
# ============================================================

def calculate_support(candles):

    window = candles[
        -SUPPORT_LOOKBACK:
    ]

    if not window:
        return 0.0

    return min(
        c["low"]
        for c in window
    )


# ============================================================
# RESISTANCE
# ============================================================

def calculate_resistance(candles):

    window = candles[
        -RESISTANCE_LOOKBACK:
    ]

    if not window:
        return 0.0

    return max(
        c["high"]
        for c in window
    )


# ============================================================
# TREND
# ============================================================

def get_trend(
    ema20,
    ema50,
    close,
):

    if (
        close > ema20
        and ema20 > ema50
    ):
        return "UPTREND"

    if (
        close < ema20
        and ema20 < ema50
    ):
        return "DOWNTREND"

    return "SIDEWAYS"


# ============================================================
# MOMENTUM
# ============================================================

def calculate_momentum_strength(
    candles,
    atr,
):

    if len(candles) < 6:
        return {
            "direction": "NEUTRAL",
            "strength": 0.0,
        }

    current = candles[-1]
    previous = candles[-4]

    move = (
        current["close"]
        - previous["close"]
    )

    if atr <= 0:
        return {
            "direction": "NEUTRAL",
            "strength": 0.0,
        }

    strength = abs(move) / atr

    strength_score = clamp(
        strength * 35.0,
        0.0,
        100.0,
    )

    if move > 0:

        direction = "BULLISH"

    elif move < 0:

        direction = "BEARISH"

    else:

        direction = "NEUTRAL"

    return {
        "direction": direction,
        "strength": round(
            strength_score,
            2,
        ),
    }


# ============================================================
# PATTERN DETECTION
# ============================================================

def detect_engulfing(candles):

    patterns = []

    if len(candles) < 2:
        return patterns

    a = candles[-2]
    b = candles[-1]

    if (
        is_bearish(a)
        and is_bullish(b)
        and b["open"] <= a["close"]
        and b["close"] >= a["open"]
        and candle_body(b)
        > candle_body(a)
    ):

        patterns.append(
            "Bullish Engulfing"
        )

    if (
        is_bullish(a)
        and is_bearish(b)
        and b["open"] >= a["close"]
        and b["close"] <= a["open"]
        and candle_body(b)
        > candle_body(a)
    ):

        patterns.append(
            "Bearish Engulfing"
        )

    return patterns


def detect_hammer(candles):

    patterns = []

    if not candles:
        return patterns

    c = candles[-1]

    body = candle_body(c)

    rng = candle_range(c)

    effective_body = (
        body
        if body > 0
        else rng * 0.05
    )

    lower = lower_wick(c)
    upper = upper_wick(c)

    if (
        lower >= effective_body * 2.0
        and upper <= effective_body
        and body / rng <= 0.45
    ):

        patterns.append(
            "Hammer"
        )

    return patterns


def detect_shooting_star(candles):

    patterns = []

    if not candles:
        return patterns

    c = candles[-1]

    body = candle_body(c)

    rng = candle_range(c)

    effective_body = (
        body
        if body > 0
        else rng * 0.05
    )

    upper = upper_wick(c)
    lower = lower_wick(c)

    if (
        upper >= effective_body * 2.0
        and lower <= effective_body
        and body / rng <= 0.45
    ):

        patterns.append(
            "Shooting Star"
        )

    return patterns


def detect_stars(candles):

    patterns = []

    if len(candles) < 3:
        return patterns

    a = candles[-3]
    b = candles[-2]
    c = candles[-1]

    a_body = candle_body(a)
    b_body = candle_body(b)

    if (
        is_bearish(a)
        and b_body <= a_body * 0.55
        and is_bullish(c)
        and c["close"]
        > (
            a["open"]
            + a["close"]
        ) / 2.0
    ):

        patterns.append(
            "Morning Star"
        )

    if (
        is_bullish(a)
        and b_body <= a_body * 0.55
        and is_bearish(c)
        and c["close"]
        < (
            a["open"]
            + a["close"]
        ) / 2.0
    ):

        patterns.append(
            "Evening Star"
        )

    return patterns


def detect_breakout(candles):

    patterns = []

    if len(candles) < (
        BREAKOUT_LOOKBACK + 1
    ):
        return patterns

    current = candles[-1]

    previous = candles[
        -(
            BREAKOUT_LOOKBACK + 1
        ):-1
    ]

    previous_high = max(
        c["high"]
        for c in previous
    )

    previous_low = min(
        c["low"]
        for c in previous
    )

    if current["close"] > previous_high:

        patterns.append(
            "Bullish Breakout"
        )

    if current["close"] < previous_low:

        patterns.append(
            "Bearish Breakout"
        )

    return patterns


def detect_pullback(
    candles,
    ema20,
    ema50,
    atr,
):

    patterns = []

    if len(candles) < 7:
        return patterns

    if atr <= 0:
        return patterns

    current = candles[-1]

    recent = candles[-6:-1]

    distance_to_ema = abs(
        current["close"]
        - ema20
    )

    near_ema = (
        distance_to_ema
        <= atr * 0.35
    )

    if not near_ema:
        return patterns

    if (
        ema20 > ema50
        and any(
            is_bearish(c)
            for c in recent
        )
        and is_bullish(current)
    ):

        patterns.append(
            "Pullback"
        )

    elif (
        ema20 < ema50
        and any(
            is_bullish(c)
            for c in recent
        )
        and is_bearish(current)
    ):

        patterns.append(
            "Pullback"
        )

    return patterns


def detect_double_patterns(candles):

    patterns = []

    if len(candles) < 20:
        return patterns

    window = candles[-20:]

    lows_1 = [
        c["low"]
        for c in window[:10]
    ]

    lows_2 = [
        c["low"]
        for c in window[10:]
    ]

    highs_1 = [
        c["high"]
        for c in window[:10]
    ]

    highs_2 = [
        c["high"]
        for c in window[10:]
    ]

    first_low = min(lows_1)
    second_low = min(lows_2)

    first_high = max(highs_1)
    second_high = max(highs_2)

    price = candles[-1]["close"]

    if price <= 0:
        return patterns

    low_difference = (
        abs(
            first_low
            - second_low
        )
        / price
    )

    high_difference = (
        abs(
            first_high
            - second_high
        )
        / price
    )

    if (
        low_difference <= 0.0015
        and price > second_low
    ):

        patterns.append(
            "Double Bottom"
        )

    if (
        high_difference <= 0.0015
        and price < second_high
    ):

        patterns.append(
            "Double Top"
        )

    return patterns


# ============================================================
# DETECT PATTERNS
# ============================================================

def detect_patterns(candles):

    closes = [
        c["close"]
        for c in candles
    ]

    ema20 = calculate_ema(
        closes,
        EMA_FAST,
    )

    ema50 = calculate_ema(
        closes,
        EMA_SLOW,
    )

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    patterns = []

    patterns.extend(
        detect_engulfing(
            candles
        )
    )

    patterns.extend(
        detect_hammer(
            candles
        )
    )

    patterns.extend(
        detect_shooting_star(
            candles
        )
    )

    patterns.extend(
        detect_stars(
            candles
        )
    )

    patterns.extend(
        detect_breakout(
            candles
        )
    )

    patterns.extend(
        detect_pullback(
            candles,
            ema20,
            ema50,
            atr,
        )
    )

    patterns.extend(
        detect_double_patterns(
            candles
        )
    )

    unique = []

    for pattern in patterns:

        if pattern not in unique:
            unique.append(pattern)

    return unique


# ============================================================
# DIRECTIONAL FILTER
# ============================================================

def directional_filter(patterns):

    bullish = [
        p
        for p in patterns
        if p in BULLISH_PATTERNS
    ]

    bearish = [
        p
        for p in patterns
        if p in BEARISH_PATTERNS
    ]

    # Pullback requires contextual direction.
    # It is not counted as both directions.
    if "Pullback" in patterns:

        bullish_count = len(
            [
                p
                for p in bullish
                if p != "Pullback"
            ]
        )

        bearish_count = len(
            [
                p
                for p in bearish
                if p != "Pullback"
            ]
        )

        if bullish_count > bearish_count:

            bullish = [
                p
                for p in bullish
                if p != "Pullback"
            ]

            bullish.append(
                "Pullback"
            )

        elif bearish_count > bullish_count:

            bearish = [
                p
                for p in bearish
                if p != "Pullback"
            ]

            bearish.append(
                "Pullback"
            )

    bull_count = len(bullish)
    bear_count = len(bearish)

    if (
        bull_count == 0
        and bear_count == 0
    ):

        return {
            "direction": None,
            "bullish": bullish,
            "bearish": bearish,
            "conflict": False,
            "strength": 0.0,
        }

    if (
        bull_count > 0
        and bear_count > 0
    ):

        return {
            "direction": None,
            "bullish": bullish,
            "bearish": bearish,
            "conflict": True,
            "strength": 0.0,
        }

    if bull_count > 0:

        return {
            "direction": "BUY",
            "bullish": bullish,
            "bearish": bearish,
            "conflict": False,
            "strength": round(
                min(
                    100.0,
                    50.0
                    + bull_count * 15.0,
                ),
                2,
            ),
        }

    return {
        "direction": "SELL",
        "bullish": bullish,
        "bearish": bearish,
        "conflict": False,
        "strength": round(
            min(
                100.0,
                50.0
                + bear_count * 15.0,
            ),
            2,
        ),
    }


# ============================================================
# PATTERN QUALITY
# ============================================================

def pattern_quality(
    candles,
    patterns,
    direction,
):

    if not patterns or not direction:

        return {
            "score": 0.0,
            "quality": "FAIL",
            "reasons": [
                "No valid directional pattern"
            ],
        }

    current = candles[-1]

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    if atr <= 0:

        return {
            "score": 0.0,
            "quality": "FAIL",
            "reasons": [
                "ATR unavailable"
            ],
        }

    directional = (
        directional_filter(
            patterns
        )
    )

    relevant = (
        directional["bullish"]
        if direction == "BUY"
        else directional["bearish"]
    )

    opposite = (
        directional["bearish"]
        if direction == "BUY"
        else directional["bullish"]
    )

    if not relevant:

        return {
            "score": 0.0,
            "quality": "FAIL",
            "reasons": [
                "No relevant pattern"
            ],
        }

    score = 40.0

    reasons = []

    # Number of agreeing patterns
    score += min(
        20.0,
        len(relevant) * 8.0,
    )

    # Candle body quality
    body_ratio = (
        candle_body(current)
        / candle_range(current)
    )

    if body_ratio >= 0.60:

        score += 15.0

        reasons.append(
            "Strong candle body"
        )

    elif body_ratio >= 0.35:

        score += 8.0

        reasons.append(
            "Moderate candle body"
        )

    else:

        reasons.append(
            "Weak candle body"
        )

    # Directional candle
    if (
        direction == "BUY"
        and is_bullish(current)
    ):

        score += 10.0

    elif (
        direction == "SELL"
        and is_bearish(current)
    ):

        score += 10.0

    else:

        score -= 10.0

        reasons.append(
            "Pattern candle direction weak"
        )

    # Pattern conflict
    if opposite:

        score -= 30.0

        reasons.append(
            "Opposite pattern conflict"
        )

    else:

        reasons.append(
            "No opposite pattern"
        )

    score = clamp(
        score,
        0.0,
        100.0,
    )

    if score >= 80:

        quality = "A"

    elif score >= 70:

        quality = "B"

    elif score >= 55:

        quality = "C"

    else:

        quality = "FAIL"

    return {
        "score": round(
            score,
            2,
        ),

        "quality": quality,

        "relevant": relevant,

        "opposite": opposite,

        "body_ratio": round(
            body_ratio,
            3,
        ),

        "reasons": reasons,
    }


# ============================================================
# MARKET REGIME
# ============================================================

def market_regime(candles):

    closes = [
        c["close"]
        for c in candles
    ]

    ema20 = calculate_ema(
        closes,
        EMA_FAST,
    )

    ema50 = calculate_ema(
        closes,
        EMA_SLOW,
    )

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    if atr <= 0:

        return {
            "regime": "UNKNOWN",
            "score": 0.0,
            "trend_strength": 0.0,
            "atr_ratio": 0.0,
        }

    close = closes[-1]

    trend_distance = abs(
        ema20 - ema50
    )

    trend_strength = (
        trend_distance / atr
    )

    # ATR relative to recent price movement
    recent_ranges = [
        candle_range(c)
        for c in candles[-20:]
    ]

    avg_range = (
        sum(recent_ranges)
        / len(recent_ranges)
        if recent_ranges
        else atr
    )

    atr_ratio = (
        atr / avg_range
        if avg_range > 0
        else 1.0
    )

    if trend_strength >= 0.80:

        if ema20 > ema50:

            regime = "TREND_UP"

        else:

            regime = "TREND_DOWN"

    elif trend_strength <= 0.35:

        regime = "RANGE"

    else:

        regime = "TRANSITION"

    # Volatility override
    if atr_ratio >= 1.60:

        regime = (
            "HIGH_VOLATILITY_"
            + regime
        )

    elif atr_ratio <= 0.65:

        regime = (
            "LOW_VOLATILITY_"
            + regime
        )

    score = clamp(
        trend_strength * 50.0,
        0.0,
        100.0,
    )

    return {
        "regime": regime,
        "score": round(
            score,
            2,
        ),
        "trend_strength": round(
            trend_strength,
            3,
        ),
        "atr_ratio": round(
            atr_ratio,
            3,
        ),
    }


# ============================================================
# LOCATION
# ============================================================

def location_quality(
    candles,
    direction,
):

    current = candles[-1]

    close = current["close"]

    closes = [
        c["close"]
        for c in candles
    ]

    ema20 = calculate_ema(
        closes,
        EMA_FAST,
    )

    ema50 = calculate_ema(
        closes,
        EMA_SLOW,
    )

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    support = calculate_support(
        candles
    )

    resistance = calculate_resistance(
        candles
    )

    if atr <= 0:

        return {
            "score": 0.0,
            "valid": False,
            "zone": "UNKNOWN",
        }

    buffer = atr * 0.50

    score = 0.0

    zones = []

    if direction == "BUY":

        distance_support = (
            abs(close - support)
        )

        distance_resistance = (
            abs(resistance - close)
        )

        if (
            distance_support
            <= buffer
        ):

            score += 35.0
            zones.append(
                "NEAR_SUPPORT"
            )

        if (
            distance_resistance
            <= buffer
        ):

            score += 10.0
            zones.append(
                "NEAR_RESISTANCE"
            )

        if close > ema20:

            score += 20.0
            zones.append(
                "ABOVE_EMA20"
            )

        if ema20 > ema50:

            score += 20.0
            zones.append(
                "EMA_TREND_ALIGNED"
            )

        # Avoid buying too far above EMA
        extension = (
            close - ema20
        ) / atr

        if extension > 1.50:

            score -= 30.0
            zones.append(
                "OVEREXTENDED"
            )

    elif direction == "SELL":

        distance_resistance = (
            abs(resistance - close)
        )

        distance_support = (
            abs(close - support)
        )

        if (
            distance_resistance
            <= buffer
        ):

            score += 35.0
            zones.append(
                "NEAR_RESISTANCE"
            )

        if (
            distance_support
            <= buffer
        ):

            score += 10.0
            zones.append(
                "NEAR_SUPPORT"
            )

        if close < ema20:

            score += 20.0
            zones.append(
                "BELOW_EMA20"
            )

        if ema20 < ema50:

            score += 20.0
            zones.append(
                "EMA_TREND_ALIGNED"
            )

        extension = (
            ema20 - close
        ) / atr

        if extension > 1.50:

            score -= 30.0
            zones.append(
                "OVEREXTENDED"
            )

    score = clamp(
        score,
        0.0,
        100.0,
    )

    return {
        "score": round(
            score,
            2,
        ),

        "valid": score >= 45.0,

        "zone": (
            zones[0]
            if zones
            else "NEUTRAL"
        ),

        "zones": zones,

        "support": round_price(
            support
        ),

        "resistance": round_price(
            resistance
        ),

        "ema20": round(
            ema20,
            4,
        ),

        "ema50": round(
            ema50,
            4,
        ),
    }


# ============================================================
# MOMENTUM QUALITY
# ============================================================

def momentum_quality(
    candles,
    direction,
):

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    rsi = calculate_rsi(
        candles,
        RSI_PERIOD,
    )

    momentum = calculate_momentum_strength(
        candles,
        atr,
    )

    score = 0.0

    reasons = []

    if direction == "BUY":

        if (
            momentum["direction"]
            == "BULLISH"
        ):

            score += 45.0

            reasons.append(
                "Bullish price momentum"
            )

        if 45 <= rsi <= 70:

            score += 30.0

            reasons.append(
                "RSI supports BUY"
            )

        elif rsi > 70:

            score += 5.0

            reasons.append(
                "BUY momentum overextended"
            )

        else:

            reasons.append(
                "RSI weak for BUY"
            )

    elif direction == "SELL":

        if (
            momentum["direction"]
            == "BEARISH"
        ):

            score += 45.0

            reasons.append(
                "Bearish price momentum"
            )

        if 30 <= rsi <= 55:

            score += 30.0

            reasons.append(
                "RSI supports SELL"
            )

        elif rsi < 30:

            score += 5.0

            reasons.append(
                "SELL momentum overextended"
            )

        else:

            reasons.append(
                "RSI weak for SELL"
            )

    # Strength component
    score += (
        momentum["strength"]
        * 0.25
    )

    score = clamp(
        score,
        0.0,
        100.0,
    )

    return {
        "score": round(
            score,
            2,
        ),

        "valid": score >= 55.0,

        "direction": momentum[
            "direction"
        ],

        "strength": momentum[
            "strength"
        ],

        "rsi": round(
            rsi,
            2,
        ),

        "reasons": reasons,
    }


# ============================================================
# TRIGGER QUALITY
# ============================================================

def trigger_quality(
    candles,
    direction,
):

    if len(candles) < (
        TRIGGER_LOOKBACK + 2
    ):

        return {
            "score": 0.0,
            "valid": False,
            "triggered": False,
        }

    current = candles[-1]

    previous = candles[
        -(
            TRIGGER_LOOKBACK + 1
        ):-1
    ]

    previous_high = max(
        c["high"]
        for c in previous
    )

    previous_low = min(
        c["low"]
        for c in previous
    )

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    if atr <= 0:

        return {
            "score": 0.0,
            "valid": False,
            "triggered": False,
        }

    body_ratio = (
        candle_body(current)
        / candle_range(current)
    )

    score = 0.0

    reasons = []

    triggered = False

    trigger_price = None

    if direction == "BUY":

        trigger_price = previous_high

        breakout_distance = (
            current["close"]
            - trigger_price
        )

        if current["close"] > trigger_price:

            triggered = True

            score += 55.0

            reasons.append(
                "BUY breakout trigger"
            )

            if (
                breakout_distance
                >= atr * 0.10
            ):

                score += 15.0

                reasons.append(
                    "Breakout distance sufficient"
                )

        if is_bullish(current):

            score += 15.0

        if body_ratio >= 0.50:

            score += 15.0

    elif direction == "SELL":

        trigger_price = previous_low

        breakout_distance = (
            trigger_price
            - current["close"]
        )

        if current["close"] < trigger_price:

            triggered = True

            score += 55.0

            reasons.append(
                "SELL breakdown trigger"
            )

            if (
                breakout_distance
                >= atr * 0.10
            ):

                score += 15.0

                reasons.append(
                    "Breakdown distance sufficient"
                )

        if is_bearish(current):

            score += 15.0

        if body_ratio >= 0.50:

            score += 15.0

    score = clamp(
        score,
        0.0,
        100.0,
    )

    return {
        "score": round(
            score,
            2,
        ),

        "valid": (
            triggered
            and score
            >= MIN_TRIGGER_QUALITY
        ),

        "triggered": triggered,

        "trigger": round_price(
            trigger_price
        ),

        "signal_close": round_price(
            current["close"]
        ),

        "body_ratio": round(
            body_ratio,
            3,
        ),

        "reasons": reasons,
    }


# ============================================================
# HARD FILTER
# ============================================================

def hard_filter(
    direction,
    pattern_quality_result,
    directional,
    regime,
    location,
    momentum,
    trigger,
    atr,
):

    checks = {}

    checks["direction"] = (
        direction is not None
        and not directional[
            "conflict"
        ]
    )

    checks["pattern_quality"] = (
        pattern_quality_result[
            "score"
        ]
        >= MIN_PATTERN_QUALITY
    )

    checks["market_regime"] = (
        regime["regime"]
        != "UNKNOWN"
    )

    checks["location"] = (
        location["valid"]
    )

    checks["momentum"] = (
        momentum["valid"]
    )

    checks["trigger"] = (
        trigger["valid"]
    )

    checks["atr"] = (
        atr >= MIN_ATR
    )

    passed = all(
        checks.values()
    )

    failed = [
        key
        for key, value
        in checks.items()
        if not value
    ]

    return {
        "passed": passed,
        "checks": checks,
        "failed": failed,
    }


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    pattern_quality_result,
    directional,
    regime,
    location,
    momentum,
    trigger,
):

    # Weighted quality score.
    #
    # Pattern        25
    # Direction      10
    # Regime         15
    # Location       15
    # Momentum       15
    # Trigger        20
    #
    # Total          100

    score = 0.0

    score += (
        pattern_quality_result["score"]
        * 0.25
    )

    score += (
        directional["strength"]
        * 0.10
    )

    score += (
        regime["score"]
        * 0.15
    )

    score += (
        location["score"]
        * 0.15
    )

    score += (
        momentum["score"]
        * 0.15
    )

    score += (
        trigger["score"]
        * 0.20
    )

    return round(
        clamp(
            score,
            0.0,
            100.0,
        ),
        2,
    )


# ============================================================
# ATR SL / TP
# ============================================================

def calculate_trade_levels(
    direction,
    entry,
    atr,
    support,
    resistance,
):

    if atr <= 0:
        return None

    minimum_risk = (
        atr * MIN_STOP_ATR
    )

    maximum_risk = (
        atr * MAX_STOP_ATR
    )

    if direction == "BUY":

        structural_sl = (
            support
            - atr
            * STRUCTURE_BUFFER_ATR
        )

        structural_distance = (
            entry
            - structural_sl
        )

        if (
            structural_distance
            >= minimum_risk
            and structural_distance
            <= maximum_risk
        ):

            risk = structural_distance

            stop_loss = structural_sl

        else:

            risk = minimum_risk

            stop_loss = (
                entry - risk
            )

        take_profit = (
            entry
            + risk
            * RISK_REWARD
        )

    elif direction == "SELL":

        structural_sl = (
            resistance
            + atr
            * STRUCTURE_BUFFER_ATR
        )

        structural_distance = (
            structural_sl
            - entry
        )

        if (
            structural_distance
            >= minimum_risk
            and structural_distance
            <= maximum_risk
        ):

            risk = structural_distance

            stop_loss = structural_sl

        else:

            risk = minimum_risk

            stop_loss = (
                entry + risk
            )

        take_profit = (
            entry
            - risk
            * RISK_REWARD
        )

    else:

        return None

    if risk <= 0:
        return None

    reward = abs(
        take_profit - entry
    )

    rr = (
        reward / risk
        if risk > 0
        else 0
    )

    if rr < MIN_RISK_REWARD:
        return None

    return {
        "entry": round_price(
            entry
        ),

        "stop_loss": round_price(
            stop_loss
        ),

        "take_profit": round_price(
            take_profit
        ),

        "risk_distance": round(
            risk,
            4,
        ),

        "risk_atr": round(
            risk / atr,
            3,
        ),

        "risk_reward": round(
            rr,
            2,
        ),
    }


# ============================================================
# COMPLETE SETUP ANALYSIS
# ============================================================

def analyze_setup(candles):

    latest = candles[-1]

    closes = [
        c["close"]
        for c in candles
    ]

    ema20 = calculate_ema(
        closes,
        EMA_FAST,
    )

    ema50 = calculate_ema(
        closes,
        EMA_SLOW,
    )

    atr = calculate_atr(
        candles,
        ATR_PERIOD,
    )

    rsi = calculate_rsi(
        candles,
        RSI_PERIOD,
    )

    trend = get_trend(
        ema20,
        ema50,
        latest["close"],
    )

    patterns = detect_patterns(
        candles
    )

    directional = directional_filter(
        patterns
    )

    direction = directional[
        "direction"
    ]

    pattern_q = pattern_quality(
        candles,
        patterns,
        direction,
    )

    regime = market_regime(
        candles
    )

    location = location_quality(
        candles,
        direction,
    )

    momentum = momentum_quality(
        candles,
        direction,
    )

    trigger = trigger_quality(
        candles,
        direction,
    )

    hard = hard_filter(
        direction,
        pattern_q,
        directional,
        regime,
        location,
        momentum,
        trigger,
        atr,
    )

    score = calculate_score(
        pattern_q,
        directional,
        regime,
        location,
        momentum,
        trigger,
    )

    # ========================================================
    # IMPORTANT:
    # The setup candle is NOT the entry candle.
    # Entry must happen on NEXT CANDLE.
    # ========================================================

    setup_valid = (
        hard["passed"]
        and score >= MIN_SCORE
    )

    if setup_valid:

        signal = "NEXT_CANDLE_ENTRY"

        status = (
            "SETUP_CONFIRMED"
        )

    elif direction is None:

        signal = "NO_TRADE"

        status = (
            "DIRECTION_FILTER_FAILED"
        )

    elif not hard["passed"]:

        signal = "NO_TRADE"

        status = (
            "HARD_FILTER_FAILED"
        )

    else:

        signal = "NO_TRADE"

        status = (
            "SCORE_TOO_LOW"
        )

    return {
        "timestamp": latest[
            "datetime"
        ],

        "symbol": SYMBOL,

        "timeframe": "M5",

        "signal": signal,

        "status": status,

        "valid": setup_valid,

        "setup_candle": latest[
            "datetime"
        ],

        "entry_rule": (
            "NEXT CANDLE OPEN"
        ),

        "patterns": patterns,

        "directional_filter": {
            "direction": direction,
            "bullish": directional[
                "bullish"
            ],
            "bearish": directional[
                "bearish"
            ],
            "conflict": directional[
                "conflict"
            ],
            "strength": directional[
                "strength"
            ],
        },

        "pattern_quality": pattern_q,

        "market_regime": regime,

        "location": location,

        "momentum": momentum,

        "trigger_quality": trigger,

        "hard_filter": hard,

        "score": score,

        "confidence": score,

        "atr": round(
            atr,
            4,
        ),

        "rsi": round(
            rsi,
            2,
        ),

        "ema20": round(
            ema20,
            4,
        ),

        "ema50": round(
            ema50,
            4,
        ),

        "trend": trend,

        "support": round_price(
            location.get(
                "support",
                0,
            )
        ),

        "resistance": round_price(
            location.get(
                "resistance",
                0,
            )
        ),

        "next_candle_entry": (
            setup_valid
        ),

        "trade_levels": None,

        "architecture": [
            "Pattern",
            "Pattern Quality",
            "Directional Filter",
            "Market Regime",
            "Location",
            "Momentum",
            "Trigger Quality",
            "Hard Filter",
            "Score",
            "NEXT CANDLE ENTRY",
            "ATR SL/TP",
            "Realistic Backtest",
        ],
    }


# ============================================================
# APPLY NEXT CANDLE ENTRY
# ============================================================

def apply_next_candle_entry(
    setup,
    next_candle,
):

    if not setup.get("valid"):
        return None

    direction = setup.get(
        "directional_filter",
        {},
    ).get(
        "direction"
    )

    if direction not in (
        "BUY",
        "SELL",
    ):
        return None

    raw_open = float(
        next_candle["open"]
    )

    # ========================================================
    # Realistic execution
    #
    # BUY:
    #   pay ask = open + half spread
    #
    # SELL:
    #   receive bid = open - half spread
    #
    # Slippage is applied in adverse direction.
    # ========================================================

    half_spread = (
        BACKTEST_SPREAD / 2.0
    )

    if direction == "BUY":

        entry = (
            raw_open
            + half_spread
            + BACKTEST_SLIPPAGE
        )

    else:

        entry = (
            raw_open
            - half_spread
            - BACKTEST_SLIPPAGE
        )

    atr = safe_float(
        setup.get(
            "atr",
            0,
        )
    )

    support = safe_float(
        setup.get(
            "support",
            0,
        )
    )

    resistance = safe_float(
        setup.get(
            "resistance",
            0,
        )
    )

    levels = calculate_trade_levels(
        direction,
        entry,
        atr,
        support,
        resistance,
    )

    if levels is None:
        return None

    return {
        "direction": direction,

        "setup_timestamp": setup[
            "timestamp"
        ],

        "entry_timestamp": next_candle[
            "datetime"
        ],

        "entry": levels["entry"],

        "stop_loss": levels[
            "stop_loss"
        ],

        "take_profit": levels[
            "take_profit"
        ],

        "risk_distance": levels[
            "risk_distance"
        ],

        "risk_atr": levels[
            "risk_atr"
        ],

        "risk_reward": levels[
            "risk_reward"
        ],

        "score": setup[
            "score"
        ],

        "patterns": setup[
            "patterns"
        ],

        "regime": setup[
            "market_regime"
        ]["regime"],
    }


# ============================================================
# TRADE EVALUATION
# ============================================================

def evaluate_trade(
    candles,
    entry_index,
    trade,
):

    direction = trade[
        "direction"
    ]

    entry = float(
        trade["entry"]
    )

    stop_loss = float(
        trade["stop_loss"]
    )

    take_profit = float(
        trade["take_profit"]
    )

    risk = abs(
        entry - stop_loss
    )

    last_index = min(
        entry_index
        + FORWARD_BARS,
        len(candles) - 1,
    )

    current_sl = stop_loss

    exit_price = None

    exit_index = last_index

    result = "TIMEOUT"

    exit_reason = (
        "FORWARD_BARS_TIMEOUT"
    )

    mfe_price = 0.0

    mae_price = 0.0

    for j in range(
        entry_index,
        last_index + 1,
    ):

        candle = candles[j]

        high = float(
            candle["high"]
        )

        low = float(
            candle["low"]
        )

        # ====================================================
        # BUY
        # ====================================================

        if direction == "BUY":

            favorable = (
                high - entry
            )

            adverse = (
                entry - low
            )

            mfe_price = max(
                mfe_price,
                favorable,
            )

            mae_price = max(
                mae_price,
                adverse,
            )

            # ------------------------------------------------
            # Break even
            # ------------------------------------------------

            if (
                ENABLE_BREAK_EVEN
                and risk > 0
                and high >= (
                    entry
                    + risk
                    * BREAK_EVEN_R
                )
            ):

                current_sl = max(
                    current_sl,
                    entry,
                )

            # ------------------------------------------------
            # Trailing
            # ------------------------------------------------

            if (
                ENABLE_TRAILING
                and risk > 0
            ):

                start = max(
                    0,
                    j - ATR_PERIOD - 1,
                )

                atr_now = calculate_atr(
                    candles[
                        start:j + 1
                    ],
                    ATR_PERIOD,
                )

                if atr_now > 0:

                    trailing_sl = (
                        high
                        - atr_now
                        * TRAILING_ATR
                    )

                    current_sl = max(
                        current_sl,
                        trailing_sl,
                    )

            hit_sl = (
                low <= current_sl
            )

            hit_tp = (
                high >= take_profit
            )

            # Conservative:
            # If both happen in same candle,
            # assume SL happened first.
            if hit_sl and hit_tp:

                exit_price = current_sl

                exit_index = j

                if current_sl >= entry:

                    result = "BREAKEVEN"

                    exit_reason = (
                        "SL_AND_TP_SAME_CANDLE_AFTER_BE"
                    )

                else:

                    result = "LOSS"

                    exit_reason = (
                        "SL_AND_TP_SAME_CANDLE"
                    )

                break

            if hit_sl:

                exit_price = current_sl

                exit_index = j

                if current_sl >= entry:

                    result = "BREAKEVEN"

                    exit_reason = (
                        "BREAK_EVEN"
                    )

                else:

                    result = "LOSS"

                    exit_reason = (
                        "STOP_LOSS"
                    )

                break

            if hit_tp:

                exit_price = take_profit

                exit_index = j

                result = "WIN"

                exit_reason = (
                    "TAKE_PROFIT"
                )

                break

        # ====================================================
        # SELL
        # ====================================================

        else:

            favorable = (
                entry - low
            )

            adverse = (
                high - entry
            )

            mfe_price = max(
                mfe_price,
                favorable,
            )

            mae_price = max(
                mae_price,
                adverse,
            )

            # ------------------------------------------------
            # Break even
            # ------------------------------------------------

            if (
                ENABLE_BREAK_EVEN
                and risk > 0
                and low <= (
                    entry
                    - risk
                    * BREAK_EVEN_R
                )
            ):

                current_sl = min(
                    current_sl,
                    entry,
                )

            # ------------------------------------------------
            # Trailing
            # ------------------------------------------------

            if (
                ENABLE_TRAILING
                and risk > 0
            ):

                start = max(
                    0,
                    j - ATR_PERIOD - 1,
                )

                atr_now = calculate_atr(
                    candles[
                        start:j + 1
                    ],
                    ATR_PERIOD,
                )

                if atr_now > 0:

                    trailing_sl = (
                        low
                        + atr_now
                        * TRAILING_ATR
                    )

                    current_sl = min(
                        current_sl,
                        trailing_sl,
                    )

            hit_sl = (
                high >= current_sl
            )

            hit_tp = (
                low <= take_profit
            )

            if hit_sl and hit_tp:

                exit_price = current_sl

                exit_index = j

                if current_sl <= entry:

                    result = "BREAKEVEN"

                    exit_reason = (
                        "SL_AND_TP_SAME_CANDLE_AFTER_BE"
                    )

                else:

                    result = "LOSS"

                    exit_reason = (
                        "SL_AND_TP_SAME_CANDLE"
                    )

                break

            if hit_sl:

                exit_price = current_sl

                exit_index = j

                if current_sl <= entry:

                    result = "BREAKEVEN"

                    exit_reason = (
                        "BREAK_EVEN"
                    )

                else:

                    result = "LOSS"

                    exit_reason = (
                        "STOP_LOSS"
                    )

                break

            if hit_tp:

                exit_price = take_profit

                exit_index = j

                result = "WIN"

                exit_reason = (
                    "TAKE_PROFIT"
                )

                break

    # ========================================================
    # TIMEOUT
    # ========================================================

    if exit_price is None:

        exit_price = float(
            candles[
                exit_index
            ]["close"]
        )

        result = "TIMEOUT"

        exit_reason = (
            "FORWARD_BARS_TIMEOUT"
        )

    # ========================================================
    # PNL
    # ========================================================

    if direction == "BUY":

        pnl_price = (
            exit_price
            - entry
        )

    else:

        pnl_price = (
            entry
            - exit_price
        )

    # ========================================================
    # R MULTIPLE
    # ========================================================

    if risk > 0:

        r_multiple = (
            pnl_price / risk
        )

        mfe_r = (
            mfe_price / risk
        )

        mae_r = (
            mae_price / risk
        )

    else:

        r_multiple = 0.0
        mfe_r = 0.0
        mae_r = 0.0

    pnl_percent = (
        pnl_price
        / entry
        * 100.0
    )

    return {
        "setup_timestamp": trade[
            "setup_timestamp"
        ],

        "entry_timestamp": trade[
            "entry_timestamp"
        ],

        "exit_timestamp": candles[
            exit_index
        ]["datetime"],

        "signal": direction,

        "patterns": trade[
            "patterns"
        ],

        "regime": trade[
            "regime"
        ],

        "score": trade[
            "score"
        ],

        "entry": round_price(
            entry
        ),

        "stop_loss": round_price(
            stop_loss
        ),

        "take_profit": round_price(
            take_profit
        ),

        "risk_reward": trade[
            "risk_reward"
        ],

        "risk_atr": trade[
            "risk_atr"
        ],

        "result": result,

        "exit_reason": exit_reason,

        "exit_price": round_price(
            exit_price
        ),

        "pnl_price": round(
            pnl_price,
            4,
        ),

        "pnl_percent": round(
            pnl_percent,
            4,
        ),

        "r_multiple": round(
            r_multiple,
            4,
        ),

        "mfe_price": round(
            mfe_price,
            4,
        ),

        "mae_price": round(
            mae_price,
            4,
        ),

        "mfe_r": round(
            mfe_r,
            4,
        ),

        "mae_r": round(
            mae_r,
            4,
        ),

        "bars_held": (
            exit_index
            - entry_index
            + 1
        ),
    }


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    points=None
):

    candles = get_candles()

    total_candles = len(
        candles
    )

    if points is None:

        points = BACKTEST_POINTS

    points = int(
        clamp(
            points,
            50,
            max(
                50,
                total_candles - 120,
            ),
        )
    )

    minimum_start = max(
        EMA_SLOW + 10,
        80,
    )

    # Need one candle after setup
    # plus forward bars.
    end = (
        total_candles
        - FORWARD_BARS
        - 2
    )

    if end <= minimum_start:

        raise RuntimeError(
            "Not enough candles for backtest"
        )

    start = max(
        minimum_start,
        end - points,
    )

    trade_results = []

    pattern_frequency = {}

    regime_frequency = {}

    score_buckets = {
        "70-74": 0,
        "75-79": 0,
        "80-84": 0,
        "85-89": 0,
        "90-94": 0,
        "95-100": 0,
    }

    candidate_count = 0
    hard_filter_count = 0
    score_pass_count = 0
    executed_count = 0

    # ========================================================
    # WALK FORWARD
    # ========================================================

    i = start

    while i < end:

        historical = candles[
            :i + 1
        ]

        setup = analyze_setup(
            historical
        )

        patterns = setup.get(
            "patterns",
            [],
        )

        for pattern in patterns:

            pattern_frequency[
                pattern
            ] = (
                pattern_frequency.get(
                    pattern,
                    0,
                )
                + 1
            )

        regime_name = setup.get(
            "market_regime",
            {},
        ).get(
            "regime",
            "UNKNOWN",
        )

        regime_frequency[
            regime_name
        ] = (
            regime_frequency.get(
                regime_name,
                0,
            )
            + 1
        )

        direction = setup.get(
            "directional_filter",
            {},
        ).get(
            "direction"
        )

        if direction:

            candidate_count += 1

        hard_passed = setup.get(
            "hard_filter",
            {},
        ).get(
            "passed",
            False,
        )

        if hard_passed:

            hard_filter_count += 1

        score = float(
            setup.get(
                "score",
                0,
            )
        )

        if score >= MIN_SCORE:

            score_pass_count += 1

            if 70 <= score < 75:
                score_buckets[
                    "70-74"
                ] += 1

            elif 75 <= score < 80:
                score_buckets[
                    "75-79"
                ] += 1

            elif 80 <= score < 85:
                score_buckets[
                    "80-84"
                ] += 1

            elif 85 <= score < 90:
                score_buckets[
                    "85-89"
                ] += 1

            elif 90 <= score < 95:
                score_buckets[
                    "90-94"
                ] += 1

            elif score >= 95:

                score_buckets[
                    "95-100"
                ] += 1

        # ====================================================
        # Setup at candle N
        #
        # Entry at candle N+1 OPEN
        # ====================================================

        if setup.get("valid"):

            next_index = i + 1

            if next_index >= len(
                candles
            ):
                break

            trade = (
                apply_next_candle_entry(
                    setup,
                    candles[
                        next_index
                    ],
                )
            )

            if trade is not None:

                result = evaluate_trade(
                    candles,
                    next_index,
                    trade,
                )

                if result is not None:

                    trade_results.append(
                        result
                    )

                    executed_count += 1

                    # ------------------------------------------------
                    # Do not overlap positions.
                    # ------------------------------------------------

                    bars_held = max(
                        1,
                        result[
                            "bars_held"
                        ],
                    )

                    i = (
                        next_index
                        + bars_held
                    )

                    continue

        i += 1

    # ========================================================
    # BASIC COUNTS
    # ========================================================

    signals = len(
        trade_results
    )

    wins = sum(
        1
        for x in trade_results
        if x["result"] == "WIN"
    )

    losses = sum(
        1
        for x in trade_results
        if x["result"] == "LOSS"
    )

    breakevens = sum(
        1
        for x in trade_results
        if x["result"] == "BREAKEVEN"
    )

    timeouts = sum(
        1
        for x in trade_results
        if x["result"] == "TIMEOUT"
    )

    buys = sum(
        1
        for x in trade_results
        if x["signal"] == "BUY"
    )

    sells = sum(
        1
        for x in trade_results
        if x["signal"] == "SELL"
    )

    # ========================================================
    # PROFIT
    # ========================================================

    total_profit = sum(
        max(
            x["pnl_percent"],
            0.0,
        )
        for x in trade_results
    )

    total_loss = sum(
        abs(
            min(
                x["pnl_percent"],
                0.0,
            )
        )
        for x in trade_results
    )

    net_profit = (
        total_profit
        - total_loss
    )

    # ========================================================
    # R
    # ========================================================

    total_r = sum(
        x["r_multiple"]
        for x in trade_results
    )

    average_r = (
        total_r / signals
        if signals
        else 0.0
    )

    # ========================================================
    # R WIN / LOSS
    # ========================================================

    winning_r = sum(
        max(
            x["r_multiple"],
            0.0,
        )
        for x in trade_results
    )

    losing_r = sum(
        abs(
            min(
                x["r_multiple"],
                0.0,
            )
        )
        for x in trade_results
    )

    if losing_r > 0:

        profit_factor_r = (
            winning_r
            / losing_r
        )

    elif winning_r > 0:

        profit_factor_r = float(
            "inf"
        )

    else:

        profit_factor_r = 0.0

    # ========================================================
    # RATES
    # ========================================================

    resolved = (
        wins
        + losses
        + breakevens
    )

    if signals:

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

        breakeven_rate = (
            breakevens
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
        breakeven_rate = 0.0
        timeout_rate = 0.0

    if resolved:

        resolved_win_rate = (
            wins
            / resolved
            * 100.0
        )

    else:

        resolved_win_rate = 0.0

    # ========================================================
    # EXPECTANCY
    # ========================================================

    expectancy_r = (
        total_r / signals
        if signals
        else 0.0
    )

    expectancy_percent = (
        net_profit / signals
        if signals
        else 0.0
    )

    # ========================================================
    # PROFIT FACTOR
    # ========================================================

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

    # ========================================================
    # EQUITY / DRAWDOWN
    # ========================================================

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0

    current_losing_streak = 0
    longest_losing_streak = 0

    equity_curve = []

    for trade in trade_results:

        equity += trade[
            "pnl_percent"
        ]

        peak = max(
            peak,
            equity,
        )

        drawdown = (
            peak
            - equity
        )

        max_drawdown = max(
            max_drawdown,
            drawdown,
        )

        equity_curve.append(
            round(
                equity,
                4,
            )
        )

        if trade["result"] == "LOSS":

            current_losing_streak += 1

            longest_losing_streak = max(
                longest_losing_streak,
                current_losing_streak,
            )

        else:

            current_losing_streak = 0

    # ========================================================
    # MFE / MAE
    # ========================================================

    mfe_values = [
        x["mfe_r"]
        for x in trade_results
    ]

    mae_values = [
        x["mae_r"]
        for x in trade_results
    ]

    score_values = [
        x["score"]
        for x in trade_results
    ]

    avg_mfe_r = (
        sum(mfe_values)
        / len(mfe_values)
        if mfe_values
        else 0.0
    )

    avg_mae_r = (
        sum(mae_values)
        / len(mae_values)
        if mae_values
        else 0.0
    )

    avg_score = (
        sum(score_values)
        / len(score_values)
        if score_values
        else 0.0
    )

    # ========================================================
    # DIRECTION STATS
    # ========================================================

    def direction_stats(
        trades
    ):

        if not trades:

            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "timeouts": 0,
                "win_rate_percent": 0.0,
                "net_profit_percent": 0.0,
                "average_r": 0.0,
                "profit_factor": 0.0,
            }

        local_wins = sum(
            1
            for x in trades
            if x["result"] == "WIN"
        )

        local_losses = sum(
            1
            for x in trades
            if x["result"] == "LOSS"
        )

        local_be = sum(
            1
            for x in trades
            if x["result"]
            == "BREAKEVEN"
        )

        local_timeout = sum(
            1
            for x in trades
            if x["result"] == "TIMEOUT"
        )

        local_profit = sum(
            max(
                x["pnl_percent"],
                0,
            )
            for x in trades
        )

        local_loss = sum(
            abs(
                min(
                    x["pnl_percent"],
                    0,
                )
            )
            for x in trades
        )

        local_net = (
            local_profit
            - local_loss
        )

        local_r = sum(
            x["r_multiple"]
            for x in trades
        )

        if local_loss > 0:

            local_pf = (
                local_profit
                / local_loss
            )

        elif local_profit > 0:

            local_pf = float(
                "inf"
            )

        else:

            local_pf = 0.0

        return {
            "trades": len(trades),

            "wins": local_wins,

            "losses": local_losses,

            "breakevens": local_be,

            "timeouts": local_timeout,

            "win_rate_percent": round(
                local_wins
                / len(trades)
                * 100.0,
                2,
            ),

            "net_profit_percent": round(
                local_net,
                4,
            ),

            "average_r": round(
                local_r
                / len(trades),
                4,
            ),

            "profit_factor": (
                round(
                    local_pf,
                    4,
                )
                if math.isfinite(
                    local_pf
                )
                else "infinite"
            ),
        }

    buy_stats = direction_stats(
        [
            x
            for x in trade_results
            if x["signal"] == "BUY"
        ]
    )

    sell_stats = direction_stats(
        [
            x
            for x in trade_results
            if x["signal"] == "SELL"
        ]
    )

    # ========================================================
    # REGIME PERFORMANCE
    # ========================================================

    regime_performance = {}

    unique_regimes = set(
        x["regime"]
        for x in trade_results
    )

    for regime_name in unique_regimes:

        regime_trades = [
            x
            for x in trade_results
            if x["regime"]
            == regime_name
        ]

        regime_performance[
            regime_name
        ] = direction_stats(
            regime_trades
        )

    # ========================================================
    # SCORE PERFORMANCE
    # ========================================================

    score_performance = {}

    buckets = {
        "70-74": (
            70,
            75,
        ),

        "75-79": (
            75,
            80,
        ),

        "80-84": (
            80,
            85,
        ),

        "85-89": (
            85,
            90,
        ),

        "90-94": (
            90,
            95,
        ),

        "95-100": (
            95,
            101,
        ),
    }

    for name, (
        lower,
        upper,
    ) in buckets.items():

        bucket_trades = [
            x
            for x in trade_results
            if lower
            <= x["score"]
            < upper
        ]

        score_performance[
            name
        ] = direction_stats(
            bucket_trades
        )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "status": "completed",

        "symbol": SYMBOL,

        "timeframe": "M5",

        "system": (
            "Quality Filtered "
            "Next Candle Entry Engine"
        ),

        "architecture": [
            "Pattern",
            "Pattern Quality",
            "Directional Filter",
            "Market Regime",
            "Location",
            "Momentum",
            "Trigger Quality",
            "Hard Filter",
            "Score",
            "NEXT CANDLE ENTRY",
            "ATR SL/TP",
            "Realistic Backtest",
        ],

        "data_source": (
            "Twelve Data XAU/USD"
        ),

        "candles_available": (
            total_candles
        ),

        "test_points": (
            end - start
        ),

        "rules": {

            "minimum_atr": MIN_ATR,

            "minimum_pattern_quality": (
                MIN_PATTERN_QUALITY
            ),

            "minimum_trigger_quality": (
                MIN_TRIGGER_QUALITY
            ),

            "minimum_score": MIN_SCORE,

            "minimum_risk_reward": (
                MIN_RISK_REWARD
            ),

            "risk_reward": RISK_REWARD,

            "forward_bars": FORWARD_BARS,

            "trigger_lookback": (
                TRIGGER_LOOKBACK
            ),

            "min_stop_atr": MIN_STOP_ATR,

            "max_stop_atr": MAX_STOP_ATR,

            "break_even": (
                ENABLE_BREAK_EVEN
            ),

            "break_even_r": (
                BREAK_EVEN_R
            ),

            "trailing": (
                ENABLE_TRAILING
            ),

            "trailing_atr": (
                TRAILING_ATR
            ),

            "spread": (
                BACKTEST_SPREAD
            ),

            "slippage": (
                BACKTEST_SLIPPAGE
            ),

            "entry": (
                "NEXT CANDLE OPEN"
            ),
        },

        "pipeline_counts": {

            "pattern_candidates": (
                candidate_count
            ),

            "hard_filter_passed": (
                hard_filter_count
            ),

            "score_passed": (
                score_pass_count
            ),

            "executed_trades": (
                executed_count
            ),
        },

        "signals": {

            "total": signals,

            "buy": buys,

            "sell": sells,
        },

        "results": {

            "wins": wins,

            "losses": losses,

            "breakevens": breakevens,

            "timeouts": timeouts,

            "resolved": resolved,
        },

        "performance": {

            "win_rate_percent": round(
                win_rate,
                2,
            ),

            "resolved_win_rate_percent": round(
                resolved_win_rate,
                2,
            ),

            "loss_rate_percent": round(
                loss_rate,
                2,
            ),

            "breakeven_rate_percent": round(
                breakeven_rate,
                2,
            ),

            "timeout_rate_percent": round(
                timeout_rate,
                2,
            ),

            "total_profit_percent": round(
                total_profit,
                4,
            ),

            "total_loss_percent": round(
                total_loss,
                4,
            ),

            "net_profit_percent": round(
                net_profit,
                4,
            ),

            "profit_factor": (
                round(
                    profit_factor,
                    4,
                )
                if math.isfinite(
                    profit_factor
                )
                else "infinite"
            ),

            "profit_factor_r": (
                round(
                    profit_factor_r,
                    4,
                )
                if math.isfinite(
                    profit_factor_r
                )
                else "infinite"
            ),

            "expectancy_percent": round(
                expectancy_percent,
                4,
            ),

            "expectancy_r": round(
                expectancy_r,
                4,
            ),

            "average_r": round(
                average_r,
                4,
            ),

            "max_drawdown_percent": round(
                max_drawdown,
                4,
            ),

            "average_mfe_r": round(
                avg_mfe_r,
                4,
            ),

            "average_mae_r": round(
                avg_mae_r,
                4,
            ),

            "average_score": round(
                avg_score,
                2,
            ),

            "longest_losing_streak": (
                longest_losing_streak
            ),
        },

        "direction_performance": {

            "BUY": buy_stats,

            "SELL": sell_stats,
        },

        "regime_performance": (
            regime_performance
        ),

        "score_performance": (
            score_performance
        ),

        "score_bucket_candidates": (
            score_buckets
        ),

        "pattern_frequency": (
            pattern_frequency
        ),

        "regime_frequency": (
            regime_frequency
        ),

        "recent_trades": (
            trade_results[-20:]
        ),

        "warning": (
            "Historical simulation only. "
            "Twelve Data OHLC candles do not "
            "contain intrabar tick sequence. "
            "Therefore when SL and TP are both "
            "touched inside the same candle, "
            "the backtest conservatively assumes "
            "SL was hit first. Spread and "
            "slippage assumptions are included. "
            "Entry is always the NEXT CANDLE OPEN "
            "after a confirmed setup candle."
        ),
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
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
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
# STARTUP TELEGRAM
# ============================================================

def send_startup_notification():

    with STARTUP_LOCK:

        if STATE[
            "startup_sent"
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
            "<b>NEW ENGINE</b>\n"
            "\n"
            "Pattern\n"
            "↓\n"
            "Pattern Quality\n"
            "↓\n"
            "Directional Filter\n"
            "↓\n"
            "Market Regime\n"
            "↓\n"
            "Location\n"
            "↓\n"
            "Momentum\n"
            "↓\n"
            "Trigger Quality\n"
            "↓\n"
            "Hard Filter\n"
            "↓\n"
            "Score\n"
            "↓\n"
            "NEXT CANDLE ENTRY\n"
            "↓\n"
            "ATR SL/TP\n"
            "↓\n"
            "Realistic Backtest\n"
            "\n"
            "<b>Symbol:</b> XAU/USD\n"
            "<b>Timeframe:</b> M5\n"
            "<b>Minimum Score:</b> "
            + str(MIN_SCORE)
            + "\n"
            "<b>Minimum Pattern Quality:</b> "
            + str(MIN_PATTERN_QUALITY)
            + "\n"
            "<b>Minimum Trigger Quality:</b> "
            + str(MIN_TRIGGER_QUALITY)
            + "\n"
            "<b>RR:</b> "
            + str(RISK_REWARD)
            + "\n"
            "\n"
            "ระบบพร้อมทำงาน"
        )

        ok, error = send_telegram(
            message
        )

        if ok:

            STATE[
                "startup_sent"
            ] = True

            print(
                "Telegram welcome message sent successfully"
            )

            return True

        print(
            "Telegram startup failed:",
            error,
        )

        return False


# ============================================================
# TELEGRAM SETUP MESSAGE
# ============================================================

def format_setup_message(
    setup
):

    if not setup.get(
        "valid"
    ):

        return None

    direction = setup.get(
        "directional_filter",
        {},
    ).get(
        "direction"
    )

    if direction not in (
        "BUY",
        "SELL",
    ):

        return None

    emoji = (
        "🟢"
        if direction == "BUY"
        else "🔴"
    )

    patterns = setup.get(
        "patterns",
        [],
    )

    pattern_text = (
        ", ".join(patterns)
        if patterns
        else "-"
    )

    regime = setup.get(
        "market_regime",
        {},
    ).get(
        "regime",
        "-",
    )

    return (
        emoji
        + " <b>XAUUSD M5 SETUP</b>\n"
        "\n"
        "<b>DIRECTION:</b> "
        + direction
        + "\n"
        "<b>SCORE:</b> "
        + str(
            setup.get(
                "score",
                0,
            )
        )
        + "\n"
        "<b>PATTERN:</b> "
        + html.escape(
            pattern_text
        )
        + "\n"
        "<b>PATTERN QUALITY:</b> "
        + str(
            setup.get(
                "pattern_quality",
                {},
            ).get(
                "score",
                0,
            )
        )
        + "\n"
        "\n"
        "<b>REGIME:</b> "
        + html.escape(
            str(regime)
        )
        + "\n"
        "<b>MOMENTUM:</b> "
        + str(
            setup.get(
                "momentum",
                {},
            ).get(
                "score",
                0,
            )
        )
        + "\n"
        "<b>LOCATION:</b> "
        + str(
            setup.get(
                "location",
                {},
            ).get(
                "score",
                0,
            )
        )
        + "\n"
        "<b>TRIGGER:</b> "
        + str(
            setup.get(
                "trigger_quality",
                {},
            ).get(
                "score",
                0,
            )
        )
        + "\n"
        "\n"
        "⚠️ <b>NEXT CANDLE ENTRY</b>\n"
        "Entry will be evaluated at the next candle open.\n"
        "\n"
        "<b>Setup Time:</b> "
        + html.escape(
            str(
                setup.get(
                    "timestamp"
                )
            )
        )
    )


def maybe_send_setup(
    setup
):

    if not setup.get(
        "valid"
    ):

        return False

    direction = setup.get(
        "directional_filter",
        {},
    ).get(
        "direction"
    )

    key = (
        str(
            setup.get(
                "timestamp"
            )
        )
        + "_"
        + str(direction)
    )

    with SIGNAL_LOCK:

        if (
            STATE[
                "last_signal_key"
            ]
            == key
        ):

            return False

        message = format_setup_message(
            setup
        )

        if not message:

            return False

        ok, error = send_telegram(
            message
        )

        if not ok:

            STATE[
                "last_error"
            ] = error

            return False

        STATE[
            "last_signal_key"
        ] = key

        STATE[
            "last_signal_sent_at"
        ] = now_iso()

        return True


# ============================================================
# LIVE SIGNAL
# ============================================================

def run_signal(
    send_notification=True
):

    candles = get_candles()

    setup = analyze_setup(
        candles
    )

    STATE[
        "last_update"
    ] = now_iso()

    STATE[
        "last_signal"
    ] = setup

    STATE[
        "last_error"
    ] = None

    if send_notification:

        maybe_send_setup(
            setup
        )

    return setup


# ============================================================
# ROOT
# ============================================================

@app.route("/")
def home():

    return jsonify(
        {
            "name": (
                "XAUUSD M5 "
                "Quality Filtered "
                "Trading Engine"
            ),

            "status": "online",

            "symbol": SYMBOL,

            "timeframe": "M5",

            "data_source": (
                "Twelve Data"
            ),

            "architecture": [
                "Pattern",
                "Pattern Quality",
                "Directional Filter",
                "Market Regime",
                "Location",
                "Momentum",
                "Trigger Quality",
                "Hard Filter",
                "Score",
                "NEXT CANDLE ENTRY",
                "ATR SL/TP",
                "Realistic Backtest",
            ],

            "telegram": bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

            "patterns": PATTERNS,

            "rules": {
                "minimum_atr": MIN_ATR,

                "minimum_pattern_quality": (
                    MIN_PATTERN_QUALITY
                ),

                "minimum_trigger_quality": (
                    MIN_TRIGGER_QUALITY
                ),

                "minimum_score": MIN_SCORE,

                "risk_reward": RISK_REWARD,

                "forward_bars": FORWARD_BARS,

                "spread": BACKTEST_SPREAD,

                "slippage": BACKTEST_SLIPPAGE,
            },

            "endpoints": [
                "/",
                "/health",
                "/signal",
                "/backtest",
                "/strategy",
                "/test-data",
                "/test-telegram",
            ],
        }
    )


# ============================================================
# STRATEGY
# ============================================================

@app.route("/strategy")
def strategy():

    return jsonify(
        {
            "symbol": SYMBOL,

            "timeframe": "M5",

            "pipeline": [
                "Pattern",
                "Pattern Quality",
                "Directional Filter",
                "Market Regime",
                "Location",
                "Momentum",
                "Trigger Quality",
                "Hard Filter",
                "Score",
                "NEXT CANDLE ENTRY",
                "ATR SL/TP",
                "Realistic Backtest",
            ],

            "score": {

                "pattern_quality": 25,

                "directional_filter": 10,

                "market_regime": 15,

                "location": 15,

                "momentum": 15,

                "trigger_quality": 20,

                "maximum": 100,
            },

            "hard_filter": {

                "direction": True,

                "pattern_quality": True,

                "market_regime": True,

                "location": True,

                "momentum": True,

                "trigger": True,

                "atr": True,
            },

            "entry": {

                "rule": (
                    "NEXT CANDLE OPEN"
                ),

                "same_candle_entry": False,
            },

            "risk": {

                "risk_reward": RISK_REWARD,

                "minimum_risk_reward": (
                    MIN_RISK_REWARD
                ),

                "min_stop_atr": (
                    MIN_STOP_ATR
                ),

                "max_stop_atr": (
                    MAX_STOP_ATR
                ),

                "structure_buffer_atr": (
                    STRUCTURE_BUFFER_ATR
                ),
            },

            "realistic_execution": {

                "spread": (
                    BACKTEST_SPREAD
                ),

                "slippage": (
                    BACKTEST_SLIPPAGE
                ),

                "same_candle_sl_tp": (
                    "SL FIRST"
                ),
            },

            "trade_management": {

                "forward_bars": (
                    FORWARD_BARS
                ),

                "break_even": (
                    ENABLE_BREAK_EVEN
                ),

                "break_even_r": (
                    BREAK_EVEN_R
                ),

                "trailing": (
                    ENABLE_TRAILING
                ),

                "trailing_atr": (
                    TRAILING_ATR
                ),
            },
        }
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify(
        {
            "status": "healthy",

            "system": (
                "Quality Filtered "
                "Next Candle Engine"
            ),

            "symbol": SYMBOL,

            "timeframe": "M5",

            "data_source": (
                "Twelve Data"
            ),

            "twelve_data": bool(
                TWELVE_DATA_API_KEY
            ),

            "telegram": bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

            "startup_notification_sent": (
                STATE[
                    "startup_sent"
                ]
            ),

            "last_update": (
                STATE[
                    "last_update"
                ]
            ),

            "last_signal": (
                STATE[
                    "last_signal"
                ]
            ),

            "last_signal_sent_at": (
                STATE[
                    "last_signal_sent_at"
                ]
            ),

            "last_error": (
                STATE[
                    "last_error"
                ]
            ),
        }
    )


# ============================================================
# SIGNAL ENDPOINT
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        if not STATE[
            "startup_sent"
        ]:

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

        return jsonify(
            {
                "status": "error",

                "signal": "ERROR",

                "error": str(exc),
            }
        ), 500


# ============================================================
# TEST DATA
# ============================================================

@app.route("/test-data")
def test_data():

    try:

        candles = get_candles()

        latest = candles[-1]

        return jsonify(
            {
                "status": "success",

                "message": (
                    "Twelve Data connection "
                    "is working"
                ),

                "symbol": SYMBOL,

                "timeframe": "M5",

                "candles": len(
                    candles
                ),

                "latest": {
                    "datetime": latest[
                        "datetime"
                    ],

                    "open": latest[
                        "open"
                    ],

                    "high": latest[
                        "high"
                    ],

                    "low": latest[
                        "low"
                    ],

                    "close": latest[
                        "close"
                    ],
                },
            }
        )

    except Exception as exc:

        STATE[
            "last_error"
        ] = str(exc)

        return jsonify(
            {
                "status": "error",

                "message": str(exc),
            }
        ), 500


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (
        "🧪 <b>XAUUSD M5 BOT TEST</b>\n"
        "\n"
        "Telegram connection ทำงานปกติ\n"
        "\n"
        "<b>Pipeline:</b>\n"
        "Pattern\n"
        "→ Pattern Quality\n"
        "→ Directional Filter\n"
        "→ Market Regime\n"
        "→ Location\n"
        "→ Momentum\n"
        "→ Trigger Quality\n"
        "→ Hard Filter\n"
        "→ Score\n"
        "→ NEXT CANDLE ENTRY\n"
        "→ ATR SL/TP\n"
        "→ Realistic Backtest\n"
        "\n"
        "<b>Time:</b> "
        + html.escape(
            now_iso()
        )
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        return jsonify(
            {
                "status": "success",

                "message": (
                    "Telegram test message "
                    "sent successfully"
                ),

                "telegram": True,
            }
        )

    return jsonify(
        {
            "status": "error",

            "message": error,

            "telegram": False,
        }
    ), 500


# ============================================================
# BACKTEST ENDPOINT
# ============================================================

@app.route("/backtest")
def backtest_endpoint():

    try:

        points_param = request.args.get(
            "points"
        )

        if points_param:

            points = int(
                points_param
            )

        else:

            points = (
                BACKTEST_POINTS
            )

        result = run_backtest(
            points=points
        )

        return jsonify(
            result
        )

    except Exception as exc:

        STATE[
            "last_error"
        ] = str(exc)

        return jsonify(
            {
                "status": "error",

                "error": str(exc),
            }
        ), 500


# ============================================================
# STARTUP WORKER
# ============================================================

def startup_worker():

    try:

        time.sleep(2)

        send_startup_notification()

    except Exception as exc:

        print(
            "Startup notification error:",
            exc,
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    send_startup_notification()

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

else:

    startup_thread = threading.Thread(
        target=startup_worker,
        daemon=True,
    )

    startup_thread.start()

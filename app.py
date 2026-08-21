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
    "TWELVE_DATA_API_KEY", ""
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID", ""
).strip()


# ============================================================
# CONFIG
# ============================================================

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"

CANDLE_LIMIT = 1000

EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14
ATR_PERIOD = 14

MIN_ATR = 0.5

# คะแนนขั้นต่ำสำหรับ Entry
MIN_SCORE = 70.0

# RR ขั้นต่ำ
MIN_RISK_REWARD = 1.30

# RR เป้าหมาย
RISK_REWARD = 1.50

# ------------------------------------------------------------
# BACKTEST
# ------------------------------------------------------------

# 24 candles = 2 ชั่วโมงบน M5
FORWARD_BARS = 24

BACKTEST_POINTS = 200

# ------------------------------------------------------------
# STRUCTURE
# ------------------------------------------------------------

SUPPORT_LOOKBACK = 30
RESISTANCE_LOOKBACK = 30

TRIGGER_LOOKBACK = 3

# ------------------------------------------------------------
# STOP LOSS
# ------------------------------------------------------------

MIN_STOP_ATR = 1.0
MAX_STOP_ATR = 3.0

# buffer จาก structure
STRUCTURE_BUFFER_ATR = 0.15

# ------------------------------------------------------------
# SIGNAL
# ------------------------------------------------------------

SIGNAL_COOLDOWN_SECONDS = 60

# ------------------------------------------------------------
# TRADE MANAGEMENT
# ------------------------------------------------------------

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


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
    "startup_sent": False,
    "last_signal_sent_at": None,
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
        - max(candle["open"], candle["close"])
    )


def lower_wick(candle):
    return (
        min(candle["open"], candle["close"])
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

    # Twelve Data: newest -> oldest
    # Bot: oldest -> newest
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

    multiplier = 2.0 / (period + 1.0)

    ema = sum(values[:period]) / period

    for value in values[period:]:
        ema = (
            (value - ema) * multiplier
            + ema
        )

    return ema


# ============================================================
# RSI
# ============================================================

def calculate_rsi(candles, period=14):
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
            closes[i] - closes[i - 1]
        )

        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    recent_gains = gains[-period:]
    recent_losses = losses[-period:]

    avg_gain = sum(recent_gains) / period
    avg_loss = sum(recent_losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100.0 - (
        100.0 / (1.0 + rs)
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(candles, period=14):
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
            max(tr1, tr2, tr3)
        )

    recent = true_ranges[-period:]

    if not recent:
        return 0.0

    return sum(recent) / len(recent)


# ============================================================
# SUPPORT / RESISTANCE
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

def get_momentum(candles):
    if len(candles) < 5:
        return "NEUTRAL"

    current = candles[-1]["close"]
    previous = candles[-4]["close"]

    if current > previous:
        return "BULLISH"

    if current < previous:
        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# ENGULFING
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
        and candle_body(b) > candle_body(a)
    ):
        patterns.append(
            "Bullish Engulfing"
        )

    if (
        is_bullish(a)
        and is_bearish(b)
        and b["open"] >= a["close"]
        and b["close"] <= a["open"]
        and candle_body(b) > candle_body(a)
    ):
        patterns.append(
            "Bearish Engulfing"
        )

    return patterns


# ============================================================
# HAMMER
# ============================================================

def detect_hammer(candles):
    patterns = []

    if not candles:
        return patterns

    c = candles[-1]

    body = candle_body(c)
    rng = candle_range(c)

    if body <= 0:
        body = rng * 0.05

    lower = lower_wick(c)
    upper = upper_wick(c)

    if (
        lower >= body * 2.0
        and upper <= body
        and body / rng <= 0.45
    ):
        patterns.append("Hammer")

    return patterns


# ============================================================
# SHOOTING STAR
# ============================================================

def detect_shooting_star(candles):
    patterns = []

    if not candles:
        return patterns

    c = candles[-1]

    body = candle_body(c)
    rng = candle_range(c)

    if body <= 0:
        body = rng * 0.05

    upper = upper_wick(c)
    lower = lower_wick(c)

    if (
        upper >= body * 2.0
        and lower <= body
        and body / rng <= 0.45
    ):
        patterns.append(
            "Shooting Star"
        )

    return patterns


# ============================================================
# MORNING / EVENING STAR
# ============================================================

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


# ============================================================
# BREAKOUT
# ============================================================

def detect_breakout(candles):
    patterns = []

    if len(candles) < 21:
        return patterns

    current = candles[-1]

    previous_high = max(
        c["high"]
        for c in candles[-21:-1]
    )

    previous_low = min(
        c["low"]
        for c in candles[-21:-1]
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


# ============================================================
# PULLBACK
# ============================================================

def detect_pullback(
    candles,
    ema20,
    ema50,
):
    patterns = []

    if len(candles) < 6:
        return patterns

    current = candles[-1]
    recent = candles[-6:-1]

    # Bullish pullback
    if (
        ema20 > ema50
        and current["close"] >= ema20 * 0.998
        and current["close"] <= ema20 * 1.003
        and any(
            c["close"] < c["open"]
            for c in recent
        )
        and is_bullish(current)
    ):
        patterns.append("Pullback")

    # Bearish pullback
    if (
        ema20 < ema50
        and current["close"] <= ema20 * 1.002
        and current["close"] >= ema20 * 0.997
        and any(
            c["close"] > c["open"]
            for c in recent
        )
        and is_bearish(current)
    ):
        patterns.append("Pullback")

    return patterns


# ============================================================
# DOUBLE BOTTOM / TOP
# ============================================================

def detect_double_patterns(candles):
    patterns = []

    if len(candles) < 20:
        return patterns

    lows = [
        c["low"]
        for c in candles[-20:]
    ]

    highs = [
        c["high"]
        for c in candles[-20:]
    ]

    first_low = min(lows[:10])
    second_low = min(lows[10:])

    first_high = max(highs[:10])
    second_high = max(highs[10:])

    avg_price = candles[-1]["close"]

    if avg_price <= 0:
        return patterns

    low_difference = (
        abs(first_low - second_low)
        / avg_price
    )

    high_difference = (
        abs(first_high - second_high)
        / avg_price
    )

    if (
        low_difference <= 0.0015
        and candles[-1]["close"] > second_low
    ):
        patterns.append(
            "Double Bottom"
        )

    if (
        high_difference <= 0.0015
        and candles[-1]["close"] < second_high
    ):
        patterns.append(
            "Double Top"
        )

    return patterns


# ============================================================
# PATTERN RECOGNITION
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

    patterns = []

    patterns.extend(
        detect_engulfing(candles)
    )

    patterns.extend(
        detect_hammer(candles)
    )

    patterns.extend(
        detect_shooting_star(candles)
    )

    patterns.extend(
        detect_stars(candles)
    )

    patterns.extend(
        detect_breakout(candles)
    )

    patterns.extend(
        detect_pullback(
            candles,
            ema20,
            ema50,
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
# PATTERN DIRECTION
# ============================================================

BULLISH_PATTERNS = {
    "Bullish Engulfing",
    "Hammer",
    "Morning Star",
    "Bullish Breakout",
    "Double Bottom",
}

BEARISH_PATTERNS = {
    "Bearish Engulfing",
    "Shooting Star",
    "Evening Star",
    "Bearish Breakout",
    "Double Top",
}


def get_directional_patterns(patterns):
    bullish = []
    bearish = []

    for pattern in patterns:

        if pattern in BULLISH_PATTERNS:
            bullish.append(pattern)

        if pattern in BEARISH_PATTERNS:
            bearish.append(pattern)

    return bullish, bearish


# ============================================================
# CANDIDATE DIRECTION
# ============================================================

def get_candidate_direction(patterns):
    bullish, bearish = (
        get_directional_patterns(patterns)
    )

    bull_count = len(bullish)
    bear_count = len(bearish)

    if bull_count == 0 and bear_count == 0:
        return None

    # Conflict -> no trade
    if bull_count > 0 and bear_count > 0:

        difference = abs(
            bull_count - bear_count
        )

        # ต้องต่างกันอย่างน้อย 2
        if difference < 2:
            return None

    if bull_count > bear_count:
        return "BUY"

    if bear_count > bull_count:
        return "SELL"

    return None


# ============================================================
# DIRECTIONAL PATTERN QUALITY
# ============================================================

def get_pattern_quality(
    patterns,
    direction,
):
    bullish, bearish = (
        get_directional_patterns(patterns)
    )

    if direction == "BUY":

        relevant = bullish
        opposite = bearish

    elif direction == "SELL":

        relevant = bearish
        opposite = bullish

    else:
        return {
            "relevant": [],
            "opposite": [],
            "score": 0.0,
            "conflict": False,
        }

    # Pattern score
    base_score = min(
        len(relevant) * 7.0,
        20.0,
    )

    conflict = len(opposite) > 0

    if conflict:
        base_score -= min(
            len(opposite) * 5.0,
            10.0,
        )

    return {
        "relevant": relevant,
        "opposite": opposite,
        "score": round(
            clamp(
                base_score,
                0.0,
                20.0,
            ),
            2,
        ),
        "conflict": conflict,
    }


# ============================================================
# CONFIRMATION ENGINE
# ============================================================

def confirmation_engine(
    candles,
    patterns,
    direction,
):
    closes = [
        c["close"]
        for c in candles
    ]

    current = candles[-1]

    close = current["close"]

    ema20 = calculate_ema(
        closes,
        EMA_FAST,
    )

    ema50 = calculate_ema(
        closes,
        EMA_SLOW,
    )

    rsi = calculate_rsi(
        candles,
        RSI_PERIOD,
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

    trend = get_trend(
        ema20,
        ema50,
        close,
    )

    momentum = get_momentum(
        candles
    )

    pattern_quality = (
        get_pattern_quality(
            patterns,
            direction,
        )
    )

    checks = {
        "pattern": False,
        "trend": False,
        "momentum": False,
        "rsi": False,
        "location": False,
        "volatility": False,
        "trigger": False,
    }

    reasons = []

    # --------------------------------------------------------
    # PATTERN
    # --------------------------------------------------------

    pattern_score = (
        pattern_quality["score"]
    )

    if (
        pattern_quality["relevant"]
        and not pattern_quality["conflict"]
    ):
        checks["pattern"] = True

        reasons.append(
            "Directional pattern confirmed"
        )

    elif pattern_quality["relevant"]:

        reasons.append(
            "Directional pattern has conflict"
        )

    else:

        reasons.append(
            "No directional pattern"
        )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if direction == "BUY":

        if trend == "UPTREND":

            checks["trend"] = True

            reasons.append(
                "BUY aligned with uptrend"
            )

        elif trend == "SIDEWAYS":

            # Sideways ไม่ผ่าน trend
            reasons.append(
                "BUY rejected: sideways trend"
            )

        else:

            reasons.append(
                "BUY rejected: downtrend"
            )

    elif direction == "SELL":

        if trend == "DOWNTREND":

            checks["trend"] = True

            reasons.append(
                "SELL aligned with downtrend"
            )

        elif trend == "SIDEWAYS":

            reasons.append(
                "SELL rejected: sideways trend"
            )

        else:

            reasons.append(
                "SELL rejected: uptrend"
            )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    if direction == "BUY":

        if momentum == "BULLISH":

            checks["momentum"] = True

            reasons.append(
                "Bullish momentum"
            )

        else:

            reasons.append(
                "Momentum does not confirm BUY"
            )

    elif direction == "SELL":

        if momentum == "BEARISH":

            checks["momentum"] = True

            reasons.append(
                "Bearish momentum"
            )

        else:

            reasons.append(
                "Momentum does not confirm SELL"
            )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if direction == "BUY":

        if 45 <= rsi <= 70:

            checks["rsi"] = True

            reasons.append(
                "RSI supports BUY"
            )

        else:

            reasons.append(
                "RSI outside BUY zone"
            )

    elif direction == "SELL":

        if 30 <= rsi <= 55:

            checks["rsi"] = True

            reasons.append(
                "RSI supports SELL"
            )

        else:

            reasons.append(
                "RSI outside SELL zone"
            )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    location_buffer = max(
        atr * 0.50,
        1.0,
    )

    if direction == "BUY":

        near_support = (
            close <= support + location_buffer
        )

        breakout_zone = (
            close >= resistance - location_buffer
        )

        above_ema = close > ema20

        if (
            near_support
            or breakout_zone
            or above_ema
        ):
            checks["location"] = True

        if breakout_zone:

            reasons.append(
                "BUY near resistance/breakout zone"
            )

        elif near_support:

            reasons.append(
                "BUY near support"
            )

        elif above_ema:

            reasons.append(
                "BUY above EMA20"
            )

    elif direction == "SELL":

        near_resistance = (
            close >= resistance - location_buffer
        )

        breakdown_zone = (
            close <= support + location_buffer
        )

        below_ema = close < ema20

        if (
            near_resistance
            or breakdown_zone
            or below_ema
        ):
            checks["location"] = True

        if breakdown_zone:

            reasons.append(
                "SELL near support/breakdown zone"
            )

        elif near_resistance:

            reasons.append(
                "SELL near resistance"
            )

        elif below_ema:

            reasons.append(
                "SELL below EMA20"
            )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    if atr >= MIN_ATR:

        checks["volatility"] = True

        reasons.append(
            "ATR sufficient"
        )

    else:

        reasons.append(
            "ATR too low"
        )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    weights = {
        "pattern": 20.0,
        "trend": 20.0,
        "momentum": 15.0,
        "rsi": 10.0,
        "location": 10.0,
        "volatility": 10.0,
        "trigger": 15.0,
    }

    score = pattern_score

    if checks["trend"]:
        score += weights["trend"]

    if checks["momentum"]:
        score += weights["momentum"]

    if checks["rsi"]:
        score += weights["rsi"]

    if checks["location"]:
        score += weights["location"]

    if checks["volatility"]:
        score += weights["volatility"]

    score = round(
        clamp(score, 0.0, 100.0),
        2,
    )

    return {
        "direction": direction,

        "score": score,

        "valid": False,

        "checks": checks,

        "reasons": reasons,

        "ema20": round(ema20, 4),

        "ema50": round(ema50, 4),

        "rsi": round(rsi, 2),

        "atr": round(atr, 4),

        "trend": trend,

        "momentum": momentum,

        "support": round_price(support),

        "resistance": round_price(resistance),

        "bullish_patterns": (
            pattern_quality["relevant"]
            if direction == "BUY"
            else get_directional_patterns(
                patterns
            )[0]
        ),

        "bearish_patterns": (
            pattern_quality["relevant"]
            if direction == "SELL"
            else get_directional_patterns(
                patterns
            )[1]
        ),

        "pattern_score": pattern_score,

        "pattern_conflict": (
            pattern_quality["conflict"]
        ),
    }


# ============================================================
# ENTRY TRIGGER
# ============================================================

def calculate_trigger(
    candles,
    direction,
):
    if len(candles) < (
        TRIGGER_LOOKBACK + 2
    ):
        return None

    current = candles[-1]

    previous = candles[
        -(TRIGGER_LOOKBACK + 1):-1
    ]

    previous_high = max(
        c["high"]
        for c in previous
    )

    previous_low = min(
        c["low"]
        for c in previous
    )

    if direction == "BUY":

        trigger = previous_high

        if current["close"] > trigger:

            return {
                "triggered": True,
                "trigger": round_price(
                    trigger
                ),
                "entry": round_price(
                    current["close"]
                ),
            }

        return {
            "triggered": False,
            "trigger": round_price(
                trigger
            ),
            "entry": None,
        }

    if direction == "SELL":

        trigger = previous_low

        if current["close"] < trigger:

            return {
                "triggered": True,
                "trigger": round_price(
                    trigger
                ),
                "entry": round_price(
                    current["close"]
                ),
            }

        return {
            "triggered": False,
            "trigger": round_price(
                trigger
            ),
            "entry": None,
        }

    return None


# ============================================================
# TP / SL
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

    # --------------------------------------------------------
    # ATR based risk
    # --------------------------------------------------------

    minimum_risk = atr * MIN_STOP_ATR
    maximum_risk = atr * MAX_STOP_ATR

    if direction == "BUY":

        structural_sl = (
            support
            - atr * STRUCTURE_BUFFER_ATR
        )

        structural_distance = (
            entry
            - structural_sl
        )

        # ใช้โครงสร้างถ้าไม่กว้างเกินไป
        if (
            structural_distance >= minimum_risk
            and structural_distance <= maximum_risk
        ):
            actual_risk = structural_distance
            stop_loss = structural_sl

        else:
            actual_risk = minimum_risk
            stop_loss = entry - actual_risk

        take_profit = (
            entry
            + actual_risk * RISK_REWARD
        )

    elif direction == "SELL":

        structural_sl = (
            resistance
            + atr * STRUCTURE_BUFFER_ATR
        )

        structural_distance = (
            structural_sl
            - entry
        )

        if (
            structural_distance >= minimum_risk
            and structural_distance <= maximum_risk
        ):
            actual_risk = structural_distance
            stop_loss = structural_sl

        else:
            actual_risk = minimum_risk
            stop_loss = entry + actual_risk

        take_profit = (
            entry
            - actual_risk * RISK_REWARD
        )

    else:
        return None

    if actual_risk <= 0:
        return None

    reward = abs(
        take_profit - entry
    )

    rr = reward / actual_risk

    if rr < MIN_RISK_REWARD:
        return None

    return {
        "entry": round_price(entry),

        "stop_loss": round_price(
            stop_loss
        ),

        "take_profit": round_price(
            take_profit
        ),

        "risk_reward": round(
            rr,
            2,
        ),

        "risk_distance": round(
            actual_risk,
            4,
        ),

        "risk_atr": round(
            actual_risk / atr,
            2,
        ),
    }


# ============================================================
# COMPLETE SIGNAL ENGINE
# ============================================================

def analyze_market(candles):

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

    support = calculate_support(
        candles
    )

    resistance = calculate_resistance(
        candles
    )

    trend = get_trend(
        ema20,
        ema50,
        latest["close"],
    )

    momentum = get_momentum(
        candles
    )

    patterns = detect_patterns(
        candles
    )

    bullish, bearish = (
        get_directional_patterns(
            patterns
        )
    )

    direction = get_candidate_direction(
        patterns
    )

    # --------------------------------------------------------
    # NO DIRECTION
    # --------------------------------------------------------

    if direction is None:

        return {
            "timestamp": latest["datetime"],
            "symbol": SYMBOL,
            "timeframe": "M5",

            "signal": "NO_TRADE",
            "status": "NO_DIRECTION",
            "valid": False,

            "patterns": patterns,

            "directional_patterns": {
                "bullish": bullish,
                "bearish": bearish,
            },

            "candidate_direction": None,

            "score": 0.0,
            "confidence": 0.0,

            "entry": None,
            "stop_loss": None,
            "take_profit": None,

            "risk_reward": 0.0,
            "risk_distance": 0.0,

            "trigger": None,
            "triggered": False,

            "atr": round(atr, 4),
            "rsi": round(rsi, 2),

            "ema20": round(ema20, 4),
            "ema50": round(ema50, 4),

            "trend": trend,
            "momentum": momentum,

            "support": round_price(
                support
            ),

            "resistance": round_price(
                resistance
            ),

            "confirmation": None,

            "method": (
                "Pattern Recognition + "
                "Directional Filter + "
                "Confirmation + Trigger + "
                "Entry + TP/SL"
            ),

            "data_source": (
                "Twelve Data XAU/USD"
            ),
        }

    # --------------------------------------------------------
    # CONFIRMATION
    # --------------------------------------------------------

    confirmation = confirmation_engine(
        candles,
        patterns,
        direction,
    )

    # --------------------------------------------------------
    # TRIGGER
    # --------------------------------------------------------

    trigger = calculate_trigger(
        candles,
        direction,
    )

    if trigger is None:

        trigger = {
            "triggered": False,
            "trigger": None,
            "entry": None,
        }

    confirmation["checks"]["trigger"] = (
        bool(trigger["triggered"])
    )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    score = float(
        confirmation["score"]
    )

    if trigger["triggered"]:
        score += 15.0

    score = round(
        clamp(score, 0.0, 100.0),
        2,
    )

    confirmation["score"] = score

    if trigger["triggered"]:

        confirmation["reasons"].append(
            "Entry trigger confirmed"
        )

    else:

        confirmation["reasons"].append(
            "Waiting for {} trigger".format(
                direction
            )
        )

    # --------------------------------------------------------
    # MANDATORY CONDITIONS
    # --------------------------------------------------------

    mandatory = (
        confirmation["checks"]["pattern"]
        and confirmation["checks"]["trend"]
        and confirmation["checks"]["momentum"]
        and confirmation["checks"]["volatility"]
    )

    valid_confirmation = (
        mandatory
        and score >= MIN_SCORE
    )

    trade = None

    if (
        valid_confirmation
        and trigger["triggered"]
    ):

        trade = calculate_trade_levels(
            direction,
            trigger["entry"],
            atr,
            support,
            resistance,
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if trade is not None:

        signal = direction
        status = "ENTRY_READY"
        valid = True

    elif (
        valid_confirmation
        and not trigger["triggered"]
    ):

        signal = "WAIT_TRIGGER"
        status = "CONFIRMED_WAITING_TRIGGER"
        valid = False

    elif (
        score >= MIN_SCORE
    ):

        signal = "WAIT_CONFIRMATION"
        status = "HIGH_SCORE_NOT_CONFIRMED"
        valid = False

    else:

        signal = "NO_TRADE"
        status = "INSUFFICIENT_CONFIRMATION"
        valid = False

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "timestamp": latest["datetime"],
        "symbol": SYMBOL,
        "timeframe": "M5",

        "signal": signal,
        "status": status,
        "valid": valid,

        "patterns": patterns,

        "directional_patterns": {
            "bullish": bullish,
            "bearish": bearish,
        },

        "candidate_direction": direction,

        "score": score,
        "confidence": score,

        "entry": (
            trade["entry"]
            if trade
            else None
        ),

        "stop_loss": (
            trade["stop_loss"]
            if trade
            else None
        ),

        "take_profit": (
            trade["take_profit"]
            if trade
            else None
        ),

        "risk_reward": (
            trade["risk_reward"]
            if trade
            else 0.0
        ),

        "risk_distance": (
            trade["risk_distance"]
            if trade
            else 0.0
        ),

        "risk_atr": (
            trade["risk_atr"]
            if trade
            else 0.0
        ),

        "trigger": trigger["trigger"],

        "triggered": bool(
            trigger["triggered"]
        ),

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

        "momentum": momentum,

        "support": round_price(
            support
        ),

        "resistance": round_price(
            resistance
        ),

        "confirmation": confirmation,

        "method": (
            "Pattern Recognition + "
            "Directional Filter + "
            "Confirmation + Trigger + "
            "Entry + TP/SL"
        ),

        "data_source": (
            "Twelve Data XAU/USD"
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

        if not result.get("ok", False):

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
            "<b>Architecture</b>\n"
            "Pattern Recognition\n"
            "→ Direction Filter\n"
            "→ Confirmation\n"
            "→ Trigger\n"
            "→ Entry\n"
            "→ TP / SL\n"
            "→ Telegram\n"
            "\n"
            "<b>Symbol:</b> XAU/USD\n"
            "<b>Timeframe:</b> M5\n"
            "<b>Data:</b> Twelve Data\n"
            "\n"
            "<b>Minimum Score:</b> "
            + str(MIN_SCORE)
            + "\n"
            "<b>Minimum ATR:</b> "
            + str(MIN_ATR)
            + "\n"
            "<b>Risk / Reward:</b> "
            + str(RISK_REWARD)
            + "\n"
            "<b>Forward Bars:</b> "
            + str(FORWARD_BARS)
            + "\n"
            "\n"
            "ระบบพร้อมวิเคราะห์ตลาด"
        )

        ok, error = send_telegram(
            message
        )

        if ok:

            STATE["startup_sent"] = True

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
# TELEGRAM SIGNAL
# ============================================================

def format_signal_message(signal):

    direction = signal.get("signal")

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

    patterns = signal.get(
        "patterns",
        [],
    )

    pattern_text = (
        ", ".join(patterns)
        if patterns
        else "-"
    )

    return (
        emoji
        + " <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"
        "<b>SIGNAL:</b> "
        + html.escape(
            str(direction)
        )
        + "\n"
        "<b>Score:</b> "
        + str(
            signal.get(
                "score",
                0,
            )
        )
        + "\n"
        "<b>Pattern:</b> "
        + html.escape(
            pattern_text
        )
        + "\n"
        "\n"
        "<b>ENTRY:</b> "
        + str(
            signal.get("entry")
        )
        + "\n"
        "<b>TP:</b> "
        + str(
            signal.get("take_profit")
        )
        + "\n"
        "<b>SL:</b> "
        + str(
            signal.get("stop_loss")
        )
        + "\n"
        "<b>RR:</b> "
        + str(
            signal.get("risk_reward")
        )
        + "\n"
        "<b>Risk ATR:</b> "
        + str(
            signal.get("risk_atr")
        )
        + "\n"
        "\n"
        "<b>Trend:</b> "
        + str(
            signal.get("trend")
        )
        + "\n"
        "<b>Momentum:</b> "
        + str(
            signal.get("momentum")
        )
        + "\n"
        "<b>RSI:</b> "
        + str(
            signal.get("rsi")
        )
        + "\n"
        "<b>ATR:</b> "
        + str(
            signal.get("atr")
        )
        + "\n"
        "\n"
        "<b>Trigger:</b> "
        + str(
            signal.get("trigger")
        )
        + "\n"
        "<b>Time:</b> "
        + html.escape(
            str(
                signal.get("timestamp")
            )
        )
        + "\n"
        "\n"
        "<i>Pattern → Confirmation → "
        "Trigger → Entry → TP/SL</i>"
    )


def maybe_send_signal(signal):

    if signal.get("signal") not in (
        "BUY",
        "SELL",
    ):
        return False

    if not signal.get("valid"):
        return False

    signal_key = (
        str(
            signal.get("timestamp")
        )
        + "_"
        + str(
            signal.get("signal")
        )
        + "_"
        + str(
            signal.get("entry")
        )
    )

    with SIGNAL_LOCK:

        if (
            STATE["last_signal_key"]
            == signal_key
        ):
            return False

        message = format_signal_message(
            signal
        )

        if not message:
            return False

        ok, error = send_telegram(
            message
        )

        if not ok:

            STATE["last_error"] = error

            return False

        STATE["last_signal_key"] = (
            signal_key
        )

        STATE[
            "last_signal_sent_at"
        ] = now_iso()

        print(
            "Telegram trading signal sent successfully"
        )

        return True


# ============================================================
# RUN SIGNAL
# ============================================================

def run_signal(
    send_notification=True,
):

    candles = get_candles()

    signal = analyze_market(
        candles
    )

    STATE["last_update"] = now_iso()

    STATE["last_signal"] = signal

    STATE["last_error"] = None

    if send_notification:
        maybe_send_signal(
            signal
        )

    return signal


# ============================================================
# BACKTEST TRADE EVALUATION
# ============================================================

def evaluate_trade_from_signal(
    candles,
    signal_index,
    signal,
):

    direction = signal.get(
        "signal"
    )

    if direction not in (
        "BUY",
        "SELL",
    ):
        return None

    entry = signal.get("entry")
    stop_loss = signal.get("stop_loss")
    take_profit = signal.get("take_profit")

    if (
        entry is None
        or stop_loss is None
        or take_profit is None
    ):
        return None

    entry = float(entry)
    stop_loss = float(stop_loss)
    take_profit = float(take_profit)

    last_index = min(
        signal_index + FORWARD_BARS,
        len(candles) - 1,
    )

    result = "TIMEOUT"
    exit_reason = "FORWARD_BARS_TIMEOUT"

    exit_price = None
    exit_index = last_index

    mfe = 0.0
    mae = 0.0

    initial_risk = abs(
        entry - stop_loss
    )

    current_sl = stop_loss

    # ========================================================
    # FOLLOW TRADE
    # ========================================================

    for j in range(
        signal_index + 1,
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

            # ------------------------------------------------
            # Break-even
            # ------------------------------------------------

            if (
                ENABLE_BREAK_EVEN
                and initial_risk > 0
                and high >= (
                    entry
                    + initial_risk
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
                and initial_risk > 0
            ):

                atr_now = calculate_atr(
                    candles[
                        max(
                            0,
                            j - ATR_PERIOD - 1
                        ): j + 1
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
            # SL first if both occur in same candle
            if hit_sl and hit_tp:

                result = "LOSS"

                exit_reason = (
                    "SL_AND_TP_SAME_CANDLE"
                )

                exit_price = current_sl

                exit_index = j

                break

            if hit_sl:

                # If SL moved to entry
                if current_sl >= entry:

                    result = "BREAKEVEN"

                    exit_reason = "BREAK_EVEN"

                else:

                    result = "LOSS"

                    exit_reason = "STOP_LOSS"

                exit_price = current_sl

                exit_index = j

                break

            if hit_tp:

                result = "WIN"

                exit_reason = "TAKE_PROFIT"

                exit_price = take_profit

                exit_index = j

                break

        # ====================================================
        # SELL
        # ====================================================

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

            # ------------------------------------------------
            # Break-even
            # ------------------------------------------------

            if (
                ENABLE_BREAK_EVEN
                and initial_risk > 0
                and low <= (
                    entry
                    - initial_risk
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
                and initial_risk > 0
            ):

                atr_now = calculate_atr(
                    candles[
                        max(
                            0,
                            j - ATR_PERIOD - 1
                        ): j + 1
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

                result = "LOSS"

                exit_reason = (
                    "SL_AND_TP_SAME_CANDLE"
                )

                exit_price = current_sl

                exit_index = j

                break

            if hit_sl:

                if current_sl <= entry:

                    result = "BREAKEVEN"

                    exit_reason = "BREAK_EVEN"

                else:

                    result = "LOSS"

                    exit_reason = "STOP_LOSS"

                exit_price = current_sl

                exit_index = j

                break

            if hit_tp:

                result = "WIN"

                exit_reason = "TAKE_PROFIT"

                exit_price = take_profit

                exit_index = j

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

        pnl_percent = (
            exit_price
            - entry
        ) / entry * 100.0

    else:

        pnl_percent = (
            entry
            - exit_price
        ) / entry * 100.0

    # ========================================================
    # R MULTIPLE
    # ========================================================

    if initial_risk > 0:

        if direction == "BUY":

            r_multiple = (
                exit_price
                - entry
            ) / initial_risk

        else:

            r_multiple = (
                entry
                - exit_price
            ) / initial_risk

    else:

        r_multiple = 0.0

    return {
        "timestamp": candles[
            signal_index
        ]["datetime"],

        "signal": direction,

        "patterns": signal.get(
            "patterns",
            [],
        ),

        "score": round(
            float(
                signal.get(
                    "score",
                    0,
                )
            ),
            2,
        ),

        "entry": round_price(entry),

        "stop_loss": round_price(
            stop_loss
        ),

        "take_profit": round_price(
            take_profit
        ),

        "risk_reward": signal.get(
            "risk_reward",
            0,
        ),

        "result": result,

        "exit_reason": exit_reason,

        "exit_price": round_price(
            exit_price
        ),

        "pnl_percent": round(
            pnl_percent,
            4,
        ),

        "r_multiple": round(
            r_multiple,
            4,
        ),

        "mfe_percent": round(
            mfe,
            4,
        ),

        "mae_percent": round(
            mae,
            4,
        ),

        "bars_held": (
            exit_index
            - signal_index
        ),
    }


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(points=None):

    candles = get_candles()

    total_candles = len(candles)

    if points is None:
        points = BACKTEST_POINTS

    points = int(
        clamp(
            points,
            50,
            total_candles - 100,
        )
    )

    minimum_start = max(
        EMA_SLOW + 10,
        80,
    )

    end = (
        total_candles
        - FORWARD_BARS
        - 1
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

    candidate_count = 0
    confirmation_count = 0
    trigger_count = 0

    # ========================================================
    # WALK FORWARD
    # ========================================================

    i = start

    while i < end:

        historical = candles[
            : i + 1
        ]

        signal = analyze_market(
            historical
        )

        patterns = signal.get(
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

        if signal.get(
            "candidate_direction"
        ):
            candidate_count += 1

        confirmation = signal.get(
            "confirmation"
        )

        if confirmation:

            if (
                confirmation.get(
                    "score",
                    0,
                )
                >= MIN_SCORE
            ):
                confirmation_count += 1

        if signal.get(
            "triggered"
        ):
            trigger_count += 1

        trade = (
            evaluate_trade_from_signal(
                candles,
                i,
                signal,
            )
        )

        if trade is not None:

            trade_results.append(
                trade
            )

            # ------------------------------------------------
            # IMPORTANT:
            # ไม่เปิด trade ใหม่จนกว่า
            # trade ปัจจุบันจะจบ
            # ------------------------------------------------

            bars_held = max(
                1,
                trade["bars_held"],
            )

            i += bars_held

        else:

            i += 1

    # ========================================================
    # COUNTS
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
    # RESOLVED
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

        win_rate_resolved = (
            wins
            / resolved
            * 100.0
        )

        loss_rate_resolved = (
            losses
            / resolved
            * 100.0
        )

    else:

        win_rate_resolved = 0.0
        loss_rate_resolved = 0.0

    if signals:

        expectancy = (
            net_profit
            / signals
        )

    else:

        expectancy = 0.0

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

        if trade["result"] == "LOSS":

            current_losing_streak += 1

            longest_losing_streak = max(
                longest_losing_streak,
                current_losing_streak,
            )

        else:

            current_losing_streak = 0

    # ========================================================
    # MFE / MAE / SCORE / R
    # ========================================================

    mfe_values = [
        x["mfe_percent"]
        for x in trade_results
    ]

    mae_values = [
        x["mae_percent"]
        for x in trade_results
    ]

    score_values = [
        x["score"]
        for x in trade_results
    ]

    r_values = [
        x["r_multiple"]
        for x in trade_results
    ]

    avg_mfe = (
        sum(mfe_values)
        / len(mfe_values)
        if mfe_values
        else 0.0
    )

    avg_mae = (
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

    avg_r = (
        sum(r_values)
        / len(r_values)
        if r_values
        else 0.0
    )

    # ========================================================
    # BUY / SELL PERFORMANCE
    # ========================================================

    buy_trades = [
        x
        for x in trade_results
        if x["signal"] == "BUY"
    ]

    sell_trades = [
        x
        for x in trade_results
        if x["signal"] == "SELL"
    ]

    def direction_stats(trades):

        if not trades:

            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "timeouts": 0,
                "net_profit_percent": 0.0,
                "win_rate_percent": 0.0,
            }

        wins_local = sum(
            1
            for x in trades
            if x["result"] == "WIN"
        )

        losses_local = sum(
            1
            for x in trades
            if x["result"] == "LOSS"
        )

        timeout_local = sum(
            1
            for x in trades
            if x["result"] == "TIMEOUT"
        )

        pnl_local = sum(
            x["pnl_percent"]
            for x in trades
        )

        return {
            "trades": len(trades),

            "wins": wins_local,

            "losses": losses_local,

            "timeouts": timeout_local,

            "net_profit_percent": round(
                pnl_local,
                4,
            ),

            "win_rate_percent": round(
                wins_local
                / len(trades)
                * 100.0,
                2,
            ),
        }

    buy_stats = direction_stats(
        buy_trades
    )

    sell_stats = direction_stats(
        sell_trades
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "status": "completed",

        "symbol": SYMBOL,

        "timeframe": "M5",

        "system": (
            "Pattern Recognition"
        ),

        "architecture": [
            "Pattern Recognition",
            "Directional Filter",
            "Confirmation",
            "Trigger",
            "Entry",
            "ATR TP/SL",
            "Trade Management",
            "Telegram",
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

            "break_even": ENABLE_BREAK_EVEN,

            "break_even_r": BREAK_EVEN_R,

            "trailing": ENABLE_TRAILING,

            "trailing_atr": TRAILING_ATR,
        },

        "pipeline_counts": {
            "pattern_candidates": (
                candidate_count
            ),

            "confirmation_passed": (
                confirmation_count
            ),

            "triggered": (
                trigger_count
            ),

            "executed_trades": (
                signals
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

            "win_rate_on_resolved_percent": round(
                win_rate_resolved,
                2,
            ),

            "loss_rate_on_resolved_percent": round(
                loss_rate_resolved,
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

            "expectancy_percent": round(
                expectancy,
                4,
            ),

            "max_drawdown_percent": round(
                max_drawdown,
                4,
            ),

            "average_mfe_percent": round(
                avg_mfe,
                4,
            ),

            "average_mae_percent": round(
                avg_mae,
                4,
            ),

            "average_score": round(
                avg_score,
                2,
            ),

            "average_r_multiple": round(
                avg_r,
                4,
            ),

            "longest_losing_streak": (
                longest_losing_streak
            ),
        },

        "direction_performance": {
            "BUY": buy_stats,
            "SELL": sell_stats,
        },

        "pattern_frequency": (
            pattern_frequency
        ),

        "recent_trades": (
            trade_results[-20:]
        ),

        "warning": (
            "Historical simulation only. "
            "Spread, slippage, execution delay, "
            "broker-specific pricing and "
            "intrabar tick sequence are not "
            "included. Same-candle TP/SL is "
            "handled conservatively as SL."
        ),
    }


# ============================================================
# ROOT
# ============================================================

@app.route("/")
def home():

    return jsonify(
        {
            "name": (
                "XAUUSD M5 Pattern "
                "Recognition Bot"
            ),

            "status": "online",

            "system": (
                "Pattern Recognition"
            ),

            "architecture": [
                "Pattern Recognition",
                "Directional Filter",
                "Confirmation",
                "Trigger",
                "Entry",
                "ATR TP/SL",
                "Trade Management",
                "Telegram",
            ],

            "symbol": SYMBOL,

            "timeframe": "M5",

            "data_source": "Twelve Data",

            "telegram": bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

            "patterns": PATTERNS,

            "rules": {
                "minimum_atr": MIN_ATR,

                "minimum_score": MIN_SCORE,

                "minimum_risk_reward": (
                    MIN_RISK_REWARD
                ),

                "risk_reward": RISK_REWARD,

                "forward_bars": FORWARD_BARS,

                "min_stop_atr": MIN_STOP_ATR,

                "max_stop_atr": MAX_STOP_ATR,
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

            "score": {
                "pattern": 20,
                "trend": 20,
                "momentum": 15,
                "rsi": 10,
                "location": 10,
                "volatility": 10,
                "trigger": 15,
                "maximum": 100,
            },

            "risk": {
                "risk_reward": RISK_REWARD,
                "minimum_risk_reward": MIN_RISK_REWARD,
                "min_stop_atr": MIN_STOP_ATR,
                "max_stop_atr": MAX_STOP_ATR,
            },

            "trade_management": {
                "forward_bars": FORWARD_BARS,
                "break_even": ENABLE_BREAK_EVEN,
                "break_even_r": BREAK_EVEN_R,
                "trailing": ENABLE_TRAILING,
                "trailing_atr": TRAILING_ATR,
            },

            "direction_filter": {
                "conflicting_patterns": (
                    "NO_TRADE"
                ),
                "sideways_trend": (
                    "NO_TRADE"
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
                "Pattern Recognition"
            ),

            "symbol": SYMBOL,

            "timeframe": "M5",

            "data_source": "Twelve Data",

            "twelve_data": bool(
                TWELVE_DATA_API_KEY
            ),

            "telegram": bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

            "startup_notification_sent": (
                STATE["startup_sent"]
            ),

            "last_update": (
                STATE["last_update"]
            ),

            "last_signal": (
                STATE["last_signal"]
            ),

            "last_signal_sent_at": (
                STATE[
                    "last_signal_sent_at"
                ]
            ),

            "last_error": (
                STATE["last_error"]
            ),
        }
    )


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

        if not STATE["startup_sent"]:

            send_startup_notification()

        signal = run_signal(
            send_notification=True
        )

        return jsonify(
            signal
        )

    except Exception as exc:

        STATE["last_error"] = str(
            exc
        )

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

        STATE["last_error"] = str(
            exc
        )

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
        "<b>System:</b> Pattern Recognition\n"
        "<b>Pipeline:</b>\n"
        "Pattern → Direction → Confirmation\n"
        "→ Trigger → Entry → TP/SL\n"
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
# BACKTEST
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

            points = BACKTEST_POINTS

        result = run_backtest(
            points=points
        )

        return jsonify(
            result
        )

    except Exception as exc:

        STATE["last_error"] = str(
            exc
        )

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

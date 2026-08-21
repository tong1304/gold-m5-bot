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

FORWARD_BARS = 12

# ------------------------------------------------------------
# ENTRY / TRIGGER
# ------------------------------------------------------------

MIN_SCORE = 70.0

MIN_ATR = 0.50

MIN_RISK_REWARD = 1.30

ATR_PERIOD = 14

EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14

TRIGGER_LOOKBACK = 3

SWING_LOOKBACK = 5

SR_LOOKBACK = 50

# Maximum stop distance in ATR.
# If the natural structural stop is farther than this,
# the trade is rejected instead of using an excessively
# wide stop.
MAX_STOP_ATR = 2.50

# Small ATR buffer behind structural swing.
STOP_BUFFER_ATR = 0.10

# Minimum candle body size relative to ATR for breakout trigger.
MIN_TRIGGER_BODY_ATR = 0.05


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
    if not values:
        return 0.0

    if len(values) < period:
        return sum(values) / len(values)

    multiplier = 2.0 / (period + 1.0)

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


def get_ema(candles, period):
    values = [
        candle["close"]
        for candle in candles
    ]

    return calculate_ema(
        values,
        period,
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=ATR_PERIOD,
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

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        true_ranges.append(tr)

    recent = true_ranges[-period:]

    if not recent:
        return 0.0

    return sum(recent) / len(recent)


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    candles,
    period=RSI_PERIOD,
):
    if len(candles) <= period:
        return 50.0

    closes = [
        candle["close"]
        for candle in candles
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
        if average_gain > 0:
            return 100.0
        return 50.0

    rs = (
        average_gain
        / average_loss
    )

    return 100.0 - (
        100.0
        / (1.0 + rs)
    )


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


def bullish(candle):
    return candle["close"] > candle["open"]


def bearish(candle):
    return candle["close"] < candle["open"]


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_support_resistance(
    candles,
    lookback=SR_LOOKBACK,
):
    if len(candles) < 10:
        return (
            candles[-1]["low"],
            candles[-1]["high"],
        )

    recent = candles[
        -lookback:
    ]

    support = min(
        candle["low"]
        for candle in recent
    )

    resistance = max(
        candle["high"]
        for candle in recent
    )

    return (
        support,
        resistance,
    )


# ============================================================
# TREND
# ============================================================

def detect_trend(
    candles,
    ema20=None,
    ema50=None,
):
    if ema20 is None:
        ema20 = get_ema(
            candles,
            EMA_FAST,
        )

    if ema50 is None:
        ema50 = get_ema(
            candles,
            EMA_SLOW,
        )

    close = candles[-1]["close"]

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

def detect_momentum(candles):
    if len(candles) < 5:
        return "NEUTRAL"

    closes = [
        candle["close"]
        for candle in candles[-5:]
    ]

    if closes[-1] > closes[0]:
        return "BULLISH"

    if closes[-1] < closes[0]:
        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# PATTERN: BULLISH ENGULFING
# ============================================================

def is_bullish_engulfing(candles):
    if len(candles) < 2:
        return False

    a = candles[-2]
    b = candles[-1]

    return (
        bearish(a)
        and bullish(b)
        and b["open"] <= a["close"]
        and b["close"] >= a["open"]
        and candle_body(b) >= candle_body(a) * 0.8
    )


# ============================================================
# PATTERN: BEARISH ENGULFING
# ============================================================

def is_bearish_engulfing(candles):
    if len(candles) < 2:
        return False

    a = candles[-2]
    b = candles[-1]

    return (
        bullish(a)
        and bearish(b)
        and b["open"] >= a["close"]
        and b["close"] <= a["open"]
        and candle_body(b) >= candle_body(a) * 0.8
    )


# ============================================================
# PATTERN: HAMMER
# ============================================================

def is_hammer(candles):
    if len(candles) < 1:
        return False

    c = candles[-1]

    body = candle_body(c)
    total_range = candle_range(c)

    if total_range <= 0:
        return False

    lower = lower_wick(c)
    upper = upper_wick(c)

    return (
        lower >= body * 2.0
        and upper <= body
        and body / total_range <= 0.45
    )


# ============================================================
# PATTERN: SHOOTING STAR
# ============================================================

def is_shooting_star(candles):
    if len(candles) < 1:
        return False

    c = candles[-1]

    body = candle_body(c)
    total_range = candle_range(c)

    if total_range <= 0:
        return False

    upper = upper_wick(c)
    lower = lower_wick(c)

    return (
        upper >= body * 2.0
        and lower <= body
        and body / total_range <= 0.45
    )


# ============================================================
# PATTERN: MORNING STAR
# ============================================================

def is_morning_star(candles):
    if len(candles) < 3:
        return False

    a = candles[-3]
    b = candles[-2]
    c = candles[-1]

    body_a = candle_body(a)
    body_b = candle_body(b)

    midpoint_a = (
        a["open"]
        + a["close"]
    ) / 2.0

    return (
        bearish(a)
        and body_a > 0
        and body_b <= body_a * 0.5
        and bullish(c)
        and c["close"] > midpoint_a
    )


# ============================================================
# PATTERN: EVENING STAR
# ============================================================

def is_evening_star(candles):
    if len(candles) < 3:
        return False

    a = candles[-3]
    b = candles[-2]
    c = candles[-1]

    body_a = candle_body(a)
    body_b = candle_body(b)

    midpoint_a = (
        a["open"]
        + a["close"]
    ) / 2.0

    return (
        bullish(a)
        and body_a > 0
        and body_b <= body_a * 0.5
        and bearish(c)
        and c["close"] < midpoint_a
    )


# ============================================================
# PATTERN: BREAKOUT
# ============================================================

def is_bullish_breakout(
    candles,
    lookback=10,
):
    if len(candles) <= lookback:
        return False

    current = candles[-1]

    previous = candles[
        -lookback - 1:-1
    ]

    previous_high = max(
        candle["high"]
        for candle in previous
    )

    return (
        current["close"]
        > previous_high
    )


def is_bearish_breakout(
    candles,
    lookback=10,
):
    if len(candles) <= lookback:
        return False

    current = candles[-1]

    previous = candles[
        -lookback - 1:-1
    ]

    previous_low = min(
        candle["low"]
        for candle in previous
    )

    return (
        current["close"]
        < previous_low
    )


# ============================================================
# PATTERN: PULLBACK
# ============================================================

def is_pullback_buy(
    candles,
    ema20,
):
    if len(candles) < 5:
        return False

    recent = candles[-4:]

    lowest = min(
        c["low"]
        for c in recent
    )

    close = candles[-1]["close"]

    return (
        lowest <= ema20 * 1.003
        and close > ema20
    )


def is_pullback_sell(
    candles,
    ema20,
):
    if len(candles) < 5:
        return False

    recent = candles[-4:]

    highest = max(
        c["high"]
        for c in recent
    )

    close = candles[-1]["close"]

    return (
        highest >= ema20 * 0.997
        and close < ema20
    )


# ============================================================
# PATTERN: DOUBLE BOTTOM
# ============================================================

def is_double_bottom(candles):
    if len(candles) < 20:
        return False

    recent = candles[-20:]

    lows = [
        c["low"]
        for c in recent
    ]

    low1 = min(lows[:10])
    low2 = min(lows[10:])

    tolerance = max(
        abs(low1),
        1.0
    ) * 0.0015

    return (
        abs(low1 - low2)
        <= tolerance
        and candles[-1]["close"]
        > candles[-1]["open"]
    )


# ============================================================
# PATTERN: DOUBLE TOP
# ============================================================

def is_double_top(candles):
    if len(candles) < 20:
        return False

    recent = candles[-20:]

    highs = [
        c["high"]
        for c in recent
    ]

    high1 = max(highs[:10])
    high2 = max(highs[10:])

    tolerance = max(
        abs(high1),
        1.0
    ) * 0.0015

    return (
        abs(high1 - high2)
        <= tolerance
        and candles[-1]["close"]
        < candles[-1]["open"]
    )


# ============================================================
# PATTERN RECOGNITION
# ============================================================

def detect_patterns(candles):
    ema20 = get_ema(
        candles,
        EMA_FAST,
    )

    patterns = []
    directions = []

    if is_bullish_engulfing(candles):
        patterns.append(
            "Bullish Engulfing"
        )
        directions.append("BUY")

    if is_bearish_engulfing(candles):
        patterns.append(
            "Bearish Engulfing"
        )
        directions.append("SELL")

    if is_hammer(candles):
        patterns.append("Hammer")
        directions.append("BUY")

    if is_shooting_star(candles):
        patterns.append(
            "Shooting Star"
        )
        directions.append("SELL")

    if is_morning_star(candles):
        patterns.append(
            "Morning Star"
        )
        directions.append("BUY")

    if is_evening_star(candles):
        patterns.append(
            "Evening Star"
        )
        directions.append("SELL")

    if is_bullish_breakout(candles):
        patterns.append(
            "Bullish Breakout"
        )
        directions.append("BUY")

    if is_bearish_breakout(candles):
        patterns.append(
            "Bearish Breakout"
        )
        directions.append("SELL")

    if is_pullback_buy(
        candles,
        ema20,
    ):
        patterns.append("Pullback")
        directions.append("BUY")

    elif is_pullback_sell(
        candles,
        ema20,
    ):
        patterns.append("Pullback")
        directions.append("SELL")

    if is_double_bottom(candles):
        patterns.append(
            "Double Bottom"
        )
        directions.append("BUY")

    if is_double_top(candles):
        patterns.append(
            "Double Top"
        )
        directions.append("SELL")

    buy_count = directions.count("BUY")
    sell_count = directions.count("SELL")

    if buy_count > sell_count:
        candidate = "BUY"
    elif sell_count > buy_count:
        candidate = "SELL"
    else:
        candidate = "NO_TRADE"

    return {
        "patterns": patterns,
        "directions": directions,
        "candidate_direction": candidate,
    }


# ============================================================
# CONFIRMATION
# ============================================================

def confirmation_engine(
    candles,
    pattern_data,
):
    atr = calculate_atr(candles)

    ema20 = get_ema(
        candles,
        EMA_FAST,
    )

    ema50 = get_ema(
        candles,
        EMA_SLOW,
    )

    rsi = calculate_rsi(candles)

    trend = detect_trend(
        candles,
        ema20,
        ema50,
    )

    momentum = detect_momentum(
        candles
    )

    support, resistance = (
        calculate_support_resistance(
            candles
        )
    )

    direction = pattern_data[
        "candidate_direction"
    ]

    patterns = pattern_data[
        "patterns"
    ]

    score = 0.0

    reasons = []

    # --------------------------------------------------------
    # PATTERN
    # --------------------------------------------------------

    if patterns:
        score += 25.0

        reasons.append(
            f"{len(patterns)} pattern(s) detected"
        )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    trend_ok = False

    if direction == "BUY":
        trend_ok = trend == "UPTREND"

    elif direction == "SELL":
        trend_ok = trend == "DOWNTREND"

    if trend_ok:
        score += 20.0

        reasons.append(
            "Aligned with trend"
        )
    else:
        reasons.append(
            "Trend not aligned"
        )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum_ok = False

    if direction == "BUY":
        momentum_ok = momentum == "BULLISH"

    elif direction == "SELL":
        momentum_ok = momentum == "BEARISH"

    if momentum_ok:
        score += 15.0

        reasons.append(
            "Momentum confirmed"
        )
    else:
        reasons.append(
            "Momentum not confirmed"
        )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi_ok = False

    if direction == "BUY":
        rsi_ok = (
            rsi >= 45
            and rsi < 70
        )

    elif direction == "SELL":
        rsi_ok = (
            rsi <= 55
            and rsi > 30
        )

    if rsi_ok:
        score += 10.0

        reasons.append(
            "RSI supports direction"
        )
    else:
        reasons.append(
            "RSI does not support direction"
        )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    close = candles[-1]["close"]

    location_ok = False

    if direction == "BUY":
        location_ok = (
            close > support
            and close < resistance
        )

    elif direction == "SELL":
        location_ok = (
            close > support
            and close < resistance
        )

    if location_ok:
        score += 10.0

        reasons.append(
            "Price location acceptable"
        )
    else:
        reasons.append(
            "Price location poor"
        )

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    volatility_ok = (
        atr >= MIN_ATR
    )

    if volatility_ok:
        score += 5.0

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

    trigger = detect_trigger(
        candles,
        direction,
        atr,
    )

    trigger_ok = trigger[
        "triggered"
    ]

    if trigger_ok:
        score += 15.0

        reasons.append(
            "Price trigger confirmed"
        )
    else:
        reasons.append(
            "Waiting for price trigger"
        )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    valid = (
        direction in [
            "BUY",
            "SELL",
        ]
        and score >= MIN_SCORE
        and atr >= MIN_ATR
        and trigger_ok
        and trend_ok
        and momentum_ok
        and rsi_ok
    )

    return {
        "direction": direction,
        "score": round(score, 2),
        "valid": valid,
        "checks": {
            "pattern": bool(patterns),
            "trend": trend_ok,
            "momentum": momentum_ok,
            "rsi": rsi_ok,
            "location": location_ok,
            "volatility": volatility_ok,
            "trigger": trigger_ok,
        },
        "reasons": reasons,
        "trend": trend,
        "momentum": momentum,
        "rsi": round(rsi, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "atr": round(atr, 4),
        "support": round(support, 2),
        "resistance": round(
            resistance,
            2,
        ),
        "trigger": trigger,
    }


# ============================================================
# TRIGGER ENGINE
# ============================================================

def detect_trigger(
    candles,
    direction,
    atr,
):
    if len(candles) < 3:
        return {
            "triggered": False,
            "price": None,
            "level": None,
            "type": None,
        }

    current = candles[-1]

    previous = candles[-2]

    recent = candles[
        -TRIGGER_LOOKBACK - 1:-1
    ]

    previous_high = max(
        candle["high"]
        for candle in recent
    )

    previous_low = min(
        candle["low"]
        for candle in recent
    )

    body = candle_body(current)

    strong_body = (
        body
        >= atr * MIN_TRIGGER_BODY_ATR
    )

    if direction == "BUY":

        level = max(
            previous_high,
            previous["high"],
        )

        triggered = (
            current["close"]
            > level
            and bullish(current)
            and strong_body
        )

        return {
            "triggered": triggered,
            "price": (
                current["close"]
                if triggered
                else None
            ),
            "level": round_price(level),
            "type": "BREAK_HIGH",
        }

    if direction == "SELL":

        level = min(
            previous_low,
            previous["low"],
        )

        triggered = (
            current["close"]
            < level
            and bearish(current)
            and strong_body
        )

        return {
            "triggered": triggered,
            "price": (
                current["close"]
                if triggered
                else None
            ),
            "level": round_price(level),
            "type": "BREAK_LOW",
        }

    return {
        "triggered": False,
        "price": None,
        "level": None,
        "type": None,
    }


# ============================================================
# STRUCTURAL STOP
# ============================================================

def calculate_stop_loss(
    candles,
    direction,
    entry,
    atr,
):
    if len(candles) < SWING_LOOKBACK:
        return None

    recent = candles[
        -SWING_LOOKBACK:
    ]

    buffer = (
        atr
        * STOP_BUFFER_ATR
    )

    if direction == "BUY":

        swing_low = min(
            c["low"]
            for c in recent
        )

        stop = (
            swing_low
            - buffer
        )

        if stop >= entry:
            stop = (
                entry
                - atr
            )

        return stop

    if direction == "SELL":

        swing_high = max(
            c["high"]
            for c in recent
        )

        stop = (
            swing_high
            + buffer
        )

        if stop <= entry:
            stop = (
                entry
                + atr
            )

        return stop

    return None


# ============================================================
# TP / SL
# ============================================================

def calculate_trade_levels(
    candles,
    direction,
    entry,
    atr,
):
    if atr <= 0:
        return {
            "valid": False,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk": 0.0,
            "reward": 0.0,
            "risk_reward": 0.0,
            "reason": "Invalid ATR",
        }

    stop_loss = calculate_stop_loss(
        candles,
        direction,
        entry,
        atr,
    )

    if stop_loss is None:
        return {
            "valid": False,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk": 0.0,
            "reward": 0.0,
            "risk_reward": 0.0,
            "reason": "Unable to calculate structural stop",
        }

    risk = abs(
        entry
        - stop_loss
    )

    if risk <= 0:
        return {
            "valid": False,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk": 0.0,
            "reward": 0.0,
            "risk_reward": 0.0,
            "reason": "Invalid risk distance",
        }

    max_risk = (
        atr
        * MAX_STOP_ATR
    )

    if risk > max_risk:
        return {
            "valid": False,
            "entry": round_price(entry),
            "stop_loss": round_price(stop_loss),
            "take_profit": None,
            "risk": round(risk, 4),
            "reward": 0.0,
            "risk_reward": 0.0,
            "reason": "Stop distance exceeds maximum ATR risk",
        }

    reward = (
        risk
        * MIN_RISK_REWARD
    )

    if direction == "BUY":

        take_profit = (
            entry
            + reward
        )

    elif direction == "SELL":

        take_profit = (
            entry
            - reward
        )

    else:
        return {
            "valid": False,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk": 0.0,
            "reward": 0.0,
            "risk_reward": 0.0,
            "reason": "Invalid direction",
        }

    risk_reward = (
        reward
        / risk
    )

    if risk_reward < MIN_RISK_REWARD:
        return {
            "valid": False,
            "entry": round_price(entry),
            "stop_loss": round_price(stop_loss),
            "take_profit": round_price(take_profit),
            "risk": round(risk, 4),
            "reward": round(reward, 4),
            "risk_reward": round(
                risk_reward,
                2,
            ),
            "reason": "Risk reward below minimum",
        }

    return {
        "valid": True,
        "entry": round_price(entry),
        "stop_loss": round_price(stop_loss),
        "take_profit": round_price(take_profit),
        "risk": round(risk, 4),
        "reward": round(reward, 4),
        "risk_reward": round(
            risk_reward,
            2,
        ),
        "reason": "Valid",
    }


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(candles):
    if len(candles) < 100:
        raise RuntimeError(
            "Not enough candles for signal engine"
        )

    latest = candles[-1]

    pattern_data = detect_patterns(
        candles
    )

    confirmation = confirmation_engine(
        candles,
        pattern_data,
    )

    direction = pattern_data[
        "candidate_direction"
    ]

    patterns = pattern_data[
        "patterns"
    ]

    atr = confirmation["atr"]

    entry = None
    stop_loss = None
    take_profit = None
    risk_reward = 0.0

    # --------------------------------------------------------
    # NO PATTERN
    # --------------------------------------------------------

    if not patterns:
        return {
            "status": "NO_PATTERN",
            "signal": "NO_TRADE",
            "timestamp": latest["datetime"],
            "symbol": SYMBOL,
            "timeframe": "M5",
            "patterns": [],
            "directional_patterns": [],
            "candidate_direction": "NO_TRADE",
            "score": 0.0,
            "confirmation": confirmation,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": 0.0,
            "atr": round(atr, 4),
            "method": (
                "Pattern Recognition + "
                "Confirmation + Trigger + Entry"
            ),
            "data_source": "Twelve Data XAU/USD",
        }

    # --------------------------------------------------------
    # PATTERN FOUND BUT NOT CONFIRMED
    # --------------------------------------------------------

    if not confirmation["valid"]:
        return {
            "status": "PATTERN_DETECTED",
            "signal": "WAIT_CONFIRMATION",
            "timestamp": latest["datetime"],
            "symbol": SYMBOL,
            "timeframe": "M5",
            "patterns": patterns,
            "directional_patterns": [
                p
                for p, d in zip(
                    patterns,
                    pattern_data["directions"],
                )
                if d == direction
            ],
            "candidate_direction": direction,
            "score": confirmation["score"],
            "confirmation": confirmation,
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": 0.0,
            "atr": round(atr, 4),
            "method": (
                "Pattern Recognition + "
                "Confirmation + Trigger + Entry"
            ),
            "data_source": "Twelve Data XAU/USD",
        }

    # --------------------------------------------------------
    # TRIGGER CONFIRMED
    # --------------------------------------------------------

    trigger_price = confirmation[
        "trigger"
    ]["price"]

    levels = calculate_trade_levels(
        candles,
        direction,
        trigger_price,
        atr,
    )

    if not levels["valid"]:
        return {
            "status": "TRIGGER_REJECTED",
            "signal": "NO_TRADE",
            "timestamp": latest["datetime"],
            "symbol": SYMBOL,
            "timeframe": "M5",
            "patterns": patterns,
            "directional_patterns": [
                p
                for p, d in zip(
                    patterns,
                    pattern_data["directions"],
                )
                if d == direction
            ],
            "candidate_direction": direction,
            "score": confirmation["score"],
            "confirmation": confirmation,
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "take_profit": levels["take_profit"],
            "risk_reward": levels["risk_reward"],
            "atr": round(atr, 4),
            "reason": levels["reason"],
            "method": (
                "Pattern Recognition + "
                "Confirmation + Trigger + Entry"
            ),
            "data_source": "Twelve Data XAU/USD",
        }

    # --------------------------------------------------------
    # REAL SIGNAL
    # --------------------------------------------------------

    entry = levels["entry"]
    stop_loss = levels["stop_loss"]
    take_profit = levels["take_profit"]
    risk_reward = levels["risk_reward"]

    return {
        "status": "ENTRY_CONFIRMED",
        "signal": direction,
        "timestamp": latest["datetime"],
        "symbol": SYMBOL,
        "timeframe": "M5",
        "patterns": patterns,
        "directional_patterns": [
            p
            for p, d in zip(
                patterns,
                pattern_data["directions"],
            )
            if d == direction
        ],
        "candidate_direction": direction,
        "score": confirmation["score"],
        "confirmation": confirmation,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward": risk_reward,
        "atr": round(atr, 4),
        "method": (
            "Pattern Recognition + "
            "Confirmation + Trigger + Entry"
        ),
        "data_source": "Twelve Data XAU/USD",
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

        if not result.get("ok"):
            return (
                False,
                result.get(
                    "description",
                    "Telegram API error",
                ),
            )

        return True, None

    except Exception as exc:
        return False, str(exc)


# ============================================================
# TELEGRAM STARTUP
# ============================================================

def send_startup_notification():
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
        "<b>Architecture</b>\n"
        "Pattern Recognition\n"
        "→ Confirmation\n"
        "→ Trigger\n"
        "→ Entry\n"
        "→ TP/SL\n"
        "→ Telegram\n"
        "\n"
        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"
        "<b>Data:</b> Twelve Data\n"
        "\n"
        f"<b>Minimum Score:</b> {MIN_SCORE:.0f}\n"
        f"<b>Minimum ATR:</b> {MIN_ATR:.2f}\n"
        f"<b>Minimum R:R:</b> {MIN_RISK_REWARD:.2f}\n"
        f"<b>Max Stop ATR:</b> {MAX_STOP_ATR:.2f}\n"
        "\n"
        "<b>Entry Rule:</b>\n"
        "Pattern + Confirmation + Trigger\n"
        "\n"
        "ระบบพร้อมวิเคราะห์ตลาด"
    )

    ok, error = send_telegram(
        message
    )

    if ok:
        STATE["startup_sent"] = True

        print(
            "Telegram startup notification sent successfully"
        )

        return True

    print(
        "Telegram startup notification failed:",
        error,
    )

    return False


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def format_signal_message(signal):
    direction = signal.get(
        "signal"
    )

    if direction not in [
        "BUY",
        "SELL",
    ]:
        return None

    emoji = (
        "🟢"
        if direction == "BUY"
        else "🔴"
    )

    confirmation = signal[
        "confirmation"
    ]

    patterns = ", ".join(
        signal["patterns"]
    )

    return (
        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"
        f"<b>SIGNAL:</b> {direction}\n"
        f"<b>Pattern:</b> {patterns}\n"
        "\n"
        "<b>CONFIRMATION</b>\n"
        f"Trend: {confirmation['trend']}\n"
        f"Momentum: {confirmation['momentum']}\n"
        f"RSI: {confirmation['rsi']:.2f}\n"
        f"Score: {signal['score']:.2f}\n"
        "\n"
        "<b>TRIGGER</b>\n"
        f"Type: {confirmation['trigger']['type']}\n"
        f"Level: {confirmation['trigger']['level']:.2f}\n"
        "\n"
        "<b>TRADE</b>\n"
        f"ENTRY: {signal['entry']:.2f}\n"
        f"SL: {signal['stop_loss']:.2f}\n"
        f"TP: {signal['take_profit']:.2f}\n"
        f"R:R: 1:{signal['risk_reward']:.2f}\n"
        "\n"
        f"<b>ATR:</b> {signal['atr']:.4f}\n"
        f"<b>Time:</b> {signal['timestamp']}\n"
        "\n"
        "<i>Pattern → Confirmation → "
        "Trigger → Entry</i>"
    )


# ============================================================
# TELEGRAM WAIT MESSAGE
# ============================================================

def format_wait_message(signal):
    if signal.get("signal") != "WAIT_CONFIRMATION":
        return None

    patterns = ", ".join(
        signal.get(
            "patterns",
            [],
        )
    )

    confirmation = signal[
        "confirmation"
    ]

    return (
        "🟡 <b>XAUUSD M5</b>\n"
        "\n"
        "<b>PATTERN DETECTED</b>\n"
        f"Pattern: {patterns}\n"
        f"Direction: {signal['candidate_direction']}\n"
        "\n"
        f"Trend: {confirmation['trend']}\n"
        f"Momentum: {confirmation['momentum']}\n"
        f"RSI: {confirmation['rsi']:.2f}\n"
        f"Score: {confirmation['score']:.2f}\n"
        "\n"
        f"<b>Trigger:</b> "
        f"{'PASSED' if confirmation['trigger']['triggered'] else 'WAITING'}\n"
        "\n"
        "<b>STATUS:</b> WAIT_CONFIRMATION"
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
    # TELEGRAM ONLY FOR REAL ENTRY
    # --------------------------------------------------------

    if (
        send_notification
        and signal["signal"]
        in [
            "BUY",
            "SELL",
        ]
    ):
        signal_key = (
            str(signal["timestamp"])
            + "_"
            + signal["signal"]
        )

        if (
            STATE["last_signal_key"]
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
                    STATE["last_error"] = error

            STATE["last_signal_key"] = (
                signal_key
            )

    STATE["last_signal"] = signal

    return signal


# ============================================================
# BACKTEST SINGLE TRADE
# ============================================================

def simulate_trade(
    candles,
    entry_index,
    signal,
):
    direction = signal["signal"]

    entry = float(
        signal["entry"]
    )

    stop_loss = float(
        signal["stop_loss"]
    )

    take_profit = float(
        signal["take_profit"]
    )

    end_index = min(
        entry_index
        + FORWARD_BARS,
        len(candles) - 1,
    )

    result = "TIME_EXIT"

    exit_price = None
    exit_index = None

    mfe = 0.0
    mae = 0.0

    # IMPORTANT:
    # Entry candle is NOT checked for TP/SL.
    # Entry happens at candle close.
    # We start checking from the next candle.
    for j in range(
        entry_index + 1,
        end_index + 1,
    ):
        candle = candles[j]

        high = candle["high"]
        low = candle["low"]

        if direction == "BUY":
            favorable = (
                (high - entry)
                / entry
                * 100.0
            )

            adverse = (
                (entry - low)
                / entry
                * 100.0
            )

            mfe = max(
                mfe,
                favorable,
            )

            mae = max(
                mae,
                adverse,
            )

            hit_sl = (
                low <= stop_loss
            )

            hit_tp = (
                high >= take_profit
            )

            # Conservative assumption:
            # if TP and SL are both hit in the same candle,
            # assume SL occurred first.
            if hit_sl and hit_tp:
                result = "LOSS"
                exit_price = stop_loss
                exit_index = j
                break

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
                (entry - low)
                / entry
                * 100.0
            )

            adverse = (
                (high - entry)
                / entry
                * 100.0
            )

            mfe = max(
                mfe,
                favorable,
            )

            mae = max(
                mae,
                adverse,
            )

            hit_sl = (
                high >= stop_loss
            )

            hit_tp = (
                low <= take_profit
            )

            if hit_sl and hit_tp:
                result = "LOSS"
                exit_price = stop_loss
                exit_index = j
                break

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

    if result == "TIME_EXIT":
        exit_index = end_index

        exit_price = float(
            candles[
                exit_index
            ]["close"]
        )

    if direction == "BUY":
        pnl_percent = (
            (exit_price - entry)
            / entry
            * 100.0
        )
    else:
        pnl_percent = (
            (entry - exit_price)
            / entry
            * 100.0
        )

    return {
        "timestamp": candles[
            entry_index
        ]["datetime"],
        "signal": direction,
        "patterns": signal[
            "patterns"
        ],
        "score": round(
            signal["score"],
            2,
        ),
        "entry": round(
            entry,
            2,
        ),
        "stop_loss": round(
            stop_loss,
            2,
        ),
        "take_profit": round(
            take_profit,
            2,
        ),
        "risk_reward": round(
            signal["risk_reward"],
            2,
        ),
        "result": result,
        "exit_price": round(
            exit_price,
            2,
        ),
        "pnl_percent": round(
            pnl_percent,
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
            - entry_index
        ),
    }


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(candles):
    total_candles = len(candles)

    # Need enough history for:
    # EMA50 + patterns + S/R
    start_index = max(
        EMA_SLOW + 20,
        SR_LOOKBACK,
        80,
    )

    last_entry_index = (
        total_candles
        - FORWARD_BARS
        - 1
    )

    if last_entry_index <= start_index:
        raise RuntimeError(
            "Not enough candles for backtest"
        )

    trade_results = []

    pattern_frequency = {}

    pattern_detected = 0
    confirmations_passed = 0
    triggers_passed = 0

    buy_signals = 0
    sell_signals = 0

    for i in range(
        start_index,
        last_entry_index + 1,
    ):
        historical_candles = (
            candles[:i + 1]
        )

        # EXACT SAME ENGINE AS LIVE
        signal = generate_signal(
            historical_candles
        )

        for pattern in signal.get(
            "patterns",
            [],
        ):
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
            "patterns"
        ):
            pattern_detected += 1

        confirmation = signal.get(
            "confirmation",
            {},
        )

        if confirmation.get(
            "score",
            0,
        ) >= MIN_SCORE:
            confirmations_passed += 1

        trigger = confirmation.get(
            "trigger",
            {},
        )

        if trigger.get(
            "triggered",
            False,
        ):
            triggers_passed += 1

        if signal.get(
            "signal"
        ) not in [
            "BUY",
            "SELL",
        ]:
            continue

        if signal.get(
            "entry"
        ) is None:
            continue

        if signal.get(
            "stop_loss"
        ) is None:
            continue

        if signal.get(
            "take_profit"
        ) is None:
            continue

        if signal["signal"] == "BUY":
            buy_signals += 1
        else:
            sell_signals += 1

        result = simulate_trade(
            historical_candles,
            i,
            signal,
        )

        trade_results.append(
            result
        )

    # ========================================================
    # RESULTS
    # ========================================================

    total_trades = len(
        trade_results
    )

    wins = sum(
        1
        for t in trade_results
        if t["result"] == "WIN"
    )

    losses = sum(
        1
        for t in trade_results
        if t["result"] == "LOSS"
    )

    time_exits = sum(
        1
        for t in trade_results
        if t["result"] == "TIME_EXIT"
    )

    total_profit = sum(
        max(
            t["pnl_percent"],
            0.0,
        )
        for t in trade_results
    )

    total_loss = sum(
        abs(
            min(
                t["pnl_percent"],
                0.0,
            )
        )
        for t in trade_results
    )

    net_profit = (
        total_profit
        - total_loss
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

    win_rate = (
        wins
        / total_trades
        * 100.0
        if total_trades
        else 0.0
    )

    loss_rate = (
        losses
        / total_trades
        * 100.0
        if total_trades
        else 0.0
    )

    timeout_rate = (
        time_exits
        / total_trades
        * 100.0
        if total_trades
        else 0.0
    )

    expectancy = (
        net_profit
        / total_trades
        if total_trades
        else 0.0
    )

    average_mfe = (
        sum(
            t["mfe_percent"]
            for t in trade_results
        )
        / total_trades
        if total_trades
        else 0.0
    )

    average_mae = (
        sum(
            t["mae_percent"]
            for t in trade_results
        )
        / total_trades
        if total_trades
        else 0.0
    )

    average_score = (
        sum(
            t["score"]
            for t in trade_results
        )
        / total_trades
        if total_trades
        else 0.0
    )

    average_rr = (
        sum(
            t["risk_reward"]
            for t in trade_results
        )
        / total_trades
        if total_trades
        else 0.0
    )

    # ========================================================
    # MAX DRAWDOWN
    # ========================================================

    equity = 0.0
    peak_equity = 0.0
    max_drawdown = 0.0

    equity_curve = []

    for trade in trade_results:
        equity += trade[
            "pnl_percent"
        ]

        peak_equity = max(
            peak_equity,
            equity,
        )

        drawdown = (
            peak_equity
            - equity
        )

        max_drawdown = max(
            max_drawdown,
            drawdown,
        )

        equity_curve.append(
            equity
        )

    # ========================================================
    # PATTERN PERFORMANCE
    # ========================================================

    pattern_stats = {}

    for trade in trade_results:
        for pattern in trade[
            "patterns"
        ]:
            if pattern not in pattern_stats:
                pattern_stats[
                    pattern
                ] = {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "time_exits": 0,
                    "net_profit_percent": 0.0,
                }

            item = pattern_stats[
                pattern
            ]

            item["trades"] += 1

            if trade[
                "result"
            ] == "WIN":
                item["wins"] += 1

            elif trade[
                "result"
            ] == "LOSS":
                item["losses"] += 1

            else:
                item["time_exits"] += 1

            item[
                "net_profit_percent"
            ] += trade[
                "pnl_percent"
            ]

    for pattern, item in pattern_stats.items():
        trades = item["trades"]

        item["win_rate_percent"] = round(
            item["wins"]
            / trades
            * 100.0,
            2,
        ) if trades else 0.0

        item["net_profit_percent"] = round(
            item["net_profit_percent"],
            4,
        )

    return {
        "status": "completed",
        "symbol": SYMBOL,
        "timeframe": "M5",
        "system": "Pattern Recognition",
        "data_source": "Twelve Data XAU/USD",

        "candles_available": total_candles,

        "test_points": (
            last_entry_index
            - start_index
            + 1
        ),

        "architecture": [
            "Pattern Recognition",
            "Confirmation",
            "Trigger",
            "Entry",
            "TP/SL",
            "Backtest",
            "Telegram",
        ],

        "rules": {
            "minimum_score": MIN_SCORE,
            "minimum_atr": MIN_ATR,
            "minimum_risk_reward": MIN_RISK_REWARD,
            "max_stop_atr": MAX_STOP_ATR,
            "stop_buffer_atr": STOP_BUFFER_ATR,
            "forward_bars": FORWARD_BARS,
            "trigger_lookback": TRIGGER_LOOKBACK,
            "swing_lookback": SWING_LOOKBACK,
        },

        "pipeline": {
            "patterns_detected": pattern_detected,
            "confirmations_passed": confirmations_passed,
            "triggers_passed": triggers_passed,
            "entries": total_trades,
        },

        "signals": {
            "total": total_trades,
            "buy": buy_signals,
            "sell": sell_signals,
        },

        "results": {
            "wins": wins,
            "losses": losses,
            "time_exits": time_exits,
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
            "expectancy_percent": round(
                expectancy,
                4,
            ),
            "max_drawdown_percent": round(
                max_drawdown,
                4,
            ),
            "average_mfe_percent": round(
                average_mfe,
                4,
            ),
            "average_mae_percent": round(
                average_mae,
                4,
            ),
            "average_score": round(
                average_score,
                2,
            ),
            "average_risk_reward": round(
                average_rr,
                2,
            ),
        },

        "pattern_frequency": (
            pattern_frequency
        ),

        "pattern_performance": (
            pattern_stats
        ),

        "recent_trades": (
            trade_results[-20:]
        ),

        "warning": (
            "Historical simulation only. "
            "Entry is assumed at trigger candle close. "
            "TP/SL are checked from the following candle. "
            "Spread, slippage, commission, latency and "
            "broker-specific execution are not included."
        ),
    }


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

        "architecture": [
            "Pattern Recognition",
            "Confirmation",
            "Trigger",
            "Entry",
            "TP/SL",
            "Telegram",
            "Backtest",
        ],

        "patterns":
            PATTERNS,

        "rules": {
            "minimum_score":
                MIN_SCORE,

            "minimum_atr":
                MIN_ATR,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "max_stop_atr":
                MAX_STOP_ATR,

            "forward_bars":
                FORWARD_BARS,
        },

        "endpoints": [
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
        "status": "healthy",

        "system":
            "Pattern Recognition",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "data_source":
            "Twelve Data",

        "twelve_data":
            bool(
                TWELVE_DATA_API_KEY
            ),

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "startup_notification":
            STATE[
                "startup_sent"
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
    })


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():
    try:
        # Make sure startup message is attempted
        # when service receives its first real request.
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
            "status": "error",
            "signal": "ERROR",
            "error": str(exc),
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
            "status": "success",
            "message":
                "Twelve Data connection is working",
            "symbol":
                SYMBOL,
            "timeframe":
                "M5",
            "candles":
                len(candles),
            "latest": {
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
            },
        })

    except Exception as exc:
        STATE[
            "last_error"
        ] = str(exc)

        return jsonify({
            "status": "error",
            "error": str(exc),
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
        "<b>System:</b> Pattern Recognition\n"
        "<b>Pipeline:</b>\n"
        "Pattern → Confirmation → Trigger "
        "→ Entry → TP/SL\n"
        "\n"
        "ข้อความนี้เป็นข้อความทดสอบ"
    )

    ok, error = send_telegram(
        message
    )

    if ok:
        return jsonify({
            "status": "success",
            "message":
                "Telegram test message sent successfully",
            "telegram": True,
        })

    return jsonify({
        "status": "error",
        "message":
            "Telegram test message failed",
        "telegram": False,
        "error": error,
    }), 500


# ============================================================
# BACKTEST ENDPOINT
# ============================================================

@app.route("/backtest")
def backtest_endpoint():
    try:
        candles = get_candles()

        result = run_backtest(
            candles
        )

        return jsonify(
            result
        )

    except Exception as exc:
        STATE[
            "last_error"
        ] = str(exc)

        return jsonify({
            "status": "error",
            "error": str(exc),
        }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Send startup message immediately
    # when running directly.
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

import os
import math
import html
import threading
import time
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
MIN_SCORE = 70.0
MIN_RISK_REWARD = 1.30

RISK_REWARD = 1.50

# จำนวนแท่งสำหรับติดตาม TP / SL
FORWARD_BARS = 12

BACKTEST_POINTS = 200

SUPPORT_LOOKBACK = 50
RESISTANCE_LOOKBACK = 50

TRIGGER_LOOKBACK = 3

SIGNAL_COOLDOWN_SECONDS = 60


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

    # Twelve Data ส่งใหม่ -> เก่า
    # ระบบต้องการเก่า -> ใหม่
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

    avg_gain = (
        sum(recent_gains) / period
    )

    avg_loss = (
        sum(recent_losses) / period
    )

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

    if low_difference <= 0.0015:
        if candles[-1]["close"] > second_low:
            patterns.append(
                "Double Bottom"
            )

    if high_difference <= 0.0015:
        if candles[-1]["close"] < second_high:
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

    if (
        len(bullish) > len(bearish)
        and len(bullish) > 0
    ):
        return "BUY"

    if (
        len(bearish) > len(bullish)
        and len(bearish) > 0
    ):
        return "SELL"

    return None


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

    bullish_patterns, bearish_patterns = (
        get_directional_patterns(patterns)
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

    if patterns:
        checks["pattern"] = True

        reasons.append(
            "{} pattern(s) detected".format(
                len(patterns)
            )
        )
    else:
        reasons.append(
            "No pattern detected"
        )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if direction == "BUY":

        if trend == "UPTREND":
            checks["trend"] = True

            reasons.append(
                "Aligned with uptrend"
            )
        else:
            reasons.append(
                "Against or outside uptrend"
            )

    elif direction == "SELL":

        if trend == "DOWNTREND":
            checks["trend"] = True

            reasons.append(
                "Aligned with downtrend"
            )
        else:
            reasons.append(
                "Against or outside downtrend"
            )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    if direction == "BUY":

        if momentum == "BULLISH":
            checks["momentum"] = True

            reasons.append(
                "Momentum confirms BUY"
            )
        else:
            reasons.append(
                "Momentum not confirmed"
            )

    elif direction == "SELL":

        if momentum == "BEARISH":
            checks["momentum"] = True

            reasons.append(
                "Momentum confirms SELL"
            )
        else:
            reasons.append(
                "Momentum not confirmed"
            )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if direction == "BUY":

        if 45 <= rsi <= 72:
            checks["rsi"] = True

            reasons.append(
                "RSI supports BUY"
            )
        else:
            reasons.append(
                "RSI does not support BUY"
            )

    elif direction == "SELL":

        if 28 <= rsi <= 55:
            checks["rsi"] = True

            reasons.append(
                "RSI supports SELL"
            )
        else:
            reasons.append(
                "RSI does not support SELL"
            )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    location_buffer = max(
        atr * 0.75,
        1.0,
    )

    if direction == "BUY":

        if (
            close >= (
                resistance
                - location_buffer
            )
            or close > ema20
        ):
            checks["location"] = True

        if close >= (
            resistance
            - location_buffer
        ):
            reasons.append(
                "Near resistance / breakout zone"
            )
        else:
            reasons.append(
                "Price location acceptable for BUY"
            )

    elif direction == "SELL":

        if (
            close <= (
                support
                + location_buffer
            )
            or close < ema20
        ):
            checks["location"] = True

        if close <= (
            support
            + location_buffer
        ):
            reasons.append(
                "Near support / breakdown zone"
            )
        else:
            reasons.append(
                "Price location acceptable for SELL"
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
    #
    # Trigger ยังไม่ถูกนับตรงนี้
    # เพื่อป้องกันการบวก trigger ซ้ำ
    # --------------------------------------------------------

    weights = {
        "pattern": 20.0,
        "trend": 15.0,
        "momentum": 15.0,
        "rsi": 10.0,
        "location": 15.0,
        "volatility": 10.0,
        "trigger": 15.0,
    }

    score = 0.0

    for key, weight in weights.items():

        if key == "trigger":
            continue

        if checks[key]:
            score += weight

    return {
        "direction": direction,
        "score": round(score, 2),
        "valid": score >= MIN_SCORE,
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
        "bullish_patterns": bullish_patterns,
        "bearish_patterns": bearish_patterns,
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

        if current["close"] >= trigger:

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

        if current["close"] <= trigger:

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

    risk_distance = max(
        atr,
        0.5,
    )

    if direction == "BUY":

        structural_sl = (
            support
            - atr * 0.10
        )

        stop_loss = min(
            entry - risk_distance,
            structural_sl,
        )

        actual_risk = (
            entry
            - stop_loss
        )

        take_profit = (
            entry
            + actual_risk
            * RISK_REWARD
        )

    elif direction == "SELL":

        structural_sl = (
            resistance
            + atr * 0.10
        )

        stop_loss = max(
            entry + risk_distance,
            structural_sl,
        )

        actual_risk = (
            stop_loss
            - entry
        )

        take_profit = (
            entry
            - actual_risk
            * RISK_REWARD
        )

    else:
        return None

    if actual_risk <= 0:
        return None

    reward = abs(
        take_profit - entry
    )

    rr = (
        reward
        / actual_risk
    )

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

    direction = get_candidate_direction(
        patterns
    )

    # --------------------------------------------------------
    # NO PATTERN
    # --------------------------------------------------------

    if direction is None:

        return {
            "timestamp": latest["datetime"],
            "symbol": SYMBOL,
            "timeframe": "M5",
            "signal": "NO_PATTERN",
            "status": "NO_PATTERN",
            "valid": False,
            "patterns": patterns,
            "directional_patterns": [],
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
            "support": round_price(support),
            "resistance": round_price(
                resistance
            ),
            "confirmation": None,
            "method": (
                "Pattern Recognition + "
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
        bool(
            trigger["triggered"]
        )
    )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = float(
        confirmation["score"]
    )

    if trigger["triggered"]:
        score += 15.0

    score = round(
        min(score, 100.0),
        2,
    )

    confirmation["score"] = score

    # --------------------------------------------------------
    # REASON
    # --------------------------------------------------------

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
    # CONFIRMATION
    # --------------------------------------------------------

    all_confirmation_checks = all(
        confirmation["checks"].values()
    )

    valid_confirmation = (
        all_confirmation_checks
        and score >= MIN_SCORE
    )

    trade = None

    # --------------------------------------------------------
    # TRADE
    # --------------------------------------------------------

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
        score >= MIN_SCORE
        and not trigger["triggered"]
    ):

        signal = "WAIT_TRIGGER"
        status = "PATTERN_CONFIRMED"
        valid = False

    else:

        signal = "WAIT_CONFIRMATION"
        status = "PATTERN_DETECTED"
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

        "directional_patterns": (
            confirmation[
                "bullish_patterns"
            ]
            if direction == "BUY"
            else confirmation[
                "bearish_patterns"
            ]
        ),

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
            "ระบบรันเสร็จแล้วและพร้อมทำงาน\n"
            "\n"
            "<b>Architecture</b>\n"
            "Pattern Recognition\n"
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
            "\n"
            "พร้อมวิเคราะห์ตลาดแล้ว"
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

    direction = signal.get(
        "signal"
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
            signal.get(
                "entry"
            )
        )
        + "\n"
        "<b>TP:</b> "
        + str(
            signal.get(
                "take_profit"
            )
        )
        + "\n"
        "<b>SL:</b> "
        + str(
            signal.get(
                "stop_loss"
            )
        )
        + "\n"
        "<b>RR:</b> "
        + str(
            signal.get(
                "risk_reward"
            )
        )
        + "\n"
        "\n"
        "<b>Trend:</b> "
        + str(
            signal.get(
                "trend"
            )
        )
        + "\n"
        "<b>Momentum:</b> "
        + str(
            signal.get(
                "momentum"
            )
        )
        + "\n"
        "<b>RSI:</b> "
        + str(
            signal.get(
                "rsi"
            )
        )
        + "\n"
        "<b>ATR:</b> "
        + str(
            signal.get(
                "atr"
            )
        )
        + "\n"
        "\n"
        "<b>Trigger:</b> "
        + str(
            signal.get(
                "trigger"
            )
        )
        + "\n"
        "<b>Time:</b> "
        + html.escape(
            str(
                signal.get(
                    "timestamp"
                )
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
            signal.get(
                "timestamp"
            )
        )
        + "_"
        + str(
            signal.get(
                "signal"
            )
        )
        + "_"
        + str(
            signal.get(
                "entry"
            )
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
        return None

    entry = float(entry)
    stop_loss = float(stop_loss)
    take_profit = float(
        take_profit
    )

    last_index = min(
        signal_index
        + FORWARD_BARS,
        len(candles) - 1,
    )

    result = "TIMEOUT"

    exit_reason = "TIMEOUT"

    exit_price = None

    exit_index = last_index

    mfe = 0.0
    mae = 0.0

    # --------------------------------------------------------
    # FOLLOW TRADE
    # --------------------------------------------------------

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

            hit_sl = (
                low <= stop_loss
            )

            hit_tp = (
                high >= take_profit
            )

            # ------------------------------------------------
            # SAME CANDLE TP + SL
            # Conservative = LOSS
            # ------------------------------------------------

            if hit_sl and hit_tp:

                result = "LOSS"

                exit_reason = (
                    "SL_AND_TP_SAME_CANDLE"
                )

                exit_price = stop_loss

                exit_index = j

                break

            if hit_sl:

                result = "LOSS"

                exit_reason = "STOP_LOSS"

                exit_price = stop_loss

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

            hit_sl = (
                high >= stop_loss
            )

            hit_tp = (
                low <= take_profit
            )

            # ------------------------------------------------
            # SAME CANDLE TP + SL
            # Conservative = LOSS
            # ------------------------------------------------

            if hit_sl and hit_tp:

                result = "LOSS"

                exit_reason = (
                    "SL_AND_TP_SAME_CANDLE"
                )

                exit_price = stop_loss

                exit_index = j

                break

            if hit_sl:

                result = "LOSS"

                exit_reason = "STOP_LOSS"

                exit_price = stop_loss

                exit_index = j

                break

            if hit_tp:

                result = "WIN"

                exit_reason = "TAKE_PROFIT"

                exit_price = take_profit

                exit_index = j

                break

    # --------------------------------------------------------
    # TIMEOUT EXIT
    # --------------------------------------------------------

    if exit_price is None:

        exit_price = float(
            candles[
                exit_index
            ]["close"]
        )

        result = "TIMEOUT"

        exit_reason = "FORWARD_BARS_TIMEOUT"

    # --------------------------------------------------------
    # PNL
    # --------------------------------------------------------

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

        "entry": round_price(
            entry
        ),

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

def run_backtest():

    candles = get_candles()

    total_candles = len(candles)

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
        end - BACKTEST_POINTS,
    )

    trade_results = []

    pattern_frequency = {}

    candidate_count = 0

    confirmation_count = 0

    trigger_count = 0

    # ========================================================
    # WALK FORWARD
    # ========================================================

    for i in range(
        start,
        end,
    ):

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
    # RATES
    # ========================================================

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

        timeout_rate = (
            timeouts
            / signals
            * 100.0
        )

        expectancy = (
            net_profit
            / signals
        )

    else:

        win_rate = 0.0

        loss_rate = 0.0

        timeout_rate = 0.0

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

    # ========================================================
    # MFE / MAE / SCORE
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
            "Confirmation",
            "Trigger",
            "Entry",
            "TP/SL",
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
            "timeouts": timeouts,
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
        },

        "pattern_frequency": (
            pattern_frequency
        ),

        "recent_trades": (
            trade_results[-20:]
        ),

        "warning": (
            "Historical simulation only. "
            "Spread, slippage, execution delay "
            "and broker-specific pricing are "
            "not included."
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
                "Confirmation",
                "Trigger",
                "Entry",
                "TP/SL",
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
            },

            "endpoints": [
                "/",
                "/health",
                "/signal",
                "/backtest",
                "/test-data",
                "/test-telegram",
            ],
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
        "Pattern → Confirmation → Trigger\n"
        "→ Entry → TP/SL\n"
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

        result = run_backtest()

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

import os
import math
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from flask import Flask, jsonify


# ============================================================
# CONFIG
# ============================================================

app = Flask(__name__)


SYMBOL = os.getenv("SYMBOL", "XAU/USD")
TIMEFRAME = os.getenv("TIMEFRAME", "5min")

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


# ------------------------------------------------------------
# Trading Engine Rules
# ------------------------------------------------------------

MIN_SCORE = float(os.getenv("MIN_SCORE", "70"))

MIN_PATTERN_QUALITY = float(
    os.getenv("MIN_PATTERN_QUALITY", "55")
)

MIN_TRIGGER_QUALITY = float(
    os.getenv("MIN_TRIGGER_QUALITY", "55")
)

MIN_RISK_REWARD = float(
    os.getenv("MIN_RISK_REWARD", "1.30")
)

RISK_REWARD = float(
    os.getenv("RISK_REWARD", "1.50")
)

MINIMUM_ATR = float(
    os.getenv("MINIMUM_ATR", "0.50")
)

MIN_STOP_ATR = float(
    os.getenv("MIN_STOP_ATR", "1.00")
)

MAX_STOP_ATR = float(
    os.getenv("MAX_STOP_ATR", "3.00")
)

FORWARD_BARS = int(
    os.getenv("FORWARD_BARS", "24")
)

TRIGGER_LOOKBACK = int(
    os.getenv("TRIGGER_LOOKBACK", "3")
)

SPREAD = float(
    os.getenv("SPREAD", "0.20")
)

SLIPPAGE = float(
    os.getenv("SLIPPAGE", "0.05")
)

BREAK_EVEN = os.getenv(
    "BREAK_EVEN", "true"
).lower() == "true"

BREAK_EVEN_R = float(
    os.getenv("BREAK_EVEN_R", "1.0")
)

CANDLES = int(
    os.getenv("CANDLES", "1000")
)


# ============================================================
# GLOBAL DATA CACHE
# ============================================================

DATA_CACHE = {
    "data": None,
    "timestamp": None
}


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        value = float(value)

        if math.isnan(value) or math.isinf(value):
            return default

        return value

    except Exception:
        return default


def clamp(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, safe_float(value)))


def round_price(value):
    return round(safe_float(value), 5)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {
            "success": False,
            "message": "Telegram credentials not configured"
        }

    try:

        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        if response.ok:

            return {
                "success": True,
                "message": "Telegram message sent successfully"
            }

        return {
            "success": False,
            "message": response.text
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ============================================================
# TWELVE DATA
# ============================================================

def get_market_data(outputsize=CANDLES):

    if not TWELVE_DATA_API_KEY:

        raise RuntimeError(
            "TWELVE_DATA_API_KEY is not configured"
        )

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": TIMEFRAME,
        "outputsize": min(int(outputsize), 5000),
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON"
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if "status" in data and data["status"] == "error":

        raise RuntimeError(
            data.get("message", "Twelve Data error")
        )

    values = data.get("values")

    if not values:

        raise RuntimeError(
            "No candle data returned by Twelve Data"
        )

    df = pd.DataFrame(values)

    required = [
        "datetime",
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        if column not in df.columns:

            raise RuntimeError(
                f"Missing column: {column}"
            )

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        errors="coerce"
    )

    for column in [
        "open",
        "high",
        "low",
        "close"
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=[
            "datetime",
            "open",
            "high",
            "low",
            "close"
        ]
    )

    df = df.sort_values(
        "datetime"
    ).reset_index(drop=True)

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    df["ema20"] = (
        df["close"]
        .ewm(span=20, adjust=False)
        .mean()
    )

    df["ema50"] = (
        df["close"]
        .ewm(span=50, adjust=False)
        .mean()
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    df["rsi"] = (
        100 - (100 / (1 + rs))
    )

    df["rsi"] = df["rsi"].fillna(50)

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]

    tr2 = (
        df["high"] - previous_close
    ).abs()

    tr3 = (
        df["low"] - previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["atr"] = (
        true_range
        .rolling(14)
        .mean()
    )

    # fallback for early candles
    df["atr"] = (
        df["atr"]
        .bfill()
        .fillna(1.0)
    )

    # --------------------------------------------------------
    # Candle properties
    # --------------------------------------------------------

    df["body"] = (
        df["close"] - df["open"]
    ).abs()

    df["range"] = (
        df["high"] - df["low"]
    ).replace(0, np.nan)

    df["body_ratio"] = (
        df["body"] / df["range"]
    )

    df["body_ratio"] = (
        df["body_ratio"]
        .fillna(0)
        .clip(0, 1)
    )

    df["upper_wick"] = (
        df["high"]
        - df[["open", "close"]].max(axis=1)
    )

    df["lower_wick"] = (
        df[["open", "close"]].min(axis=1)
        - df["low"]
    )

    # --------------------------------------------------------
    # ATR ratio
    # --------------------------------------------------------

    atr_average = (
        df["atr"]
        .rolling(50)
        .mean()
        .replace(0, np.nan)
    )

    df["atr_ratio"] = (
        df["atr"] / atr_average
    )

    df["atr_ratio"] = (
        df["atr_ratio"]
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .fillna(1.0)
    )

    return df


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def get_support_resistance(df, index):

    start = max(0, index - 50)

    window = df.iloc[start:index + 1]

    if len(window) < 5:

        return {
            "support": safe_float(
                df.iloc[index]["low"]
            ),
            "resistance": safe_float(
                df.iloc[index]["high"]
            )
        }

    support = safe_float(
        window["low"].min()
    )

    resistance = safe_float(
        window["high"].max()
    )

    return {
        "support": support,
        "resistance": resistance
    }


# ============================================================
# PATTERN DETECTION
# ============================================================

def detect_patterns(df, i):

    if i < 5:

        return []

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    patterns = []

    o = safe_float(row["open"])
    h = safe_float(row["high"])
    l = safe_float(row["low"])
    c = safe_float(row["close"])

    po = safe_float(prev["open"])
    ph = safe_float(prev["high"])
    pl = safe_float(prev["low"])
    pc = safe_float(prev["close"])

    body = abs(c - o)
    candle_range = max(h - l, 1e-9)

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    # --------------------------------------------------------
    # Bullish Engulfing
    # --------------------------------------------------------

    if (
        pc < po
        and c > o
        and o <= pc
        and c >= po
    ):

        patterns.append(
            "Bullish Engulfing"
        )

    # --------------------------------------------------------
    # Bearish Engulfing
    # --------------------------------------------------------

    if (
        pc > po
        and c < o
        and o >= pc
        and c <= po
    ):

        patterns.append(
            "Bearish Engulfing"
        )

    # --------------------------------------------------------
    # Hammer
    # --------------------------------------------------------

    if (
        lower_wick >= body * 2
        and upper_wick <= body
        and candle_range > 0
    ):

        patterns.append("Hammer")

    # --------------------------------------------------------
    # Shooting Star
    # --------------------------------------------------------

    if (
        upper_wick >= body * 2
        and lower_wick <= body
        and candle_range > 0
    ):

        patterns.append("Shooting Star")

    # --------------------------------------------------------
    # Morning Star
    # --------------------------------------------------------

    if i >= 2:

        r2 = df.iloc[i - 2]

        o2 = safe_float(r2["open"])
        c2 = safe_float(r2["close"])

        first_bearish = c2 < o2
        second_small = (
            abs(pc - po)
            < abs(c2 - o2) * 0.5
        )
        third_bullish = c > o

        if (
            first_bearish
            and second_small
            and third_bullish
        ):

            patterns.append(
                "Morning Star"
            )

    # --------------------------------------------------------
    # Evening Star
    # --------------------------------------------------------

    if i >= 2:

        r2 = df.iloc[i - 2]

        o2 = safe_float(r2["open"])
        c2 = safe_float(r2["close"])

        first_bullish = c2 > o2

        second_small = (
            abs(pc - po)
            < abs(c2 - o2) * 0.5
        )

        third_bearish = c < o

        if (
            first_bullish
            and second_small
            and third_bearish
        ):

            patterns.append(
                "Evening Star"
            )

    # --------------------------------------------------------
    # Double Top
    # --------------------------------------------------------

    lookback = df.iloc[
        max(0, i - 12):i
    ]

    if len(lookback) >= 6:

        previous_high = safe_float(
            lookback["high"].max()
        )

        tolerance = max(
            safe_float(row["atr"]) * 0.35,
            0.5
        )

        if abs(h - previous_high) <= tolerance:

            patterns.append(
                "Double Top"
            )

    # --------------------------------------------------------
    # Double Bottom
    # --------------------------------------------------------

    if len(lookback) >= 6:

        previous_low = safe_float(
            lookback["low"].min()
        )

        tolerance = max(
            safe_float(row["atr"]) * 0.35,
            0.5
        )

        if abs(l - previous_low) <= tolerance:

            patterns.append(
                "Double Bottom"
            )

    # --------------------------------------------------------
    # Bullish Breakout
    # --------------------------------------------------------

    if len(lookback) >= 5:

        previous_resistance = safe_float(
            lookback["high"].max()
        )

        if (
            c > previous_resistance
            and c > o
        ):

            patterns.append(
                "Bullish Breakout"
            )

    # --------------------------------------------------------
    # Bearish Breakout
    # --------------------------------------------------------

    if len(lookback) >= 5:

        previous_support = safe_float(
            lookback["low"].min()
        )

        if (
            c < previous_support
            and c < o
        ):

            patterns.append(
                "Bearish Breakout"
            )

    # --------------------------------------------------------
    # Pullback
    # --------------------------------------------------------

    ema20 = safe_float(row["ema20"])
    ema50 = safe_float(row["ema50"])

    if (
        ema20 > ema50
        and l <= ema20
        and c > ema20
    ):

        patterns.append("Pullback")

    elif (
        ema20 < ema50
        and h >= ema20
        and c < ema20
    ):

        patterns.append("Pullback")

    return list(dict.fromkeys(patterns))


# ============================================================
# PATTERN DIRECTION
# ============================================================

BULLISH_PATTERNS = {
    "Bullish Engulfing",
    "Hammer",
    "Morning Star",
    "Double Bottom",
    "Bullish Breakout",
    "Pullback"
}

BEARISH_PATTERNS = {
    "Bearish Engulfing",
    "Shooting Star",
    "Evening Star",
    "Double Top",
    "Bearish Breakout",
    "Pullback"
}


def get_pattern_direction(patterns, df, i):

    bullish = []
    bearish = []

    for pattern in patterns:

        if pattern == "Pullback":

            row = df.iloc[i]

            if (
                safe_float(row["ema20"])
                > safe_float(row["ema50"])
            ):

                bullish.append(pattern)

            else:

                bearish.append(pattern)

        elif pattern in BULLISH_PATTERNS:

            bullish.append(pattern)

        elif pattern in BEARISH_PATTERNS:

            bearish.append(pattern)

    if bullish and bearish:

        return {
            "direction": "CONFLICT",
            "bullish": bullish,
            "bearish": bearish,
            "conflict": True
        }

    if bullish:

        return {
            "direction": "BUY",
            "bullish": bullish,
            "bearish": [],
            "conflict": False
        }

    if bearish:

        return {
            "direction": "SELL",
            "bullish": [],
            "bearish": bearish,
            "conflict": False
        }

    return {
        "direction": "NONE",
        "bullish": [],
        "bearish": [],
        "conflict": False
    }


# ============================================================
# MARKET REGIME
# ============================================================

def calculate_market_regime(df, i):

    row = df.iloc[i]

    ema20 = safe_float(row["ema20"])
    ema50 = safe_float(row["ema50"])

    atr_ratio = safe_float(
        row["atr_ratio"],
        1.0
    )

    atr = safe_float(
        row["atr"],
        1.0
    )

    price = safe_float(
        row["close"]
    )

    trend_strength = 0.0

    if atr > 0:

        trend_strength = (
            abs(ema20 - ema50)
            / atr
        )

    if (
        ema20 > ema50
        and price >= ema20
        and trend_strength >= 1.0
    ):

        regime = "TREND_UP"

    elif (
        ema20 < ema50
        and price <= ema20
        and trend_strength >= 1.0
    ):

        regime = "TREND_DOWN"

    elif (
        atr_ratio < 0.70
        and trend_strength >= 0.8
    ):

        if ema20 >= ema50:
            regime = "LOW_VOLATILITY_TREND_UP"
        else:
            regime = "LOW_VOLATILITY_TREND_DOWN"

    elif trend_strength < 0.7:

        regime = "RANGE"

    else:

        regime = "TRANSITION"

    if regime in [
        "TREND_UP",
        "TREND_DOWN"
    ]:

        score = 100.0

    elif regime.startswith(
        "LOW_VOLATILITY"
    ):

        score = 80.0

    elif regime == "TRANSITION":

        score = 55.0

    else:

        score = 45.0

    return {
        "regime": regime,
        "atr_ratio": round(atr_ratio, 3),
        "trend_strength": round(
            trend_strength,
            3
        ),
        "score": round(score, 2)
    }


# ============================================================
# LOCATION
# ============================================================

def calculate_location(
    df,
    i,
    direction
):

    row = df.iloc[i]

    price = safe_float(row["close"])

    ema20 = safe_float(row["ema20"])
    ema50 = safe_float(row["ema50"])

    levels = get_support_resistance(
        df,
        i
    )

    support = levels["support"]
    resistance = levels["resistance"]

    atr = max(
        safe_float(row["atr"]),
        0.01
    )

    distance_support = (
        price - support
    )

    distance_resistance = (
        resistance - price
    )

    score = 50.0
    zone = "NEUTRAL"

    if direction == "BUY":

        if distance_support <= atr * 1.5:

            zone = "NEAR_SUPPORT"
            score = 100.0

        elif price > ema20 > ema50:

            zone = "TREND_SUPPORT"
            score = 80.0

        elif distance_resistance <= atr:

            zone = "NEAR_RESISTANCE"
            score = 20.0

        else:

            zone = "NEUTRAL"
            score = 55.0

    elif direction == "SELL":

        if distance_resistance <= atr * 1.5:

            zone = "NEAR_RESISTANCE"
            score = 100.0

        elif price < ema20 < ema50:

            zone = "TREND_RESISTANCE"
            score = 80.0

        elif distance_support <= atr:

            zone = "NEAR_SUPPORT"
            score = 20.0

        else:

            zone = "NEUTRAL"
            score = 55.0

    return {
        "support": round_price(support),
        "resistance": round_price(resistance),
        "ema20": round_price(ema20),
        "ema50": round_price(ema50),
        "zone": zone,
        "zones": [zone],
        "score": round(score, 2),
        "valid": score >= 50
    }


# ============================================================
# MOMENTUM
# ============================================================

def calculate_momentum(
    df,
    i,
    direction
):

    row = df.iloc[i]

    rsi = safe_float(
        row["rsi"],
        50
    )

    score = 50.0
    strength = 0.0
    reasons = []

    if direction == "BUY":

        if 50 <= rsi <= 68:

            score = 100.0

        elif rsi > 68:

            score = 45.0

            reasons.append(
                "RSI high for BUY"
            )

        elif rsi < 40:

            score = 30.0

            reasons.append(
                "RSI weak for BUY"
            )

        else:

            score = 60.0

    elif direction == "SELL":

        if 32 <= rsi <= 50:

            score = 100.0

        elif rsi < 32:

            score = 45.0

            reasons.append(
                "RSI low for SELL"
            )

        elif rsi > 60:

            score = 20.0

            reasons.append(
                "RSI weak for SELL"
            )

        else:

            score = 60.0

    if direction == "BUY":

        strength = max(
            0,
            min(
                100,
                (rsi - 50) * 2
            )
        )

    elif direction == "SELL":

        strength = max(
            0,
            min(
                100,
                (50 - rsi) * 2
            )
        )

    return {
        "direction": (
            "BULLISH"
            if direction == "BUY"
            else "BEARISH"
        ),
        "rsi": round(rsi, 1),
        "score": round(score, 2),
        "strength": round(
            strength,
            1
        ),
        "valid": score >= 50,
        "reasons": reasons
    }


# ============================================================
# PATTERN QUALITY
# ============================================================

def calculate_pattern_quality(
    df,
    i,
    patterns,
    direction
):

    row = df.iloc[i]

    body_ratio = safe_float(
        row["body_ratio"]
    )

    candle_direction = (
        "BUY"
        if safe_float(row["close"])
        > safe_float(row["open"])
        else "SELL"
    )

    score = 50.0
    reasons = []
    opposite = []

    if body_ratio >= 0.70:

        score += 25

    elif body_ratio >= 0.50:

        score += 15

    elif body_ratio >= 0.35:

        score += 5

    else:

        score -= 15

        reasons.append(
            "Weak candle body"
        )

    if direction == candle_direction:

        score += 20

    else:

        score -= 10

        reasons.append(
            "Pattern candle direction weak"
        )

    for pattern in patterns:

        if direction == "BUY":

            if pattern in BEARISH_PATTERNS:

                opposite.append(pattern)

        elif direction == "SELL":

            if pattern in BULLISH_PATTERNS:

                opposite.append(pattern)

    if opposite:

        score -= 15

    else:

        reasons.append(
            "No opposite pattern"
        )

    score = clamp(score)

    quality = (
        "PASS"
        if score >= MIN_PATTERN_QUALITY
        else "FAIL"
    )

    return {
        "body_ratio": round(
            body_ratio,
            3
        ),
        "opposite": opposite,
        "quality": quality,
        "reasons": reasons,
        "relevant": patterns,
        "score": round(
            score,
            2
        )
    }


# ============================================================
# TRIGGER QUALITY
# ============================================================

def calculate_trigger_quality(
    df,
    i,
    direction
):

    row = df.iloc[i]

    close = safe_float(
        row["close"]
    )

    open_price = safe_float(
        row["open"]
    )

    high = safe_float(
        row["high"]
    )

    low = safe_float(
        row["low"]
    )

    atr = max(
        safe_float(row["atr"]),
        0.01
    )

    body_ratio = safe_float(
        row["body_ratio"]
    )

    score = 0.0
    reasons = []

    if body_ratio >= 0.50:

        score += 35

    elif body_ratio >= 0.35:

        score += 20

    if direction == "BUY":

        if close > open_price:

            score += 25

        if close >= high - atr * 0.20:

            score += 25

        trigger = (
            high + atr * 0.05
        )

    else:

        if close < open_price:

            score += 25

        if close <= low + atr * 0.20:

            score += 25

        trigger = (
            low - atr * 0.05
        )

    if body_ratio < 0.30:

        reasons.append(
            "Weak trigger candle"
        )

    score = clamp(score)

    return {
        "body_ratio": round(
            body_ratio,
            3
        ),
        "signal_close": round_price(
            close
        ),
        "trigger": round_price(
            trigger
        ),
        "triggered": False,
        "valid": (
            score >= MIN_TRIGGER_QUALITY
        ),
        "score": round(
            score,
            2
        ),
        "reasons": reasons
    }


# ============================================================
# DIRECTIONAL FILTER
# ============================================================

def calculate_directional_filter(
    df,
    i,
    direction
):

    row = df.iloc[i]

    ema20 = safe_float(
        row["ema20"]
    )

    ema50 = safe_float(
        row["ema50"]
    )

    close = safe_float(
        row["close"]
    )

    score = 50.0

    if direction == "BUY":

        if ema20 > ema50:

            score += 25

        else:

            score -= 25

        if close > ema20:

            score += 15

        else:

            score -= 15

    elif direction == "SELL":

        if ema20 < ema50:

            score += 25

        else:

            score -= 25

        if close < ema20:

            score += 15

        else:

            score -= 15

    score = clamp(score)

    return {
        "direction": direction,
        "strength": round(
            score,
            2
        ),
        "bullish": [],
        "bearish": [],
        "conflict": False
    }


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    directional,
    regime,
    location,
    momentum,
    pattern_quality,
    trigger_quality
):

    # --------------------------------------------------------
    # Weighted score
    #
    # Direction      20%
    # Regime         15%
    # Location       15%
    # Momentum       15%
    # Pattern        20%
    # Trigger        15%
    # --------------------------------------------------------

    score = (

        directional["strength"] * 0.20

        + regime["score"] * 0.15

        + location["score"] * 0.15

        + momentum["score"] * 0.15

        + pattern_quality["score"] * 0.20

        + trigger_quality["score"] * 0.15
    )

    return round(
        clamp(score),
        2
    )


# ============================================================
# HARD FILTER
# ============================================================

def hard_filter(
    df,
    i,
    direction,
    regime,
    location,
    momentum,
    pattern_quality,
    trigger_quality,
    score
):

    row = df.iloc[i]

    atr = safe_float(
        row["atr"]
    )

    checks = {}

    # --------------------------------------------------------
    # Critical checks
    # --------------------------------------------------------

    checks["atr"] = (
        atr >= MINIMUM_ATR
    )

    checks["direction"] = (
        direction in ["BUY", "SELL"]
    )

    checks["market_regime"] = (
        regime["regime"]
        not in ["RANGE"]
    )

    # --------------------------------------------------------
    # Quality checks are NOT individually mandatory anymore.
    #
    # They are incorporated into Score.
    # --------------------------------------------------------

    checks["location"] = (
        location["valid"]
    )

    checks["momentum"] = (
        momentum["valid"]
    )

    checks["pattern_quality"] = (
        pattern_quality["score"]
        >= MIN_PATTERN_QUALITY
    )

    checks["trigger"] = (
        trigger_quality["score"]
        >= MIN_TRIGGER_QUALITY
    )

    failed = [
        key
        for key, value in checks.items()
        if not value
    ]

    # --------------------------------------------------------
    # Critical filter
    # --------------------------------------------------------

    critical_pass = (
        checks["atr"]
        and checks["direction"]
        and checks["market_regime"]
    )

    score_pass = (
        score >= MIN_SCORE
    )

    passed = (
        critical_pass
        and score_pass
    )

    return {
        "checks": checks,
        "failed": failed,
        "passed": passed,
        "critical_passed": critical_pass,
        "score_passed": score_pass
    }


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    df,
    i,
    direction
):

    row = df.iloc[i]

    close = safe_float(
        row["close"]
    )

    atr = max(
        safe_float(row["atr"]),
        MINIMUM_ATR
    )

    levels = get_support_resistance(
        df,
        i
    )

    support = levels["support"]
    resistance = levels["resistance"]

    if direction == "BUY":

        structure_sl = (
            support - atr * 0.20
        )

        atr_sl = (
            close - atr * 1.5
        )

        sl = min(
            structure_sl,
            atr_sl
        )

        risk = close - sl

        risk = max(
            risk,
            atr * MIN_STOP_ATR
        )

        risk = min(
            risk,
            atr * MAX_STOP_ATR
        )

        sl = close - risk

        tp = (
            close
            + risk * RISK_REWARD
        )

    else:

        structure_sl = (
            resistance + atr * 0.20
        )

        atr_sl = (
            close + atr * 1.5
        )

        sl = max(
            structure_sl,
            atr_sl
        )

        risk = sl - close

        risk = max(
            risk,
            atr * MIN_STOP_ATR
        )

        risk = min(
            risk,
            atr * MAX_STOP_ATR
        )

        sl = close + risk

        tp = (
            close
            - risk * RISK_REWARD
        )

    risk = abs(
        close - sl
    )

    reward = abs(
        tp - close
    )

    rr = (
        reward / risk
        if risk > 0
        else 0
    )

    return {
        "entry_reference": round_price(
            close
        ),
        "sl": round_price(sl),
        "tp": round_price(tp),
        "risk": round_price(risk),
        "reward": round_price(reward),
        "risk_reward": round(
            rr,
            2
        ),
        "atr": round(
            atr,
            4
        )
    }


# ============================================================
# SIGNAL ENGINE
# ============================================================

def analyze_candle(
    df,
    i,
    include_trade_levels=True
):

    if i < 55:

        return {
            "valid": False,
            "signal": "NO_TRADE",
            "reason": "Not enough candles"
        }

    row = df.iloc[i]

    patterns = detect_patterns(
        df,
        i
    )

    pattern_direction = (
        get_pattern_direction(
            patterns,
            df,
            i
        )
    )

    direction = (
        pattern_direction["direction"]
    )

    if direction == "CONFLICT":

        return {
            "valid": False,
            "signal": "NO_TRADE",
            "status": "PATTERN_CONFLICT",
            "patterns": patterns,
            "setup_candle": str(
                row["datetime"]
            )
        }

    if direction == "NONE":

        return {
            "valid": False,
            "signal": "NO_TRADE",
            "status": "NO_PATTERN",
            "patterns": [],
            "setup_candle": str(
                row["datetime"]
            )
        }

    directional = (
        calculate_directional_filter(
            df,
            i,
            direction
        )
    )

    regime = (
        calculate_market_regime(
            df,
            i
        )
    )

    location = (
        calculate_location(
            df,
            i,
            direction
        )
    )

    momentum = (
        calculate_momentum(
            df,
            i,
            direction
        )
    )

    pattern_quality = (
        calculate_pattern_quality(
            df,
            i,
            patterns,
            direction
        )
    )

    trigger_quality = (
        calculate_trigger_quality(
            df,
            i,
            direction
        )
    )

    score = calculate_score(
        directional,
        regime,
        location,
        momentum,
        pattern_quality,
        trigger_quality
    )

    filter_result = hard_filter(
        df,
        i,
        direction,
        regime,
        location,
        momentum,
        pattern_quality,
        trigger_quality,
        score
    )

    trade_levels = None

    if include_trade_levels:

        trade_levels = (
            calculate_trade_levels(
                df,
                i,
                direction
            )
        )

        if (
            trade_levels["risk_reward"]
            < MIN_RISK_REWARD
        ):

            filter_result[
                "passed"
            ] = False

            filter_result[
                "failed"
            ].append(
                "risk_reward"
            )

    signal = "NO_TRADE"

    if filter_result["passed"]:

        signal = direction

    confidence = score

    return {
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
            "Realistic Backtest"
        ],

        "symbol": SYMBOL,
        "timeframe": "M5",

        "timestamp": now_utc(),

        "setup_candle": str(
            row["datetime"]
        ),

        "patterns": patterns,

        "directional_filter": {
            **directional,
            "bullish": pattern_direction[
                "bullish"
            ],
            "bearish": pattern_direction[
                "bearish"
            ]
        },

        "market_regime": regime,

        "location": location,

        "momentum": momentum,

        "pattern_quality": pattern_quality,

        "trigger_quality": trigger_quality,

        "hard_filter": filter_result,

        "score": score,

        "confidence": confidence,

        "probability": confidence,

        "trend": (
            "UPTREND"
            if safe_float(row["ema20"])
            > safe_float(row["ema50"])
            else "DOWNTREND"
        ),

        "ema20": round_price(
            row["ema20"]
        ),

        "ema50": round_price(
            row["ema50"]
        ),

        "rsi": round(
            safe_float(row["rsi"]),
            1
        ),

        "atr": round(
            safe_float(row["atr"]),
            4
        ),

        "support": location[
            "support"
        ],

        "resistance": location[
            "resistance"
        ],

        "entry_rule":
            "NEXT CANDLE OPEN",

        "next_candle_entry": (
            signal in ["BUY", "SELL"]
        ),

        "signal": signal,

        "valid": (
            signal in ["BUY", "SELL"]
        ),

        "status": (
            "READY"
            if signal in ["BUY", "SELL"]
            else "HARD_FILTER_FAILED"
        ),

        "trade_levels":
            trade_levels
    }


# ============================================================
# BACKTEST ENGINE
# ============================================================

def simulate_trade(
    df,
    signal_index,
    direction,
    levels
):

    # Entry is NEXT CANDLE OPEN
    entry_index = signal_index + 1

    if entry_index >= len(df):

        return None

    entry_candle = df.iloc[
        entry_index
    ]

    raw_entry = safe_float(
        entry_candle["open"]
    )

    sl = safe_float(
        levels["sl"]
    )

    tp = safe_float(
        levels["tp"]
    )

    risk = abs(
        raw_entry - sl
    )

    if risk <= 0:

        return None

    # --------------------------------------------------------
    # Spread / slippage
    # --------------------------------------------------------

    if direction == "BUY":

        entry = (
            raw_entry
            + SPREAD / 2
            + SLIPPAGE
        )

    else:

        entry = (
            raw_entry
            - SPREAD / 2
            - SLIPPAGE
        )

    # Recalculate R based on actual entry
    if direction == "BUY":

        risk = abs(
            entry - sl
        )

    else:

        risk = abs(
            sl - entry
        )

    if risk <= 0:

        return None

    # --------------------------------------------------------
    # Forward simulation
    # --------------------------------------------------------

    end_index = min(
        len(df),
        entry_index + FORWARD_BARS
    )

    result = "TIMEOUT"

    exit_price = None
    exit_index = None

    max_favorable = 0.0
    max_adverse = 0.0

    moved_to_breakeven = False

    for j in range(
        entry_index,
        end_index
    ):

        candle = df.iloc[j]

        high = safe_float(
            candle["high"]
        )

        low = safe_float(
            candle["low"]
        )

        if direction == "BUY":

            mfe = (
                high - entry
            ) / risk

            mae = (
                low - entry
            ) / risk

            max_favorable = max(
                max_favorable,
                mfe
            )

            max_adverse = min(
                max_adverse,
                mae
            )

            # ------------------------------------------------
            # Break-even
            # ------------------------------------------------

            if (
                BREAK_EVEN
                and not moved_to_breakeven
                and mfe >= BREAK_EVEN_R
            ):

                sl = max(
                    sl,
                    entry
                )

                moved_to_breakeven = True

            # ------------------------------------------------
            # Conservative:
            # If SL and TP touched same candle,
            # assume SL first.
            # ------------------------------------------------

            if low <= sl:

                exit_price = sl
                exit_index = j

                if moved_to_breakeven:
                    result = "BREAKEVEN"
                else:
                    result = "LOSS"

                break

            if high >= tp:

                exit_price = tp
                exit_index = j
                result = "WIN"

                break

        else:

            mfe = (
                entry - low
            ) / risk

            mae = (
                entry - high
            ) / risk

            max_favorable = max(
                max_favorable,
                mfe
            )

            max_adverse = min(
                max_adverse,
                mae
            )

            if (
                BREAK_EVEN
                and not moved_to_breakeven
                and mfe >= BREAK_EVEN_R
            ):

                sl = min(
                    sl,
                    entry
                )

                moved_to_breakeven = True

            if high >= sl:

                exit_price = sl
                exit_index = j

                if moved_to_breakeven:
                    result = "BREAKEVEN"
                else:
                    result = "LOSS"

                break

            if low <= tp:

                exit_price = tp
                exit_index = j
                result = "WIN"

                break

    # --------------------------------------------------------
    # Timeout
    # --------------------------------------------------------

    if result == "TIMEOUT":

        exit_index = end_index - 1

        if exit_index >= entry_index:

            exit_price = safe_float(
                df.iloc[
                    exit_index
                ]["close"]
            )

        else:

            exit_price = entry

    # --------------------------------------------------------
    # R result
    # --------------------------------------------------------

    if direction == "BUY":

        r = (
            exit_price - entry
        ) / risk

    else:

        r = (
            entry - exit_price
        ) / risk

    if result == "BREAKEVEN":

        r = 0.0

    return {
        "setup_index": signal_index,
        "entry_index": entry_index,
        "exit_index": exit_index,

        "setup_time": str(
            df.iloc[
                signal_index
            ]["datetime"]
        ),

        "entry_time": str(
            df.iloc[
                entry_index
            ]["datetime"]
        ),

        "exit_time": str(
            df.iloc[
                exit_index
            ]["datetime"]
        ),

        "direction": direction,

        "entry": round_price(
            entry
        ),

        "sl": round_price(sl),

        "tp": round_price(tp),

        "exit": round_price(
            exit_price
        ),

        "result": result,

        "r": round(
            r,
            4
        ),

        "mae_r": round(
            max_adverse,
            4
        ),

        "mfe_r": round(
            max_favorable,
            4
        )
    }


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    df,
    test_points=200
):

    df = df.copy()

    test_points = min(
        int(test_points),
        len(df) - 60
    )

    start = max(
        55,
        len(df) - test_points
    )

    trades = []

    pattern_frequency = {}

    regime_frequency = {}

    score_bucket_candidates = {
        "70-74": 0,
        "75-79": 0,
        "80-84": 0,
        "85-89": 0,
        "90-94": 0,
        "95-100": 0
    }

    pattern_candidates = 0
    score_passed = 0
    hard_filter_passed = 0

    for i in range(
        start,
        len(df) - 1
    ):

        result = analyze_candle(
            df,
            i,
            include_trade_levels=True
        )

        patterns = result.get(
            "patterns",
            []
        )

        for pattern in patterns:

            pattern_frequency[
                pattern
            ] = (
                pattern_frequency.get(
                    pattern,
                    0
                ) + 1
            )

        regime = (
            result
            .get(
                "market_regime",
                {}
            )
            .get(
                "regime"
            )
        )

        if regime:

            regime_frequency[
                regime
            ] = (
                regime_frequency.get(
                    regime,
                    0
                ) + 1
            )

        if not patterns:

            continue

        pattern_candidates += 1

        score = safe_float(
            result.get(
                "score"
            )
        )

        if score >= MIN_SCORE:

            score_passed += 1

            if score < 75:
                bucket = "70-74"
            elif score < 80:
                bucket = "75-79"
            elif score < 85:
                bucket = "80-84"
            elif score < 90:
                bucket = "85-89"
            elif score < 95:
                bucket = "90-94"
            else:
                bucket = "95-100"

            score_bucket_candidates[
                bucket
            ] += 1

        hard_pass = (
            result
            .get(
                "hard_filter",
                {}
            )
            .get(
                "passed",
                False
            )
        )

        if not hard_pass:

            continue

        hard_filter_passed += 1

        direction = result.get(
            "signal"
        )

        levels = result.get(
            "trade_levels"
        )

        if (
            direction
            not in ["BUY", "SELL"]
            or not levels
        ):

            continue

        trade = simulate_trade(
            df,
            i,
            direction,
            levels
        )

        if trade:

            trade["score"] = score

            trade["patterns"] = patterns

            trades.append(
                trade
            )

    # ========================================================
    # PERFORMANCE
    # ========================================================

    wins = [
        t for t in trades
        if t["result"] == "WIN"
    ]

    losses = [
        t for t in trades
        if t["result"] == "LOSS"
    ]

    breakevens = [
        t for t in trades
        if t["result"] == "BREAKEVEN"
    ]

    timeouts = [
        t for t in trades
        if t["result"] == "TIMEOUT"
    ]

    resolved = (
        len(wins)
        + len(losses)
        + len(breakevens)
    )

    total_r = sum(
        t["r"]
        for t in trades
    )

    total_profit_r = sum(
        max(t["r"], 0)
        for t in trades
    )

    total_loss_r = abs(
        sum(
            min(t["r"], 0)
            for t in trades
        )
    )

    profit_factor = (
        total_profit_r
        / total_loss_r
        if total_loss_r > 0
        else (
            float("inf")
            if total_profit_r > 0
            else 0
        )
    )

    average_r = (
        total_r / len(trades)
        if trades
        else 0
    )

    win_rate = (
        len(wins)
        / resolved
        * 100
        if resolved
        else 0
    )

    loss_rate = (
        len(losses)
        / len(trades)
        * 100
        if trades
        else 0
    )

    breakeven_rate = (
        len(breakevens)
        / len(trades)
        * 100
        if trades
        else 0
    )

    timeout_rate = (
        len(timeouts)
        / len(trades)
        * 100
        if trades
        else 0
    )

    # --------------------------------------------------------
    # MAE / MFE
    # --------------------------------------------------------

    average_mae = (
        np.mean(
            [
                t["mae_r"]
                for t in trades
            ]
        )
        if trades
        else 0
    )

    average_mfe = (
        np.mean(
            [
                t["mfe_r"]
                for t in trades
            ]
        )
        if trades
        else 0
    )

    average_score = (
        np.mean(
            [
                t["score"]
                for t in trades
            ]
        )
        if trades
        else 0
    )

    # --------------------------------------------------------
    # Losing streak
    # --------------------------------------------------------

    longest_losing_streak = 0
    current_streak = 0

    for trade in trades:

        if trade["result"] == "LOSS":

            current_streak += 1

            longest_losing_streak = max(
                longest_losing_streak,
                current_streak
            )

        else:

            current_streak = 0

    # --------------------------------------------------------
    # Drawdown
    # --------------------------------------------------------

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for trade in trades:

        equity += trade["r"]

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

    # --------------------------------------------------------
    # Direction performance
    # --------------------------------------------------------

    direction_performance = {}

    for direction in [
        "BUY",
        "SELL"
    ]:

        direction_trades = [
            t for t in trades
            if t["direction"] == direction
        ]

        direction_wins = [
            t for t in direction_trades
            if t["result"] == "WIN"
        ]

        direction_losses = [
            t for t in direction_trades
            if t["result"] == "LOSS"
        ]

        direction_r = sum(
            t["r"]
            for t in direction_trades
        )

        profit_r = sum(
            max(t["r"], 0)
            for t in direction_trades
        )

        loss_r = abs(
            sum(
                min(t["r"], 0)
                for t in direction_trades
            )
        )

        pf = (
            profit_r / loss_r
            if loss_r > 0
            else 0
        )

        direction_performance[
            direction
        ] = {

            "trades":
                len(direction_trades),

            "wins":
                len(direction_wins),

            "losses":
                len(direction_losses),

            "breakevens":
                len([
                    t for t in direction_trades
                    if t["result"] == "BREAKEVEN"
                ]),

            "timeouts":
                len([
                    t for t in direction_trades
                    if t["result"] == "TIMEOUT"
                ]),

            "win_rate_percent":
                round(
                    (
                        len(direction_wins)
                        / len(direction_trades)
                        * 100
                    )
                    if direction_trades
                    else 0,
                    2
                ),

            "average_r":
                round(
                    (
                        direction_r
                        / len(direction_trades)
                    )
                    if direction_trades
                    else 0,
                    4
                ),

            "profit_factor":
                round(
                    pf,
                    3
                ),

            "net_profit_percent":
                round(
                    direction_r,
                    2
                )
        }

    # --------------------------------------------------------
    # Score performance
    # --------------------------------------------------------

    score_performance = {}

    for bucket in score_bucket_candidates:

        if bucket == "70-74":
            low, high = 70, 75
        elif bucket == "75-79":
            low, high = 75, 80
        elif bucket == "80-84":
            low, high = 80, 85
        elif bucket == "85-89":
            low, high = 85, 90
        elif bucket == "90-94":
            low, high = 90, 95
        else:
            low, high = 95, 101

        bucket_trades = [
            t for t in trades
            if low <= t["score"] < high
        ]

        bwins = [
            t for t in bucket_trades
            if t["result"] == "WIN"
        ]

        blosses = [
            t for t in bucket_trades
            if t["result"] == "LOSS"
        ]

        br = sum(
            t["r"]
            for t in bucket_trades
        )

        bp = sum(
            max(t["r"], 0)
            for t in bucket_trades
        )

        bl = abs(
            sum(
                min(t["r"], 0)
                for t in bucket_trades
            )
        )

        score_performance[
            bucket
        ] = {

            "trades":
                len(bucket_trades),

            "wins":
                len(bwins),

            "losses":
                len(blosses),

            "breakevens":
                len([
                    t for t in bucket_trades
                    if t["result"] == "BREAKEVEN"
                ]),

            "timeouts":
                len([
                    t for t in bucket_trades
                    if t["result"] == "TIMEOUT"
                ]),

            "win_rate_percent":
                round(
                    (
                        len(bwins)
                        / len(bucket_trades)
                        * 100
                    )
                    if bucket_trades
                    else 0,
                    2
                ),

            "average_r":
                round(
                    (
                        br / len(bucket_trades)
                    )
                    if bucket_trades
                    else 0,
                    4
                ),

            "profit_factor":
                round(
                    (
                        bp / bl
                    )
                    if bl > 0
                    else 0,
                    3
                ),

            "net_profit_percent":
                round(
                    br,
                    2
                )
        }

    # --------------------------------------------------------
    # Recent trades
    # --------------------------------------------------------

    recent_trades = trades[-20:]

    # --------------------------------------------------------
    # Regime performance
    # --------------------------------------------------------

    regime_performance = {}

    for regime in regime_frequency:

        regime_trades = [
            t for t in trades
            if (
                t.get("regime")
                == regime
            )
        ]

        # Usually empty because regime is not
        # attached to old trade object.
        # Kept for API compatibility.

        if regime_trades:

            regime_performance[
                regime
            ] = {
                "trades":
                    len(regime_trades)
            }

    # --------------------------------------------------------
    # Final object
    # --------------------------------------------------------

    return {

        "status": "completed",

        "system":
            "Quality Filtered Next Candle Entry Engine",

        "symbol": SYMBOL,

        "timeframe": "M5",

        "data_source":
            "Twelve Data XAU/USD",

        "candles_available":
            len(df),

        "test_points":
            test_points,

        "pipeline_counts": {

            "pattern_candidates":
                pattern_candidates,

            "score_passed":
                score_passed,

            "hard_filter_passed":
                hard_filter_passed,

            "executed_trades":
                len(trades)
        },

        "signals": {

            "buy":
                len([
                    t for t in trades
                    if t["direction"] == "BUY"
                ]),

            "sell":
                len([
                    t for t in trades
                    if t["direction"] == "SELL"
                ]),

            "total":
                len(trades)
        },

        "results": {

            "wins":
                len(wins),

            "losses":
                len(losses),

            "breakevens":
                len(breakevens),

            "timeouts":
                len(timeouts),

            "resolved":
                resolved
        },

        "performance": {

            "total_profit_percent":
                round(
                    total_profit_r,
                    2
                ),

            "total_loss_percent":
                round(
                    total_loss_r,
                    2
                ),

            "net_profit_percent":
                round(
                    total_r,
                    2
                ),

            "average_r":
                round(
                    average_r,
                    4
                ),

            "expectancy_r":
                round(
                    average_r,
                    4
                ),

            "expectancy_percent":
                round(
                    average_r,
                    2
                ),

            "win_rate_percent":
                round(
                    win_rate,
                    2
                ),

            "resolved_win_rate_percent":
                round(
                    win_rate,
                    2
                ),

            "loss_rate_percent":
                round(
                    loss_rate,
                    2
                ),

            "breakeven_rate_percent":
                round(
                    breakeven_rate,
                    2
                ),

            "timeout_rate_percent":
                round(
                    timeout_rate,
                    2
                ),

            "profit_factor":
                round(
                    profit_factor,
                    3
                ),

            "profit_factor_r":
                round(
                    profit_factor,
                    3
                ),

            "average_score":
                round(
                    average_score,
                    2
                ),

            "average_mae_r":
                round(
                    average_mae,
                    4
                ),

            "average_mfe_r":
                round(
                    average_mfe,
                    4
                ),

            "longest_losing_streak":
                longest_losing_streak,

            "max_drawdown_percent":
                round(
                    max_drawdown,
                    2
                )
        },

        "direction_performance":
            direction_performance,

        "pattern_frequency":
            pattern_frequency,

        "regime_frequency":
            regime_frequency,

        "regime_performance":
            regime_performance,

        "score_bucket_candidates":
            score_bucket_candidates,

        "score_performance":
            score_performance,

        "recent_trades":
            recent_trades,

        "rules": {

            "entry":
                "NEXT CANDLE OPEN",

            "minimum_score":
                MIN_SCORE,

            "minimum_pattern_quality":
                MIN_PATTERN_QUALITY,

            "minimum_trigger_quality":
                MIN_TRIGGER_QUALITY,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "risk_reward":
                RISK_REWARD,

            "minimum_atr":
                MINIMUM_ATR,

            "min_stop_atr":
                MIN_STOP_ATR,

            "max_stop_atr":
                MAX_STOP_ATR,

            "forward_bars":
                FORWARD_BARS,

            "spread":
                SPREAD,

            "slippage":
                SLIPPAGE,

            "break_even":
                BREAK_EVEN,

            "break_even_r":
                BREAK_EVEN_R,

            "trigger_lookback":
                TRIGGER_LOOKBACK
        },

        "warning":
            "Historical simulation only. Twelve Data OHLC candles do not contain intrabar tick sequence. Therefore when SL and TP are both touched inside the same candle, the backtest conservatively assumes SL was hit first. Spread and slippage assumptions are included. Entry is always the NEXT CANDLE OPEN after a confirmed setup candle."
    }


# ============================================================
# ROUTE: HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "status": "online",

        "service":
            "XAU/USD M5 Quality Filtered Next Candle Entry Engine",

        "symbol": SYMBOL,

        "timeframe": "M5",

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
            "Realistic Backtest"
        ],

        "minimum_score":
            MIN_SCORE,

        "endpoints": [

            "/",

            "/health",

            "/signal",

            "/backtest",

            "/backtest/200",

            "/backtest/800",

            "/backtest/1000",

            "/test-data",

            "/test-telegram"
        ]
    })


# ============================================================
# ROUTE: HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status": "healthy",

        "service":
            "XAU/USD Signal Engine",

        "symbol": SYMBOL,

        "timeframe": "M5",

        "twelve_data":
            bool(TWELVE_DATA_API_KEY),

        "telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),

        "timestamp":
            now_utc()
    })


# ============================================================
# ROUTE: TEST DATA
# ============================================================

@app.route("/test-data")
def test_data():

    try:

        df = get_market_data(
            1000
        )

        latest = df.iloc[-1]

        return jsonify({

            "status": "success",

            "message":
                "Twelve Data connection is working",

            "symbol": SYMBOL,

            "timeframe": "M5",

            "candles":
                len(df),

            "latest": {

                "datetime":
                    str(
                        latest["datetime"]
                    ),

                "open":
                    round_price(
                        latest["open"]
                    ),

                "high":
                    round_price(
                        latest["high"]
                    ),

                "low":
                    round_price(
                        latest["low"]
                    ),

                "close":
                    round_price(
                        latest["close"]
                    )
            }
        })

    except Exception as e:

        return jsonify({

            "status": "error",

            "message": str(e),

            "trace":
                traceback.format_exc()
        }), 500


# ============================================================
# ROUTE: SIGNAL
# ============================================================

@app.route("/signal")
def signal():

    try:

        df = get_market_data(
            1000
        )

        df = calculate_indicators(
            df
        )

        index = len(df) - 1

        result = analyze_candle(
            df,
            index
        )

        # ----------------------------------------------------
        # Send Telegram ONLY when valid trade
        # ----------------------------------------------------

        if result.get(
            "valid"
        ):

            direction = result[
                "signal"
            ]

            levels = result[
                "trade_levels"
            ]

            telegram_message = f"""
<b>🚨 XAU/USD SIGNAL</b>

<b>Direction:</b> {direction}

<b>Timeframe:</b> M5

<b>Score:</b> {result['score']}

<b>Probability:</b> {result['probability']}%

<b>Entry:</b> NEXT CANDLE OPEN

<b>SL:</b> {levels['sl']}

<b>TP:</b> {levels['tp']}

<b>RR:</b> {levels['risk_reward']}

<b>RSI:</b> {result['rsi']}

<b>ATR:</b> {result['atr']}

<b>Pattern:</b>
{", ".join(result['patterns'])}

<b>Setup:</b>
{result['setup_candle']}
"""

            telegram = send_telegram(
                telegram_message
            )

            result[
                "telegram"
            ] = telegram

        else:

            result[
                "telegram"
            ] = {
                "success": False,
                "message":
                    "No trade - Telegram not sent"
            }

        return jsonify(
            result
        )

    except Exception as e:

        return jsonify({

            "status": "error",

            "message": str(e),

            "trace":
                traceback.format_exc()
        }), 500


# ============================================================
# BACKTEST INTERNAL
# ============================================================

def backtest_endpoint(
    points
):

    try:

        # Need extra candles for indicators
        outputsize = max(
            points + 100,
            300
        )

        df = get_market_data(
            outputsize
        )

        df = calculate_indicators(
            df
        )

        result = run_backtest(
            df,
            points
        )

        return jsonify(
            result
        )

    except Exception as e:

        return jsonify({

            "status": "error",

            "message": str(e),

            "trace":
                traceback.format_exc()
        }), 500


# ============================================================
# ROUTES: BACKTEST
# ============================================================

@app.route("/backtest")
def backtest():

    return backtest_endpoint(
        200
    )


@app.route("/backtest/200")
def backtest_200():

    return backtest_endpoint(
        200
    )


@app.route("/backtest/800")
def backtest_800():

    return backtest_endpoint(
        800
    )


@app.route("/backtest/1000")
def backtest_1000():

    return backtest_endpoint(
        1000
    )


# ============================================================
# ROUTE: TELEGRAM TEST
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    result = send_telegram(
        """
<b>✅ XAU/USD ENGINE</b>

Telegram test message sent successfully.

System:
Quality Filtered Next Candle Entry Engine

Symbol:
XAU/USD

Timeframe:
M5
"""
    )

    if result["success"]:

        return jsonify({

            "status":
                "success",

            "telegram":
                True,

            "message":
                "Telegram test message sent successfully"
        })

    return jsonify({

        "status":
            "error",

        "telegram":
            False,

        "message":
            result["message"]
    }), 500


# ============================================================
# STARTUP
# ============================================================

def startup_message():

    message = f"""
<b>🟢 XAU/USD ENGINE STARTED</b>

<b>Symbol:</b> {SYMBOL}

<b>Timeframe:</b> M5

<b>Engine:</b>
Quality Filtered Next Candle Entry Engine

<b>Entry:</b>
NEXT CANDLE OPEN

<b>Minimum Score:</b>
{MIN_SCORE}

<b>Minimum RR:</b>
{MIN_RISK_REWARD}

<b>ATR SL:</b>
{MIN_STOP_ATR} - {MAX_STOP_ATR} ATR

<b>Break Even:</b>
{"ON" if BREAK_EVEN else "OFF"}

<b>Time:</b>
{now_utc()}
"""

    return send_telegram(
        message
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("XAU/USD QUALITY FILTERED NEXT CANDLE ENTRY ENGINE")
    print("=" * 70)

    print(
        f"Symbol       : {SYMBOL}"
    )

    print(
        f"Timeframe    : M5"
    )

    print(
        f"Min Score    : {MIN_SCORE}"
    )

    print(
        f"Min RR       : {MIN_RISK_REWARD}"
    )

    print(
        f"ATR          : {MIN_STOP_ATR} - {MAX_STOP_ATR}"
    )

    print(
        f"Break Even   : {BREAK_EVEN}"
    )

    print(
        f"Twelve Data  : "
        f"{'OK' if TWELVE_DATA_API_KEY else 'NOT CONFIGURED'}"
    )

    print(
        f"Telegram     : "
        f"{'OK' if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else 'NOT CONFIGURED'}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # Startup Telegram
    # --------------------------------------------------------

    if (
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    ):

        try:

            result = startup_message()

            print(
                "Telegram startup:",
                result
            )

        except Exception as e:

            print(
                "Telegram startup error:",
                e
            )

    # --------------------------------------------------------
    # Flask
    # --------------------------------------------------------

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

import os
import math
import traceback
from datetime import datetime, timezone, timedelta

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
# TRADING ENGINE RULES
# ============================================================

MIN_SCORE = float(
    os.getenv("MIN_SCORE", "70")
)

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
    "BREAK_EVEN",
    "true"
).lower() == "true"

BREAK_EVEN_R = float(
    os.getenv("BREAK_EVEN_R", "1.0")
)

CANDLES = int(
    os.getenv("CANDLES", "1000")
)

# ป้องกันการเปิด trade ซ้อนกัน
ALLOW_OVERLAPPING_TRADES = (
    os.getenv(
        "ALLOW_OVERLAPPING_TRADES",
        "false"
    ).lower() == "true"
)

# SELL is intentionally more conservative until the historical sample
# proves that the short side has enough edge. These are filters, not
# fabricated probabilities.
SELL_MIN_SCORE = float(os.getenv("SELL_MIN_SCORE", "75"))
SELL_MIN_PATTERN_QUALITY = float(
    os.getenv("SELL_MIN_PATTERN_QUALITY", "60")
)
SELL_MIN_TRIGGER_QUALITY = float(
    os.getenv("SELL_MIN_TRIGGER_QUALITY", "60")
)

# Historical probability is only considered meaningful after this many
# resolved trades in the relevant subgroup. It is reported either way,
# but the confidence flag prevents a 1/1 or 2/2 sample from looking robust.
MIN_HISTORICAL_SAMPLE = int(os.getenv("MIN_HISTORICAL_SAMPLE", "20"))

# When true, /signal runs a compact historical lookup so the response
# contains empirical probability separately from the current Score.
SIGNAL_HISTORY_POINTS = int(os.getenv("SIGNAL_HISTORY_POINTS", "200"))


# ============================================================
# GLOBAL CACHE
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


def clamp(
    value,
    minimum=0.0,
    maximum=100.0
):

    return max(
        minimum,
        min(
            maximum,
            safe_float(value)
        )
    )


def round_price(value):

    return round(
        safe_float(value),
        5
    )


def now_utc():

    return datetime.now(
        timezone.utc
    ).isoformat()


def timeframe_minutes():

    mapping = {
        "1min": 1,
        "5min": 5,
        "15min": 15,
        "30min": 30,
        "45min": 45,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "1day": 1440
    }

    return mapping.get(
        TIMEFRAME,
        5
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):

        return {
            "success": False,
            "message":
                "Telegram credentials not configured"
        }

    try:

        url = (
            "https://api.telegram.org/bot"
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
                "message":
                    "Telegram message sent successfully"
            }

        return {
            "success": False,
            "message":
                response.text
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ============================================================
# TWELVE DATA
# ============================================================

def get_market_data(
    outputsize=CANDLES
):

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
        "outputsize":
            min(
                int(outputsize),
                5000
            ),
        "apikey":
            TWELVE_DATA_API_KEY,
        "format":
            "JSON"
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if (
        data.get("status")
        == "error"
    ):

        raise RuntimeError(
            data.get(
                "message",
                "Twelve Data error"
            )
        )

    values = data.get(
        "values"
    )

    if not values:

        raise RuntimeError(
            "No candle data returned by Twelve Data"
        )

    df = pd.DataFrame(
        values
    )

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
    ).reset_index(
        drop=True
    )

    return df


# ============================================================
# REMOVE INCOMPLETE CANDLE
# ============================================================

def remove_incomplete_last_candle(
    df
):

    if df.empty:
        return df

    try:

        last_time = df.iloc[-1][
            "datetime"
        ]

        if last_time.tzinfo is None:

            last_time = last_time.replace(
                tzinfo=timezone.utc
            )

        else:

            last_time = last_time.astimezone(
                timezone.utc
            )

        close_time = (
            last_time
            + timedelta(
                minutes=timeframe_minutes()
            )
        )

        current_time = datetime.now(
            timezone.utc
        )

        if current_time < close_time:

            return df.iloc[:-1].copy()

        return df

    except Exception:

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
        .ewm(
            span=20,
            adjust=False
        )
        .mean()
    )

    df["ema50"] = (
        df["close"]
        .ewm(
            span=50,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False
    ).mean()

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            np.nan
        )
    )

    df["rsi"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    df["rsi"] = df[
        "rsi"
    ].fillna(50)

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    previous_close = (
        df["close"].shift(1)
    )

    tr1 = (
        df["high"]
        - df["low"]
    )

    tr2 = (
        df["high"]
        - previous_close
    ).abs()

    tr3 = (
        df["low"]
        - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    df["atr"] = (
        true_range
        .rolling(14)
        .mean()
    )

    df["atr"] = (
        df["atr"]
        .bfill()
        .fillna(1.0)
    )

    # --------------------------------------------------------
    # Candle
    # --------------------------------------------------------

    df["body"] = (
        df["close"]
        - df["open"]
    ).abs()

    df["range"] = (
        df["high"]
        - df["low"]
    ).replace(
        0,
        np.nan
    )

    df["body_ratio"] = (
        df["body"]
        / df["range"]
    )

    df["body_ratio"] = (
        df["body_ratio"]
        .fillna(0)
        .clip(0, 1)
    )

    df["upper_wick"] = (
        df["high"]
        - df[
            ["open", "close"]
        ].max(axis=1)
    )

    df["lower_wick"] = (
        df[
            ["open", "close"]
        ].min(axis=1)
        - df["low"]
    )

    # --------------------------------------------------------
    # ATR ratio
    # --------------------------------------------------------

    atr_average = (
        df["atr"]
        .rolling(50)
        .mean()
        .replace(
            0,
            np.nan
        )
    )

    df["atr_ratio"] = (
        df["atr"]
        / atr_average
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

def get_support_resistance(
    df,
    index,
    lookback=50
):

    start = max(
        0,
        index - lookback
    )

    window = df.iloc[
        start:index + 1
    ]

    if len(window) < 5:

        return {
            "support":
                safe_float(
                    df.iloc[index]["low"]
                ),

            "resistance":
                safe_float(
                    df.iloc[index]["high"]
                )
        }

    return {
        "support":
            safe_float(
                window["low"].min()
            ),

        "resistance":
            safe_float(
                window["high"].max()
            )
    }


# ============================================================
# LOCAL PIVOTS
# ============================================================

def is_local_high(
    df,
    i,
    left=2,
    right=2
):

    if (
        i - left < 0
        or i + right >= len(df)
    ):
        return False

    value = safe_float(
        df.iloc[i]["high"]
    )

    left_values = [
        safe_float(
            df.iloc[j]["high"]
        )
        for j in range(
            i - left,
            i
        )
    ]

    right_values = [
        safe_float(
            df.iloc[j]["high"]
        )
        for j in range(
            i + 1,
            i + right + 1
        )
    ]

    return (
        value >= max(left_values)
        and value >= max(right_values)
    )


def is_local_low(
    df,
    i,
    left=2,
    right=2
):

    if (
        i - left < 0
        or i + right >= len(df)
    ):
        return False

    value = safe_float(
        df.iloc[i]["low"]
    )

    left_values = [
        safe_float(
            df.iloc[j]["low"]
        )
        for j in range(
            i - left,
            i
        )
    ]

    right_values = [
        safe_float(
            df.iloc[j]["low"]
        )
        for j in range(
            i + 1,
            i + right + 1
        )
    ]

    return (
        value <= min(left_values)
        and value <= min(right_values)
    )


# ============================================================
# PATTERN DETECTION
# ============================================================

def detect_patterns(
    df,
    i
):

    if i < 5:
        return []

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    patterns = []

    o = safe_float(
        row["open"]
    )

    h = safe_float(
        row["high"]
    )

    l = safe_float(
        row["low"]
    )

    c = safe_float(
        row["close"]
    )

    po = safe_float(
        prev["open"]
    )

    ph = safe_float(
        prev["high"]
    )

    pl = safe_float(
        prev["low"]
    )

    pc = safe_float(
        prev["close"]
    )

    body = abs(
        c - o
    )

    candle_range = max(
        h - l,
        1e-9
    )

    upper_wick = (
        h
        - max(o, c)
    )

    lower_wick = (
        min(o, c)
        - l
    )

    # ========================================================
    # ENGULFING
    # ========================================================

    if (
        pc < po
        and c > o
        and o <= pc
        and c >= po
    ):

        patterns.append(
            "Bullish Engulfing"
        )

    if (
        pc > po
        and c < o
        and o >= pc
        and c <= po
    ):

        patterns.append(
            "Bearish Engulfing"
        )

    # ========================================================
    # HAMMER
    # ========================================================

    if (
        body > 0
        and lower_wick >= body * 2
        and upper_wick <= body
        and candle_range > 0
    ):

        patterns.append(
            "Hammer"
        )

    # ========================================================
    # SHOOTING STAR
    # ========================================================

    if (
        body > 0
        and upper_wick >= body * 2
        and lower_wick <= body
        and candle_range > 0
    ):

        patterns.append(
            "Shooting Star"
        )

    # ========================================================
    # MORNING STAR
    # ========================================================

    if i >= 2:

        r2 = df.iloc[i - 2]

        o2 = safe_float(
            r2["open"]
        )

        c2 = safe_float(
            r2["close"]
        )

        first_bearish = (
            c2 < o2
        )

        second_small = (
            abs(pc - po)
            < abs(c2 - o2) * 0.5
        )

        third_bullish = (
            c > o
        )

        if (
            first_bearish
            and second_small
            and third_bullish
            and c > (o2 + c2) / 2
        ):

            patterns.append(
                "Morning Star"
            )

    # ========================================================
    # EVENING STAR
    # ========================================================

    if i >= 2:

        r2 = df.iloc[i - 2]

        o2 = safe_float(
            r2["open"]
        )

        c2 = safe_float(
            r2["close"]
        )

        first_bullish = (
            c2 > o2
        )

        second_small = (
            abs(pc - po)
            < abs(c2 - o2) * 0.5
        )

        third_bearish = (
            c < o
        )

        if (
            first_bullish
            and second_small
            and third_bearish
            and c < (o2 + c2) / 2
        ):

            patterns.append(
                "Evening Star"
            )

    # ========================================================
    # DOUBLE TOP / BOTTOM
    # ========================================================

    lookback_start = max(
        2,
        i - 20
    )

    pivot_highs = []

    pivot_lows = []

    for p in range(
        lookback_start,
        i - 1
    ):

        if is_local_high(
            df,
            p,
            2,
            2
        ):

            pivot_highs.append(p)

        if is_local_low(
            df,
            p,
            2,
            2
        ):

            pivot_lows.append(p)

    atr = max(
        safe_float(row["atr"]),
        0.01
    )

    tolerance = max(
        atr * 0.35,
        0.50
    )

    # Double Top
    if (
        len(pivot_highs) >= 2
    ):

        p1 = pivot_highs[-2]
        p2 = pivot_highs[-1]

        h1 = safe_float(
            df.iloc[p1]["high"]
        )

        h2 = safe_float(
            df.iloc[p2]["high"]
        )

        if (
            abs(h1 - h2)
            <= tolerance
            and c < h2
        ):

            patterns.append(
                "Double Top"
            )

    # Double Bottom
    if (
        len(pivot_lows) >= 2
    ):

        p1 = pivot_lows[-2]
        p2 = pivot_lows[-1]

        l1 = safe_float(
            df.iloc[p1]["low"]
        )

        l2 = safe_float(
            df.iloc[p2]["low"]
        )

        if (
            abs(l1 - l2)
            <= tolerance
            and c > l2
        ):

            patterns.append(
                "Double Bottom"
            )

    # ========================================================
    # BREAKOUT
    # ========================================================

    breakout_start = max(
        0,
        i - 6
    )

    breakout_window = df.iloc[
        breakout_start:i
    ]

    if len(
        breakout_window
    ) >= 5:

        previous_resistance = safe_float(
            breakout_window["high"].max()
        )

        previous_support = safe_float(
            breakout_window["low"].min()
        )

        if (
            c > previous_resistance
            and c > o
        ):

            patterns.append(
                "Bullish Breakout"
            )

        if (
            c < previous_support
            and c < o
        ):

            patterns.append(
                "Bearish Breakout"
            )

    # ========================================================
    # PULLBACK
    # ========================================================

    ema20 = safe_float(
        row["ema20"]
    )

    ema50 = safe_float(
        row["ema50"]
    )

    if (
        ema20 > ema50
        and l <= ema20
        and c > ema20
        and c > o
    ):

        patterns.append(
            "Bullish Pullback"
        )

    elif (
        ema20 < ema50
        and h >= ema20
        and c < ema20
        and c < o
    ):

        patterns.append(
            "Bearish Pullback"
        )

    return list(
        dict.fromkeys(
            patterns
        )
    )


# ============================================================
# PATTERN DIRECTION
# ============================================================

BULLISH_PATTERNS = {
    "Bullish Engulfing",
    "Hammer",
    "Morning Star",
    "Double Bottom",
    "Bullish Breakout",
    "Bullish Pullback"
}

BEARISH_PATTERNS = {
    "Bearish Engulfing",
    "Shooting Star",
    "Evening Star",
    "Double Top",
    "Bearish Breakout",
    "Bearish Pullback"
}


def get_pattern_direction(
    patterns
):

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

    if bullish and bearish:

        return {
            "direction":
                "CONFLICT",

            "bullish":
                bullish,

            "bearish":
                bearish,

            "conflict":
                True
        }

    if bullish:

        return {
            "direction":
                "BUY",

            "bullish":
                bullish,

            "bearish":
                [],

            "conflict":
                False
        }

    if bearish:

        return {
            "direction":
                "SELL",

            "bullish":
                [],

            "bearish":
                bearish,

            "conflict":
                False
        }

    return {
        "direction":
            "NONE",

        "bullish":
            [],

        "bearish":
            [],

        "conflict":
            False
    }


# ============================================================
# MARKET REGIME
# ============================================================

def calculate_market_regime(
    df,
    i
):

    row = df.iloc[i]

    ema20 = safe_float(
        row["ema20"]
    )

    ema50 = safe_float(
        row["ema50"]
    )

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
            abs(
                ema20 - ema50
            )
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
            regime = (
                "LOW_VOLATILITY_TREND_UP"
            )
        else:
            regime = (
                "LOW_VOLATILITY_TREND_DOWN"
            )

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
        "regime":
            regime,

        "atr_ratio":
            round(
                atr_ratio,
                3
            ),

        "trend_strength":
            round(
                trend_strength,
                3
            ),

        "score":
            round(
                score,
                2
            )
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

    price = safe_float(
        row["close"]
    )

    ema20 = safe_float(
        row["ema20"]
    )

    ema50 = safe_float(
        row["ema50"]
    )

    levels = get_support_resistance(
        df,
        i
    )

    support = levels[
        "support"
    ]

    resistance = levels[
        "resistance"
    ]

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

        if (
            distance_support
            <= atr * 1.5
        ):

            zone = "NEAR_SUPPORT"
            score = 100.0

        elif (
            price > ema20 > ema50
        ):

            zone = "TREND_SUPPORT"
            score = 80.0

        elif (
            distance_resistance
            <= atr
        ):

            zone = "NEAR_RESISTANCE"
            score = 20.0

        else:

            zone = "NEUTRAL"
            score = 55.0

    elif direction == "SELL":

        if (
            distance_resistance
            <= atr * 1.5
        ):

            zone = "NEAR_RESISTANCE"
            score = 100.0

        elif (
            price < ema20 < ema50
        ):

            zone = "TREND_RESISTANCE"
            score = 80.0

        elif (
            distance_support <= atr
        ):

            zone = "NEAR_SUPPORT"
            score = 20.0

        else:

            zone = "NEUTRAL"
            score = 55.0

    return {
        "support":
            round_price(
                support
            ),

        "resistance":
            round_price(
                resistance
            ),

        "ema20":
            round_price(
                ema20
            ),

        "ema50":
            round_price(
                ema50
            ),

        "zone":
            zone,

        "zones":
            [zone],

        "score":
            round(
                score,
                2
            ),

        "valid":
            score >= 50
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
        "direction":
            (
                "BULLISH"
                if direction == "BUY"
                else "BEARISH"
            ),

        "rsi":
            round(
                rsi,
                1
            ),

        "score":
            round(
                score,
                2
            ),

        "strength":
            round(
                strength,
                1
            ),

        "valid":
            score >= 50,

        "reasons":
            reasons
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
        if safe_float(
            row["close"]
        )
        > safe_float(
            row["open"]
        )
        else "SELL"
    )

    score = 50.0

    reasons = []

    opposite = []

    for pattern in patterns:

        if (
            direction == "BUY"
            and pattern in BEARISH_PATTERNS
        ):

            opposite.append(
                pattern
            )

        elif (
            direction == "SELL"
            and pattern in BULLISH_PATTERNS
        ):

            opposite.append(
                pattern
            )

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

    if opposite:

        score -= 15

        reasons.append(
            "Opposite pattern detected"
        )

    else:

        reasons.append(
            "No opposite pattern"
        )

    score = clamp(
        score
    )

    quality = (
        "PASS"
        if score >= MIN_PATTERN_QUALITY
        else "FAIL"
    )

    return {
        "body_ratio":
            round(
                body_ratio,
                3
            ),

        "opposite":
            opposite,

        "quality":
            quality,

        "reasons":
            reasons,

        "relevant":
            patterns,

        "score":
            round(
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

        if (
            close
            >= high - atr * 0.20
        ):

            score += 25

        trigger = (
            high + atr * 0.05
        )

    else:

        if close < open_price:

            score += 25

        if (
            close
            <= low + atr * 0.20
        ):

            score += 25

        trigger = (
            low - atr * 0.05
        )

    if body_ratio < 0.30:

        reasons.append(
            "Weak trigger candle"
        )

    score = clamp(
        score
    )

    return {
        "body_ratio":
            round(
                body_ratio,
                3
            ),

        "signal_close":
            round_price(
                close
            ),

        "trigger":
            round_price(
                trigger
            ),

        "triggered":
            False,

        "valid":
            score >= MIN_TRIGGER_QUALITY,

        "score":
            round(
                score,
                2
            ),

        "reasons":
            reasons
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

    score = clamp(
        score
    )

    return {
        "direction":
            direction,

        "strength":
            round(
                score,
                2
            ),

        "bullish":
            [],

        "bearish":
            [],

        "conflict":
            False
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

    score = (

        directional[
            "strength"
        ] * 0.20

        + regime[
            "score"
        ] * 0.15

        + location[
            "score"
        ] * 0.15

        + momentum[
            "score"
        ] * 0.15

        + pattern_quality[
            "score"
        ] * 0.20

        + trigger_quality[
            "score"
        ] * 0.15
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
    atr = safe_float(row["atr"])

    checks = {
        "atr": atr >= MINIMUM_ATR,
        "direction": direction in ["BUY", "SELL"],
        "market_regime": regime["regime"] not in ["RANGE"],
        "location": location["valid"],
        "momentum": momentum["valid"],
        "pattern_quality": pattern_quality["score"] >= (
            SELL_MIN_PATTERN_QUALITY if direction == "SELL"
            else MIN_PATTERN_QUALITY
        ),
        "trigger": trigger_quality["score"] >= (
            SELL_MIN_TRIGGER_QUALITY if direction == "SELL"
            else MIN_TRIGGER_QUALITY
        ),
        "score": score >= (
            SELL_MIN_SCORE if direction == "SELL"
            else MIN_SCORE
        ),
    }

    failed = [key for key, value in checks.items() if not value]
    critical_pass = (
        checks["atr"]
        and checks["direction"]
        and checks["market_regime"]
    )
    score_pass = checks["score"]
    passed = critical_pass and score_pass

    return {
        "checks": checks,
        "failed": failed,
        "passed": passed,
        "critical_passed": critical_pass,
        "score_passed": score_pass,
        "side_policy": {
            "direction": direction,
            "minimum_score": SELL_MIN_SCORE if direction == "SELL" else MIN_SCORE,
            "minimum_pattern_quality": (
                SELL_MIN_PATTERN_QUALITY if direction == "SELL"
                else MIN_PATTERN_QUALITY
            ),
            "minimum_trigger_quality": (
                SELL_MIN_TRIGGER_QUALITY if direction == "SELL"
                else MIN_TRIGGER_QUALITY
            )
        }
    }



# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    df,
    i,
    direction,
    entry_price=None
):

    row = df.iloc[i]

    setup_close = safe_float(
        row["close"]
    )

    if entry_price is None:

        entry_price = setup_close

    entry_price = safe_float(
        entry_price
    )

    atr = max(
        safe_float(row["atr"]),
        MINIMUM_ATR
    )

    levels = get_support_resistance(
        df,
        i
    )

    support = levels[
        "support"
    ]

    resistance = levels[
        "resistance"
    ]

    if direction == "BUY":

        structure_sl = (
            support
            - atr * 0.20
        )

        atr_sl = (
            entry_price
            - atr * 1.50
        )

        raw_sl = min(
            structure_sl,
            atr_sl
        )

        risk = (
            entry_price
            - raw_sl
        )

        risk = max(
            risk,
            atr * MIN_STOP_ATR
        )

        risk = min(
            risk,
            atr * MAX_STOP_ATR
        )

        sl = (
            entry_price
            - risk
        )

        tp = (
            entry_price
            + risk * RISK_REWARD
        )

    else:

        structure_sl = (
            resistance
            + atr * 0.20
        )

        atr_sl = (
            entry_price
            + atr * 1.50
        )

        raw_sl = max(
            structure_sl,
            atr_sl
        )

        risk = (
            raw_sl
            - entry_price
        )

        risk = max(
            risk,
            atr * MIN_STOP_ATR
        )

        risk = min(
            risk,
            atr * MAX_STOP_ATR
        )

        sl = (
            entry_price
            + risk
        )

        tp = (
            entry_price
            - risk * RISK_REWARD
        )

    risk = abs(
        entry_price - sl
    )

    reward = abs(
        tp - entry_price
    )

    rr = (
        reward / risk
        if risk > 0
        else 0
    )

    return {

        "entry_reference":
            round_price(
                entry_price
            ),

        "setup_close":
            round_price(
                setup_close
            ),

        "sl":
            round_price(
                sl
            ),

        "tp":
            round_price(
                tp
            ),

        "risk":
            round_price(
                risk
            ),

        "reward":
            round_price(
                reward
            ),

        "risk_reward":
            round(
                rr,
                2
            ),

        "atr":
            round(
                atr,
                4
            )
    }


# ============================================================
# ANALYZE CANDLE
# ============================================================

def analyze_candle(
    df,
    i,
    include_trade_levels=True
):

    if i < 55:

        return {
            "valid":
                False,

            "signal":
                "NO_TRADE",

            "reason":
                "Not enough candles"
        }

    row = df.iloc[i]

    patterns = detect_patterns(
        df,
        i
    )

    pattern_direction = (
        get_pattern_direction(
            patterns
        )
    )

    direction = (
        pattern_direction[
            "direction"
        ]
    )

    if direction == "CONFLICT":

        return {
            "valid":
                False,

            "signal":
                "NO_TRADE",

            "status":
                "PATTERN_CONFLICT",

            "patterns":
                patterns,

            "setup_candle":
                str(
                    row["datetime"]
                )
        }

    if direction == "NONE":

        return {
            "valid":
                False,

            "signal":
                "NO_TRADE",

            "status":
                "NO_PATTERN",

            "patterns":
                [],

            "setup_candle":
                str(
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

        # ใช้ Setup Close เป็นเพียงราคาอ้างอิง
        # Backtest จะ recalculated จาก Next Candle Open
        trade_levels = (
            calculate_trade_levels(
                df,
                i,
                direction,
                entry_price=safe_float(
                    row["close"]
                )
            )
        )

        if (
            trade_levels[
                "risk_reward"
            ]
            < MIN_RISK_REWARD
        ):

            filter_result[
                "passed"
            ] = False

            if (
                "risk_reward"
                not in filter_result[
                    "failed"
                ]
            ):

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

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "timestamp":
            now_utc(),

        "setup_candle":
            str(
                row["datetime"]
            ),

        "patterns":
            patterns,

        "directional_filter": {
            **directional,

            "bullish":
                pattern_direction[
                    "bullish"
                ],

            "bearish":
                pattern_direction[
                    "bearish"
                ]
        },

        "market_regime":
            regime,

        "location":
            location,

        "momentum":
            momentum,

        "pattern_quality":
            pattern_quality,

        "trigger_quality":
            trigger_quality,

        "hard_filter":
            filter_result,

        "score":
            score,

        "confidence":
            confidence,

        # สำคัญ:
        # ไม่เรียกว่า Probability เชิงสถิติ
        "score_percent":
            score,

        "probability":
            None,

        "probability_note":
            "Score is not statistical probability. Historical probability is calculated from backtest statistics.",

        "trend":
            (
                "UPTREND"
                if safe_float(
                    row["ema20"]
                )
                >
                safe_float(
                    row["ema50"]
                )
                else "DOWNTREND"
            ),

        "ema20":
            round_price(
                row["ema20"]
            ),

        "ema50":
            round_price(
                row["ema50"]
            ),

        "rsi":
            round(
                safe_float(
                    row["rsi"]
                ),
                1
            ),

        "atr":
            round(
                safe_float(
                    row["atr"]
                ),
                4
            ),

        "support":
            location[
                "support"
            ],

        "resistance":
            location[
                "resistance"
            ],

        "entry_rule":
            "NEXT CANDLE OPEN",

        "next_candle_entry":
            (
                signal
                in [
                    "BUY",
                    "SELL"
                ]
            ),

        "signal":
            signal,

        "valid":
            (
                signal
                in [
                    "BUY",
                    "SELL"
                ]
            ),

        "status":
            (
                "READY"
                if signal
                in [
                    "BUY",
                    "SELL"
                ]
                else "HARD_FILTER_FAILED"
            ),

        "trade_levels":
            trade_levels
    }


# ============================================================
# SIMULATE TRADE
# ============================================================

def simulate_trade(
    df,
    signal_index,
    direction,
    setup_levels
):
    """Simulate a trade from the real next-candle execution price.

    Two paths are evaluated from the same OHLC sequence:
      1) the configured path (possibly using conservative break-even),
      2) a no-BE baseline.

    This makes BE impact visible instead of allowing it to silently improve
    historical results. When SL and TP are both touched in one candle, SL
    is assumed first because Twelve Data OHLC has no intrabar sequence.
    """
    entry_index = signal_index + 1
    if entry_index >= len(df):
        return None

    raw_entry = safe_float(df.iloc[entry_index]["open"])
    if direction == "BUY":
        entry = raw_entry + SPREAD / 2 + SLIPPAGE
    else:
        entry = raw_entry - SPREAD / 2 - SLIPPAGE

    # SL/TP are recalculated using the actual next-candle execution price.
    levels = calculate_trade_levels(
        df, signal_index, direction, entry_price=entry
    )
    original_sl = safe_float(levels["sl"])
    tp = safe_float(levels["tp"])
    risk = abs(entry - original_sl)
    if risk <= 0:
        return None

    end_index = min(len(df), entry_index + FORWARD_BARS + 1)

    def path(use_break_even):
        sl = original_sl
        result = "TIMEOUT"
        exit_price = entry
        exit_index = end_index - 1
        max_favorable = 0.0
        max_adverse = 0.0
        moved_to_be = False

        for j in range(entry_index, end_index):
            candle = df.iloc[j]
            high = safe_float(candle["high"])
            low = safe_float(candle["low"])

            if direction == "BUY":
                mfe = (high - entry) / risk
                mae = (low - entry) / risk
            else:
                mfe = (entry - low) / risk
                mae = (entry - high) / risk

            max_favorable = max(max_favorable, mfe)
            max_adverse = min(max_adverse, mae)

            # Conservative ordering: active SL is checked before TP.
            if direction == "BUY":
                if low <= sl:
                    exit_price = sl
                    exit_index = j
                    result = "BREAKEVEN" if moved_to_be else "LOSS"
                    break
                if high >= tp:
                    exit_price = tp
                    exit_index = j
                    result = "WIN"
                    break
            else:
                if high >= sl:
                    exit_price = sl
                    exit_index = j
                    result = "BREAKEVEN" if moved_to_be else "LOSS"
                    break
                if low <= tp:
                    exit_price = tp
                    exit_index = j
                    result = "WIN"
                    break

            # BE can only become active AFTER this candle has closed.
            if (
                use_break_even
                and BREAK_EVEN
                and not moved_to_be
                and mfe >= BREAK_EVEN_R
            ):
                sl = max(sl, entry) if direction == "BUY" else min(sl, entry)
                moved_to_be = True

        if result == "TIMEOUT":
            exit_index = max(entry_index, end_index - 1)
            exit_price = safe_float(df.iloc[exit_index]["close"])

        if direction == "BUY":
            r = (exit_price - entry) / risk
        else:
            r = (entry - exit_price) / risk

        if result == "BREAKEVEN":
            r = 0.0

        return {
            "result": result,
            "exit_price": exit_price,
            "exit_index": exit_index,
            "r": r,
            "mfe_r": max_favorable,
            "mae_r": max_adverse,
            "break_even_used": moved_to_be,
        }

    actual = path(BREAK_EVEN)
    baseline = path(False)

    return {
        "setup_index": signal_index,
        "entry_index": entry_index,
        "exit_index": actual["exit_index"],
        "setup_time": str(df.iloc[signal_index]["datetime"]),
        "entry_time": str(df.iloc[entry_index]["datetime"]),
        "exit_time": str(df.iloc[actual["exit_index"]]["datetime"]),
        "direction": direction,
        "entry_raw": round_price(raw_entry),
        "entry": round_price(entry),
        "sl": round_price(actual["result"] == "TIMEOUT" and original_sl or (
            entry if actual["result"] == "BREAKEVEN" else original_sl
        )),
        "original_sl": round_price(original_sl),
        "tp": round_price(tp),
        "exit": round_price(actual["exit_price"]),
        "result": actual["result"],
        "r": round(actual["r"], 4),
        "r_no_be": round(baseline["r"], 4),
        "result_no_be": baseline["result"],
        "be_delta_r": round(actual["r"] - baseline["r"], 4),
        "mae_r": round(actual["mae_r"], 4),
        "mfe_r": round(actual["mfe_r"], 4),
        "break_even_used": actual["break_even_used"],
        "timeout_mfe_ge_1r": (
            actual["result"] == "TIMEOUT" and actual["mfe_r"] >= 1.0
        ),
        "timeout_mfe_ge_tp": (
            actual["result"] == "TIMEOUT"
            and actual["mfe_r"] >= safe_float(levels["risk_reward"])
        ),
        "risk": round_price(risk),
        "reward": round_price(abs(tp - entry)),
        "risk_reward": round(safe_float(levels["risk_reward"]), 3),
    }



# ============================================================
# GENERIC PERFORMANCE
# ============================================================

def calculate_trade_statistics(trades):
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    breakevens = [t for t in trades if t["result"] == "BREAKEVEN"]
    timeouts = [t for t in trades if t["result"] == "TIMEOUT"]
    resolved = len(wins) + len(losses) + len(breakevens)

    total_r = sum(safe_float(t.get("r")) for t in trades)
    total_r_no_be = sum(safe_float(t.get("r_no_be", t.get("r", 0))) for t in trades)
    total_profit_r = sum(max(safe_float(t.get("r")), 0) for t in trades)
    total_loss_r = abs(sum(min(safe_float(t.get("r")), 0) for t in trades))
    total_profit_r_no_be = sum(max(safe_float(t.get("r_no_be", t.get("r", 0))), 0) for t in trades)
    total_loss_r_no_be = abs(sum(min(safe_float(t.get("r_no_be", t.get("r", 0))), 0) for t in trades))

    profit_factor = (
        total_profit_r / total_loss_r
        if total_loss_r > 0
        else (float("inf") if total_profit_r > 0 else 0)
    )
    profit_factor_no_be = (
        total_profit_r_no_be / total_loss_r_no_be
        if total_loss_r_no_be > 0
        else (float("inf") if total_profit_r_no_be > 0 else 0)
    )

    average_r = total_r / len(trades) if trades else 0
    average_r_no_be = total_r_no_be / len(trades) if trades else 0
    win_rate = len(wins) / resolved * 100 if resolved else 0
    loss_rate = len(losses) / len(trades) * 100 if trades else 0
    breakeven_rate = len(breakevens) / len(trades) * 100 if trades else 0
    timeout_rate = len(timeouts) / len(trades) * 100 if trades else 0

    average_mae = np.mean([safe_float(t.get("mae_r")) for t in trades]) if trades else 0
    average_mfe = np.mean([safe_float(t.get("mfe_r")) for t in trades]) if trades else 0
    average_score = np.mean([safe_float(t.get("score")) for t in trades]) if trades else 0

    timeout_mfe_1r = [t for t in timeouts if safe_float(t.get("mfe_r")) >= 1.0]
    timeout_mfe_tp = [t for t in timeouts if t.get("timeout_mfe_ge_tp")]
    be_used = [t for t in trades if t.get("break_even_used")]
    be_delta = sum(safe_float(t.get("be_delta_r")) for t in trades)

    longest_losing_streak = 0
    current_streak = 0
    for trade in trades:
        if trade["result"] == "LOSS":
            current_streak += 1
            longest_losing_streak = max(longest_losing_streak, current_streak)
        else:
            current_streak = 0

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += safe_float(trade.get("r"))
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    def pct(n, d):
        return round(n / d * 100, 2) if d else 0.0

    def finite_or_none(x):
        return round(x, 3) if math.isfinite(x) else None

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(breakevens),
        "timeouts": len(timeouts),
        "resolved": resolved,
        "total_profit_r": round(total_profit_r, 4),
        "total_loss_r": round(total_loss_r, 4),
        "net_profit_r": round(total_r, 4),
        "net_profit_r_no_be": round(total_r_no_be, 4),
        "be_delta_total_r": round(be_delta, 4),
        "average_r": round(average_r, 4),
        "average_r_no_be": round(average_r_no_be, 4),
        "expectancy_r": round(average_r, 4),
        "win_rate_percent": round(win_rate, 2),
        "loss_rate_percent": round(loss_rate, 2),
        "breakeven_rate_percent": round(breakeven_rate, 2),
        "timeout_rate_percent": round(timeout_rate, 2),
        "profit_factor": finite_or_none(profit_factor),
        "profit_factor_no_be": finite_or_none(profit_factor_no_be),
        "average_score": round(average_score, 2),
        "average_mae_r": round(average_mae, 4),
        "average_mfe_r": round(average_mfe, 4),
        "timeout_mfe_ge_1r": len(timeout_mfe_1r),
        "timeout_mfe_ge_1r_percent": pct(len(timeout_mfe_1r), len(timeouts)),
        "timeout_mfe_ge_tp": len(timeout_mfe_tp),
        "timeout_mfe_ge_tp_percent": pct(len(timeout_mfe_tp), len(timeouts)),
        "break_even_used_trades": len(be_used),
        "break_even_used_percent": pct(len(be_used), len(trades)),
        "longest_losing_streak": longest_losing_streak,
        "max_drawdown_r": round(max_drawdown, 4),
    }



# ============================================================
# GROUP PERFORMANCE
# ============================================================

def grouped_performance(
    trades,
    key_function
):

    groups = {}

    for trade in trades:

        key = key_function(
            trade
        )

        if not key:
            continue

        groups.setdefault(
            key,
            []
        ).append(
            trade
        )

    result = {}

    for key, group in groups.items():

        stats = calculate_trade_statistics(
            group
        )

        result[key] = {

            "trades":
                stats["trades"],

            "wins":
                stats["wins"],

            "losses":
                stats["losses"],

            "breakevens":
                stats["breakevens"],

            "timeouts":
                stats["timeouts"],

            "win_rate_percent":
                stats["win_rate_percent"],

            "average_r":
                stats["average_r"],

            "profit_factor":
                stats["profit_factor"],

            "net_profit_r":
                stats["net_profit_r"]
        }

    return result


# ============================================================
# BACKTEST
# ============================================================

def score_bucket(score):
    score = safe_float(score)
    if score < 70:
        return "<70"
    if score < 75:
        return "70-74"
    if score < 80:
        return "75-79"
    if score < 85:
        return "80-84"
    if score < 90:
        return "85-89"
    if score < 95:
        return "90-94"
    return "95-100"


def empirical_probability(trades, group_name="all"):
    resolved = [t for t in trades if t.get("result") in ["WIN", "LOSS", "BREAKEVEN"]]
    wins = [t for t in resolved if t.get("result") == "WIN"]
    n = len(resolved)
    p = len(wins) / n * 100 if n else None
    return {
        "group": group_name,
        "wins": len(wins),
        "resolved": n,
        "probability_percent": round(p, 2) if p is not None else None,
        "sample_size": n,
        "sample_sufficient": n >= MIN_HISTORICAL_SAMPLE,
        "minimum_sample_required": MIN_HISTORICAL_SAMPLE,
        "note": (
            "Empirical historical win rate among resolved trades. "
            "TIMEOUT trades are excluded from the numerator and denominator."
        )
    }


def run_backtest(df, test_points=200):
    df = df.copy()
    if len(df) <= 60:
        raise RuntimeError("Not enough candles for backtest")

    test_points = min(int(test_points), len(df) - 60)
    start = max(55, len(df) - test_points)
    trades = []
    pattern_frequency = {}
    regime_frequency = {}
    score_bucket_candidates = {
        "70-74": 0, "75-79": 0, "80-84": 0,
        "85-89": 0, "90-94": 0, "95-100": 0
    }
    pattern_candidates = 0
    score_passed = 0
    hard_filter_passed = 0
    skipped_overlapping = 0
    next_available_index = start

    for i in range(start, len(df) - 1):
        result = analyze_candle(df, i, include_trade_levels=True)
        patterns = result.get("patterns", [])
        for pattern in patterns:
            pattern_frequency[pattern] = pattern_frequency.get(pattern, 0) + 1

        regime = result.get("market_regime", {}).get("regime")
        if regime:
            regime_frequency[regime] = regime_frequency.get(regime, 0) + 1

        if not patterns:
            continue
        pattern_candidates += 1
        score = safe_float(result.get("score"))
        if score >= 70:
            score_passed += 1
            score_bucket_candidates[score_bucket(score)] += 1

        hard_pass = result.get("hard_filter", {}).get("passed", False)
        if not hard_pass:
            continue
        hard_filter_passed += 1
        direction = result.get("signal")
        levels = result.get("trade_levels")
        if direction not in ["BUY", "SELL"] or not levels:
            continue

        if not ALLOW_OVERLAPPING_TRADES and i < next_available_index:
            skipped_overlapping += 1
            continue

        trade = simulate_trade(df, i, direction, levels)
        if not trade:
            continue

        trade["score"] = score
        trade["score_bucket"] = score_bucket(score)
        trade["patterns"] = patterns
        trade["primary_pattern"] = patterns[0] if patterns else None
        trade["regime"] = regime
        trade["location_zone"] = result.get("location", {}).get("zone")
        trade["rsi"] = result.get("rsi")
        trade["atr"] = result.get("atr")
        trade["pattern_quality_score"] = result.get("pattern_quality", {}).get("score")
        trade["trigger_quality_score"] = result.get("trigger_quality", {}).get("score")
        trades.append(trade)

        if not ALLOW_OVERLAPPING_TRADES:
            next_available_index = trade["exit_index"] + 1

    stats = calculate_trade_statistics(trades)

    def group_stats(key):
        groups = {}
        for t in trades:
            value = key(t)
            if value:
                groups.setdefault(value, []).append(t)
        out = {}
        for value, group in groups.items():
            st = calculate_trade_statistics(group)
            out[value] = {
                "trades": st["trades"], "wins": st["wins"],
                "losses": st["losses"], "breakevens": st["breakevens"],
                "timeouts": st["timeouts"], "resolved": st["resolved"],
                "win_rate_percent": st["win_rate_percent"],
                "historical_probability": empirical_probability(group, str(value)),
                "average_r": st["average_r"],
                "net_profit_r": st["net_profit_r"],
                "profit_factor": st["profit_factor"],
                "timeout_mfe_ge_1r": st["timeout_mfe_ge_1r"],
                "timeout_mfe_ge_tp": st["timeout_mfe_ge_tp"],
            }
        return out

    score_performance = group_stats(lambda t: t.get("score_bucket"))
    direction_performance = group_stats(lambda t: t.get("direction"))
    regime_performance = group_stats(lambda t: t.get("regime"))
    pattern_performance = group_stats(lambda t: t.get("primary_pattern"))
    location_performance = group_stats(lambda t: t.get("location_zone"))

    # Pattern-level performance is also expanded to every detected pattern,
    # rather than only the first pattern, so the analysis does not silently
    # discard multi-pattern setups.
    pattern_all_performance = {}
    for pattern in pattern_frequency:
        group = [t for t in trades if pattern in t.get("patterns", [])]
        if group:
            st = calculate_trade_statistics(group)
            pattern_all_performance[pattern] = {
                "trades": st["trades"],
                "wins": st["wins"],
                "losses": st["losses"],
                "timeouts": st["timeouts"],
                "resolved": st["resolved"],
                "historical_probability": empirical_probability(group, pattern),
                "average_r": st["average_r"],
                "net_profit_r": st["net_profit_r"],
                "profit_factor": st["profit_factor"],
            }

    historical_probability = empirical_probability(trades, "all")

    return {
        "status": "completed",
        "system": "Quality Filtered Next Candle Entry Engine v3",
        "symbol": SYMBOL,
        "timeframe": "M5",
        "data_source": "Twelve Data XAU/USD",
        "candles_available": len(df),
        "test_points": test_points,
        "test_start": str(df.iloc[start]["datetime"]),
        "test_end": str(df.iloc[-2]["datetime"]),
        "pipeline_counts": {
            "pattern_candidates": pattern_candidates,
            "score_passed": score_passed,
            "hard_filter_passed": hard_filter_passed,
            "executed_trades": len(trades),
            "skipped_overlapping": skipped_overlapping,
        },
        "signals": {
            "buy": len([t for t in trades if t["direction"] == "BUY"]),
            "sell": len([t for t in trades if t["direction"] == "SELL"]),
            "total": len(trades),
        },
        "results": {
            "wins": stats["wins"], "losses": stats["losses"],
            "breakevens": stats["breakevens"], "timeouts": stats["timeouts"],
            "resolved": stats["resolved"],
        },
        "performance": {
            "net_profit_r": stats["net_profit_r"],
            "net_profit_r_no_be": stats["net_profit_r_no_be"],
            "be_delta_total_r": stats["be_delta_total_r"],
            "average_r": stats["average_r"],
            "average_r_no_be": stats["average_r_no_be"],
            "expectancy_r": stats["expectancy_r"],
            "win_rate_percent": stats["win_rate_percent"],
            "loss_rate_percent": stats["loss_rate_percent"],
            "breakeven_rate_percent": stats["breakeven_rate_percent"],
            "timeout_rate_percent": stats["timeout_rate_percent"],
            "profit_factor": stats["profit_factor"],
            "profit_factor_no_be": stats["profit_factor_no_be"],
            "average_score": stats["average_score"],
            "average_mae_r": stats["average_mae_r"],
            "average_mfe_r": stats["average_mfe_r"],
            "timeout_mfe_ge_1r": stats["timeout_mfe_ge_1r"],
            "timeout_mfe_ge_1r_percent": stats["timeout_mfe_ge_1r_percent"],
            "timeout_mfe_ge_tp": stats["timeout_mfe_ge_tp"],
            "timeout_mfe_ge_tp_percent": stats["timeout_mfe_ge_tp_percent"],
            "break_even_used_trades": stats["break_even_used_trades"],
            "break_even_used_percent": stats["break_even_used_percent"],
            "longest_losing_streak": stats["longest_losing_streak"],
            "max_drawdown_r": stats["max_drawdown_r"],
            "historical_probability": historical_probability,
        },
        "historical_probability": historical_probability,
        "direction_performance": direction_performance,
        "pattern_frequency": pattern_frequency,
        "pattern_performance": pattern_performance,
        "pattern_all_performance": pattern_all_performance,
        "regime_frequency": regime_frequency,
        "regime_performance": regime_performance,
        "location_performance": location_performance,
        "score_bucket_candidates": score_bucket_candidates,
        "score_performance": score_performance,
        "recent_trades": trades[-20:],
        "rules": {
            "entry": "NEXT CANDLE OPEN",
            "minimum_score": MIN_SCORE,
            "sell_minimum_score": SELL_MIN_SCORE,
            "minimum_pattern_quality": MIN_PATTERN_QUALITY,
            "sell_minimum_pattern_quality": SELL_MIN_PATTERN_QUALITY,
            "minimum_trigger_quality": MIN_TRIGGER_QUALITY,
            "sell_minimum_trigger_quality": SELL_MIN_TRIGGER_QUALITY,
            "minimum_risk_reward": MIN_RISK_REWARD,
            "risk_reward": RISK_REWARD,
            "minimum_atr": MINIMUM_ATR,
            "min_stop_atr": MIN_STOP_ATR,
            "max_stop_atr": MAX_STOP_ATR,
            "forward_bars": FORWARD_BARS,
            "spread": SPREAD,
            "slippage": SLIPPAGE,
            "break_even": BREAK_EVEN,
            "break_even_r": BREAK_EVEN_R,
            "historical_minimum_sample": MIN_HISTORICAL_SAMPLE,
            "allow_overlapping_trades": ALLOW_OVERLAPPING_TRADES,
        },
        "warning": (
            "Historical simulation only. Twelve Data OHLC candles do not contain "
            "intrabar tick sequence. When SL and TP are both touched inside the "
            "same candle, SL is assumed first. Entry is the NEXT CANDLE OPEN and "
            "SL/TP are recalculated from the actual next-candle execution price. "
            "Score is a model score, not a statistical probability. Historical "
            "probability is an empirical win rate among resolved trades; TIMEOUT "
            "trades are excluded from that probability. Break-even is activated "
            "only after a candle closes with MFE >= BREAK_EVEN_R, and no-BE results "
            "are reported alongside configured results to expose BE impact."
        ),
    }



# ============================================================
# ROUTE: HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "status":
            "online",

        "version":
            "3.0",

        "service":
            "XAU/USD M5 Quality Filtered Next Candle Entry Engine",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

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

            "REAL ENTRY PRICE",

            "ATR SL/TP",

            "Conservative Intrabar Simulation",

            "Historical Probability",
            "BE vs No-BE Audit",
            "Regime / Pattern / Score Performance"
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

        "status":
            "healthy",

        "service":
            "XAU/USD Signal Engine v3",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "twelve_data":
            bool(
                TWELVE_DATA_API_KEY
            ),

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

        raw_latest = df.iloc[
            -1
        ]

        closed_df = (
            remove_incomplete_last_candle(
                df
            )
        )

        if closed_df.empty:

            raise RuntimeError(
                "No closed candle available"
            )

        latest = closed_df.iloc[
            -1
        ]

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
                len(df),

            "closed_candles":
                len(closed_df),

            "latest_raw":
                {
                    "datetime":
                        str(
                            raw_latest[
                                "datetime"
                            ]
                        ),

                    "open":
                        round_price(
                            raw_latest[
                                "open"
                            ]
                        ),

                    "high":
                        round_price(
                            raw_latest[
                                "high"
                            ]
                        ),

                    "low":
                        round_price(
                            raw_latest[
                                "low"
                            ]
                        ),

                    "close":
                        round_price(
                            raw_latest[
                                "close"
                            ]
                        )
                },

            "latest_closed":
                {

                    "datetime":
                        str(
                            latest[
                                "datetime"
                            ]
                        ),

                    "open":
                        round_price(
                            latest[
                                "open"
                            ]
                        ),

                    "high":
                        round_price(
                            latest[
                                "high"
                            ]
                        ),

                    "low":
                        round_price(
                            latest[
                                "low"
                            ]
                        ),

                    "close":
                        round_price(
                            latest[
                                "close"
                            ]
                        )
                }
        })

    except Exception as e:

        return jsonify({

            "status":
                "error",

            "message":
                str(e),

            "trace":
                traceback.format_exc()

        }), 500


# ============================================================
# ROUTE: SIGNAL
# ============================================================

@app.route("/signal")
@app.route("/signal")
def signal():
    try:
        df = get_market_data(1000)
        df = remove_incomplete_last_candle(df)
        if len(df) < 100:
            raise RuntimeError("Not enough closed candles")

        df = calculate_indicators(df)
        index = len(df) - 1
        result = analyze_candle(df, index)

        # Score and historical probability are deliberately separate.
        if SIGNAL_HISTORY_POINTS > 0:
            try:
                history_result = run_backtest(df, min(SIGNAL_HISTORY_POINTS, len(df) - 60))
                result["historical_probability"] = history_result.get("historical_probability")
                result["historical_context"] = {
                    "overall": history_result.get("historical_probability"),
                    "direction": history_result.get("direction_performance", {}).get(result.get("signal")),
                    "regime": history_result.get("regime_performance", {}).get(
                        result.get("market_regime", {}).get("regime")
                    ),
                    "score_bucket": history_result.get("score_performance", {}).get(
                        score_bucket(result.get("score"))
                    ),
                    "primary_pattern": history_result.get("pattern_performance", {}).get(
                        (result.get("patterns") or [None])[0]
                    ),
                    "minimum_sample_required": MIN_HISTORICAL_SAMPLE,
                }
            except Exception as history_error:
                result["historical_probability"] = None
                result["historical_context_error"] = str(history_error)
        else:
            result["historical_probability"] = None

        if result.get("valid"):
            direction = result["signal"]
            levels = result["trade_levels"]
            hp = result.get("historical_probability") or {}
            hp_text = (
                f"{hp.get('probability_percent')}% (n={hp.get('resolved')})"
                if hp.get("probability_percent") is not None
                else "Not enough historical sample"
            )
            telegram_message = f"""
<b>🚨 XAU/USD SIGNAL</b>

<b>Direction:</b> {direction}
<b>Timeframe:</b> M5
<b>Score:</b> {result['score']}
<b>Historical Probability:</b> {hp_text}
<b>Entry:</b> NEXT CANDLE OPEN
<b>Projected SL:</b> {levels['sl']}
<b>Projected TP:</b> {levels['tp']}
<b>RR:</b> {levels['risk_reward']}
<b>RSI:</b> {result['rsi']}
<b>ATR:</b> {result['atr']}
<b>Pattern:</b> {", ".join(result['patterns'])}
<b>Setup:</b> {result['setup_candle']}
"""
            result["telegram"] = send_telegram(telegram_message)
        else:
            result["telegram"] = {
                "success": False,
                "message": "No trade - Telegram not sent"
            }

        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "trace": traceback.format_exc()
        }), 500



# ============================================================
# BACKTEST INTERNAL
# ============================================================

def backtest_endpoint(
    points
):

    try:

        outputsize = max(
            points + 150,
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

            "status":
                "error",

            "message":
                str(e),

            "trace":
                traceback.format_exc()

        }), 500


# ============================================================
# BACKTEST ROUTES
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
# TELEGRAM TEST
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    result = send_telegram(
        """
<b>✅ XAU/USD ENGINE v3</b>

Telegram test message sent successfully.

System:
Quality Filtered Next Candle Entry Engine

Symbol:
XAU/USD

Timeframe:
M5

Entry:
NEXT CANDLE OPEN
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
# STARTUP MESSAGE
# ============================================================

def startup_message():

    message = f"""
<b>🟢 XAU/USD ENGINE v3 STARTED</b>

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

<b>Overlap:</b>
{"ON" if ALLOW_OVERLAPPING_TRADES else "OFF"}

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

    print(
        "XAU/USD QUALITY FILTERED "
        "NEXT CANDLE ENTRY ENGINE v3"
    )

    print("=" * 70)

    print(
        f"Symbol       : {SYMBOL}"
    )

    print(
        "Timeframe    : M5"
    )

    print(
        f"Min Score    : {MIN_SCORE}"
    )

    print(
        f"Min RR       : {MIN_RISK_REWARD}"
    )

    print(
        f"ATR          : "
        f"{MIN_STOP_ATR} - "
        f"{MAX_STOP_ATR}"
    )

    print(
        f"Break Even   : "
        f"{BREAK_EVEN}"
    )

    print(
        f"Overlap      : "
        f"{ALLOW_OVERLAPPING_TRADES}"
    )

    print(
        "Entry        : NEXT CANDLE OPEN"
    )

    print(
        "SL/TP        : BASED ON ACTUAL ENTRY"
    )

    print(
        "Probability  : HISTORICAL BACKTEST"
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
    # Telegram startup
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

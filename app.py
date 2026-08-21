import os
import math
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


# ============================================================
# ENTRY / TRIGGER RULES
# ============================================================

MINIMUM_ATR = 0.5

MINIMUM_SCORE = 70.0

MINIMUM_RISK_REWARD = 1.3

ATR_SL_MULTIPLIER = 1.0

RISK_REWARD = 1.5

FORWARD_BARS = 12


# ============================================================
# TECHNICAL PARAMETERS
# ============================================================

EMA_FAST = 20

EMA_SLOW = 50

RSI_PERIOD = 14

ATR_PERIOD = 14

BREAKOUT_LOOKBACK = 20

SUPPORT_RESISTANCE_LOOKBACK = 50


# ============================================================
# TRIGGER PARAMETERS
# ============================================================

TRIGGER_LOOKBACK = 3

BREAKOUT_BUFFER_ATR = 0.10

PULLBACK_DISTANCE_ATR = 0.35


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

    return datetime.now(
        timezone.utc
    )


# ============================================================
# NUMBER HELPERS
# ============================================================

def round_price(value):

    if value is None:
        return None

    return round(
        float(value),
        2
    )


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

        "symbol":
            SYMBOL,

        "interval":
            TIMEFRAME,

        "outputsize":
            CANDLE_LIMIT,

        "apikey":
            TWELVE_DATA_API_KEY,

        "format":
            "JSON",

        "timezone":
            "UTC"
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
        EMA_SLOW + 10,
        100
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

        return []

    multiplier = (
        2.0
        / (
            period
            + 1.0
        )
    )

    ema = []

    initial = (
        sum(
            values[:period]
        )
        / period
    )

    ema.append(initial)

    previous = initial

    for value in values[period:]:

        current = (
            (
                value
                - previous
            )
            * multiplier
            + previous
        )

        ema.append(
            current
        )

        previous = current

    padding = (
        [None]
        * (
            period
            - 1
        )
    )

    return (
        padding
        + ema
    )


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

            gains.append(
                change
            )

            losses.append(
                0.0
            )

        else:

            gains.append(
                0.0
            )

            losses.append(
                abs(change)
            )

    recent_gains = gains[
        -period:
    ]

    recent_losses = losses[
        -period:
    ]

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
            / (
                1.0
                + rs
            )
        )
    )

    return rsi


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

        previous_close = previous[
            "close"
        ]

        tr1 = (
            high
            - low
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
# PATTERN DETECTION
# ============================================================

def detect_patterns(candles):

    patterns = []

    if len(candles) < 5:

        return patterns

    c1 = candles[-1]

    c2 = candles[-2]

    c3 = candles[-3]

    c4 = candles[-4]

    c5 = candles[-5]

    # --------------------------------------------------------
    # Bullish Engulfing
    # --------------------------------------------------------

    if (
        bearish(c2)
        and bullish(c1)
        and c1["open"] <= c2["close"]
        and c1["close"] >= c2["open"]
    ):

        patterns.append(
            "Bullish Engulfing"
        )

    # --------------------------------------------------------
    # Bearish Engulfing
    # --------------------------------------------------------

    if (
        bullish(c2)
        and bearish(c1)
        and c1["open"] >= c2["close"]
        and c1["close"] <= c2["open"]
    ):

        patterns.append(
            "Bearish Engulfing"
        )

    # --------------------------------------------------------
    # Hammer
    # --------------------------------------------------------

    r1 = candle_range(c1)

    b1 = candle_body(c1)

    if r1 > 0:

        if (
            lower_wick(c1)
            >= b1 * 2.0
            and upper_wick(c1)
            <= r1 * 0.30
            and b1
            <= r1 * 0.40
        ):

            patterns.append(
                "Hammer"
            )

    # --------------------------------------------------------
    # Shooting Star
    # --------------------------------------------------------

    if r1 > 0:

        if (
            upper_wick(c1)
            >= b1 * 2.0
            and lower_wick(c1)
            <= r1 * 0.30
            and b1
            <= r1 * 0.40
        ):

            patterns.append(
                "Shooting Star"
            )

    # --------------------------------------------------------
    # Morning Star
    # --------------------------------------------------------

    r2 = candle_range(c2)

    r3 = candle_range(c3)

    if (
        bearish(c3)
        and bullish(c1)
        and r2 > 0
        and r3 > 0
        and c1["close"]
        > (
            c3["open"]
            + c3["close"]
        ) / 2
    ):

        patterns.append(
            "Morning Star"
        )

    # --------------------------------------------------------
    # Evening Star
    # --------------------------------------------------------

    if (
        bullish(c3)
        and bearish(c1)
        and r2 > 0
        and r3 > 0
        and c1["close"]
        < (
            c3["open"]
            + c3["close"]
        ) / 2
    ):

        patterns.append(
            "Evening Star"
        )

    # --------------------------------------------------------
    # Breakout
    # --------------------------------------------------------

    if len(candles) >= BREAKOUT_LOOKBACK + 2:

        previous = candles[
            -BREAKOUT_LOOKBACK - 1:-1
        ]

        previous_high = max(
            c["high"]
            for c in previous
        )

        previous_low = min(
            c["low"]
            for c in previous
        )

        if (
            c1["close"]
            > previous_high
        ):

            patterns.append(
                "Bullish Breakout"
            )

        if (
            c1["close"]
            < previous_low
        ):

            patterns.append(
                "Bearish Breakout"
            )

    # --------------------------------------------------------
    # Pullback
    # --------------------------------------------------------

    if len(candles) >= 25:

        closes = [
            c["close"]
            for c in candles
        ]

        ema20_values = calculate_ema(
            closes,
            EMA_FAST
        )

        ema20 = ema20_values[-1]

        if ema20 is not None:

            distance = abs(
                c1["close"]
                - ema20
            )

            atr = calculate_atr(
                candles
            )

            if atr > 0:

                if (
                    distance
                    <= atr
                    * 1.0
                ):

                    recent_direction = (
                        closes[-1]
                        > closes[-6]
                    )

                    if recent_direction:

                        patterns.append(
                            "Pullback"
                        )

    # --------------------------------------------------------
    # Double Bottom
    # --------------------------------------------------------

    if len(candles) >= 20:

        lows = [
            c["low"]
            for c in candles[
                -20:
            ]
        ]

        low1 = min(
            lows[:10]
        )

        low2 = min(
            lows[10:]
        )

        tolerance = (
            abs(low1)
            * 0.0015
        )

        if (
            abs(
                low1
                - low2
            )
            <= tolerance
        ):

            patterns.append(
                "Double Bottom"
            )

    # --------------------------------------------------------
    # Double Top
    # --------------------------------------------------------

    if len(candles) >= 20:

        highs = [
            c["high"]
            for c in candles[
                -20:
            ]
        ]

        high1 = max(
            highs[:10]
        )

        high2 = max(
            highs[10:]
        )

        tolerance = (
            abs(high1)
            * 0.0015
        )

        if (
            abs(
                high1
                - high2
            )
            <= tolerance
        ):

            patterns.append(
                "Double Top"
            )

    return patterns


# ============================================================
# DIRECTIONAL PATTERNS
# ============================================================

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
}


def directional_patterns(
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

    if (
        len(bullish)
        > len(bearish)
    ):

        return (
            "BUY",
            bullish
        )

    if (
        len(bearish)
        > len(bullish)
    ):

        return (
            "SELL",
            bearish
        )

    return (
        None,
        []
    )


# ============================================================
# TREND
# ============================================================

def calculate_trend(
    candles
):

    closes = [
        c["close"]
        for c in candles
    ]

    ema20_values = calculate_ema(
        closes,
        EMA_FAST
    )

    ema50_values = calculate_ema(
        closes,
        EMA_SLOW
    )

    ema20 = ema20_values[-1]

    ema50 = ema50_values[-1]

    close = closes[-1]

    if (
        ema20 is None
        or ema50 is None
    ):

        return (
            "UNKNOWN",
            ema20,
            ema50
        )

    if (
        close > ema20
        and ema20 > ema50
    ):

        return (
            "UPTREND",
            ema20,
            ema50
        )

    if (
        close < ema20
        and ema20 < ema50
    ):

        return (
            "DOWNTREND",
            ema20,
            ema50
        )

    return (
        "SIDEWAYS",
        ema20,
        ema50
    )


# ============================================================
# MOMENTUM
# ============================================================

def calculate_momentum(
    candles
):

    if len(candles) < 5:

        return "NEUTRAL"

    recent = candles[-3:]

    bullish_count = 0

    bearish_count = 0

    for candle in recent:

        if bullish(candle):

            bullish_count += 1

        elif bearish(candle):

            bearish_count += 1

    if bullish_count > bearish_count:

        return "BULLISH"

    if bearish_count > bullish_count:

        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_support_resistance(
    candles
):

    lookback = min(
        SUPPORT_RESISTANCE_LOOKBACK,
        len(candles)
    )

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

    return (
        support,
        resistance
    )


# ============================================================
# CONFIRMATION
# ============================================================

def confirmation_engine(
    candles,
    direction,
    patterns,
    trend,
    momentum,
    rsi,
    atr,
    support,
    resistance
):

    if direction not in [
        "BUY",
        "SELL"
    ]:

        return {

            "valid":
                False,

            "score":
                0.0,

            "checks": {},

            "reasons": [
                "No directional pattern"
            ]
        }

    latest = candles[-1]

    previous = candles[-2]

    score = 0.0

    reasons = []

    checks = {

        "pattern":
            False,

        "trend":
            False,

        "momentum":
            False,

        "rsi":
            False,

        "location":
            False,

        "volatility":
            False,

        "trigger":
            False
    }

    # --------------------------------------------------------
    # Pattern
    # --------------------------------------------------------

    directional = [
        p
        for p in patterns
        if (
            (
                direction == "BUY"
                and p in BULLISH_PATTERNS
            )
            or
            (
                direction == "SELL"
                and p in BEARISH_PATTERNS
            )
        )
    ]

    if directional:

        checks[
            "pattern"
        ] = True

        score += 25.0

        reasons.append(
            f"{len(directional)} pattern(s) detected"
        )

    # --------------------------------------------------------
    # Trend
    # --------------------------------------------------------

    trend_ok = (

        (
            direction == "BUY"
            and trend == "UPTREND"
        )

        or

        (
            direction == "SELL"
            and trend == "DOWNTREND"
        )
    )

    if trend_ok:

        checks[
            "trend"
        ] = True

        score += 20.0

        reasons.append(
            "Aligned with trend"
        )

    else:

        reasons.append(
            "Against trend"
        )

    # --------------------------------------------------------
    # Momentum
    # --------------------------------------------------------

    momentum_ok = (

        (
            direction == "BUY"
            and momentum == "BULLISH"
        )

        or

        (
            direction == "SELL"
            and momentum == "BEARISH"
        )
    )

    if momentum_ok:

        checks[
            "momentum"
        ] = True

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

    rsi_ok = (

        (
            direction == "BUY"
            and 50.0 <= rsi <= 72.0
        )

        or

        (
            direction == "SELL"
            and 28.0 <= rsi <= 50.0
        )
    )

    if rsi_ok:

        checks[
            "rsi"
        ] = True

        score += 10.0

        reasons.append(
            "RSI supports direction"
        )

    else:

        reasons.append(
            "RSI does not confirm direction"
        )

    # --------------------------------------------------------
    # Location
    # --------------------------------------------------------

    current = latest["close"]

    location_ok = False

    if direction == "BUY":

        if (
            current <= resistance
            and current >= support
        ):

            location_ok = True

    else:

        if (
            current >= support
            and current <= resistance
        ):

            location_ok = True

    if location_ok:

        checks[
            "location"
        ] = True

        score += 10.0

        reasons.append(
            "Price in tradable zone"
        )

    # --------------------------------------------------------
    # Volatility
    # --------------------------------------------------------

    if atr >= MINIMUM_ATR:

        checks[
            "volatility"
        ] = True

        score += 10.0

        reasons.append(
            "ATR sufficient"
        )

    else:

        reasons.append(
            "ATR too low"
        )

    # --------------------------------------------------------
    # Trigger
    # --------------------------------------------------------

    trigger = check_entry_trigger(
        candles,
        direction,
        atr
    )

    if trigger["triggered"]:

        checks[
            "trigger"
        ] = True

        score += 10.0

        reasons.append(
            "Entry trigger confirmed"
        )

    else:

        reasons.append(
            trigger["reason"]
        )

    valid = (
        score >= MINIMUM_SCORE
        and checks["pattern"]
        and checks["trend"]
        and checks["rsi"]
        and checks["volatility"]
        and checks["trigger"]
    )

    return {

        "valid":
            valid,

        "score":
            round(
                score,
                2
            ),

        "checks":
            checks,

        "reasons":
            reasons,

        "trigger":
            trigger
    }


# ============================================================
# ENTRY TRIGGER
# ============================================================

def check_entry_trigger(
    candles,
    direction,
    atr
):

    if len(candles) < 5:

        return {

            "triggered":
                False,

            "reason":
                "Not enough candles"
        }

    latest = candles[-1]

    previous = candles[-2]

    previous2 = candles[-3]

    close = latest["close"]

    previous_high = previous["high"]

    previous_low = previous["low"]

    buffer = (
        atr
        * BREAKOUT_BUFFER_ATR
    )

    # --------------------------------------------------------
    # BUY TRIGGERS
    # --------------------------------------------------------

    if direction == "BUY":

        breakout_trigger = (
            close
            > previous_high
            + buffer
        )

        bullish_trigger = (
            bullish(latest)
            and close
            > previous["close"]
            and close
            > previous2["close"]
        )

        reclaim_trigger = (
            bullish(latest)
            and close
            > previous["high"]
        )

        if (
            breakout_trigger
            or bullish_trigger
            or reclaim_trigger
        ):

            trigger_type = []

            if breakout_trigger:

                trigger_type.append(
                    "BREAKOUT"
                )

            if bullish_trigger:

                trigger_type.append(
                    "MOMENTUM"
                )

            if reclaim_trigger:

                trigger_type.append(
                    "RECLAIM"
                )

            return {

                "triggered":
                    True,

                "type":
                    "+".join(
                        trigger_type
                    ),

                "price":
                    close,

                "reason":
                    "BUY trigger confirmed"
            }

        return {

            "triggered":
                False,

            "type":
                None,

            "price":
                None,

            "reason":
                "Waiting for BUY trigger"
        }

    # --------------------------------------------------------
    # SELL TRIGGERS
    # --------------------------------------------------------

    if direction == "SELL":

        breakout_trigger = (
            close
            < previous_low
            - buffer
        )

        bearish_trigger = (
            bearish(latest)
            and close
            < previous["close"]
            and close
            < previous2["close"]
        )

        rejection_trigger = (
            bearish(latest)
            and close
            < previous["low"]
        )

        if (
            breakout_trigger
            or bearish_trigger
            or rejection_trigger
        ):

            trigger_type = []

            if breakout_trigger:

                trigger_type.append(
                    "BREAKDOWN"
                )

            if bearish_trigger:

                trigger_type.append(
                    "MOMENTUM"
                )

            if rejection_trigger:

                trigger_type.append(
                    "REJECTION"
                )

            return {

                "triggered":
                    True,

                "type":
                    "+".join(
                        trigger_type
                    ),

                "price":
                    close,

                "reason":
                    "SELL trigger confirmed"
            }

        return {

            "triggered":
                False,

            "type":
                None,

            "price":
                None,

            "reason":
                "Waiting for SELL trigger"
        }

    return {

        "triggered":
            False,

        "reason":
            "No direction"
    }


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    direction,
    entry,
    atr
):

    if atr <= 0:

        return (
            None,
            None,
            0.0
        )

    sl_distance = (
        atr
        * ATR_SL_MULTIPLIER
    )

    tp_distance = (
        sl_distance
        * RISK_REWARD
    )

    if direction == "BUY":

        stop_loss = (
            entry
            - sl_distance
        )

        take_profit = (
            entry
            + tp_distance
        )

    elif direction == "SELL":

        stop_loss = (
            entry
            + sl_distance
        )

        take_profit = (
            entry
            - tp_distance
        )

    else:

        return (
            None,
            None,
            0.0
        )

    actual_risk = abs(
        entry
        - stop_loss
    )

    actual_reward = abs(
        take_profit
        - entry
    )

    if actual_risk <= 0:

        risk_reward = 0.0

    else:

        risk_reward = (
            actual_reward
            / actual_risk
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
# MAIN ANALYSIS ENGINE
# ============================================================

def analyze_market(
    candles
):

    latest = candles[-1]

    close = latest["close"]

    atr = calculate_atr(
        candles,
        ATR_PERIOD
    )

    rsi = calculate_rsi(
        candles,
        RSI_PERIOD
    )

    trend, ema20, ema50 = (
        calculate_trend(
            candles
        )
    )

    momentum = calculate_momentum(
        candles
    )

    support, resistance = (
        calculate_support_resistance(
            candles
        )
    )

    patterns = detect_patterns(
        candles
    )

    direction, directional = (
        directional_patterns(
            patterns
        )
    )

    if direction is None:

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

            "patterns":
                patterns,

            "directional_patterns":
                directional,

            "candidate_direction":
                None,

            "entry":
                None,

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                0.0,

            "score":
                0.0,

            "confidence":
                0.0,

            "atr":
                round(
                    atr,
                    4
                ),

            "rsi":
                round(
                    rsi,
                    2
                ),

            "ema20":
                round_price(
                    ema20
                ),

            "ema50":
                round_price(
                    ema50
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

            "confirmation":
                {

                    "valid":
                        False,

                    "score":
                        0.0,

                    "checks":
                        {},

                    "reasons":
                        [
                            "No directional pattern"
                        ]
                },

            "method":
                "Pattern → Confirmation → Trigger → Entry → TP/SL",

            "data_source":
                "Twelve Data XAU/USD"
        }

    confirmation = confirmation_engine(

        candles,

        direction,

        patterns,

        trend,

        momentum,

        rsi,

        atr,

        support,

        resistance
    )

    score = confirmation[
        "score"
    ]

    trigger = confirmation.get(
        "trigger",
        {}
    )

    # --------------------------------------------------------
    # ENTRY ONLY AFTER CONFIRMATION + TRIGGER
    # --------------------------------------------------------

    if not confirmation["valid"]:

        if (
            score >= MINIMUM_SCORE
            and not trigger.get(
                "triggered",
                False
            )
        ):

            signal = (
                "WAIT_TRIGGER"
            )

            status = (
                "WAITING_FOR_TRIGGER"
            )

        else:

            signal = (
                "WAIT_CONFIRMATION"
            )

            status = (
                "PATTERN_DETECTED"
            )

        return {

            "timestamp":
                latest["datetime"],

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "signal":
                signal,

            "status":
                status,

            "valid":
                False,

            "patterns":
                patterns,

            "directional_patterns":
                directional,

            "candidate_direction":
                direction,

            "entry":
                None,

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                0.0,

            "score":
                score,

            "confidence":
                score,

            "atr":
                round(
                    atr,
                    4
                ),

            "rsi":
                round(
                    rsi,
                    2
                ),

            "ema20":
                round_price(
                    ema20
                ),

            "ema50":
                round_price(
                    ema50
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

            "reasons":
                confirmation[
                    "reasons"
                ],

            "confirmation":
                confirmation,

            "method":
                "Pattern → Confirmation → Trigger → Entry → TP/SL",

            "data_source":
                "Twelve Data XAU/USD"
        }

    # --------------------------------------------------------
    # REAL ENTRY
    # --------------------------------------------------------

    entry = (
        trigger.get(
            "price"
        )
    )

    if entry is None:

        entry = close

    stop_loss, take_profit, risk_reward = (
        calculate_trade_levels(
            direction,
            entry,
            atr
        )
    )

    if (
        stop_loss is None
        or take_profit is None
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
                "INVALID_LEVELS",

            "valid":
                False,

            "patterns":
                patterns,

            "directional_patterns":
                directional,

            "candidate_direction":
                direction,

            "entry":
                None,

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                risk_reward,

            "score":
                score,

            "confidence":
                score,

            "atr":
                round(
                    atr,
                    4
                ),

            "rsi":
                round(
                    rsi,
                    2
                ),

            "ema20":
                round_price(
                    ema20
                ),

            "ema50":
                round_price(
                    ema50
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

            "reasons":
                confirmation[
                    "reasons"
                ],

            "confirmation":
                confirmation,

            "method":
                "Pattern → Confirmation → Trigger → Entry → TP/SL",

            "data_source":
                "Twelve Data XAU/USD"
        }

    if risk_reward < MINIMUM_RISK_REWARD:

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
                directional,

            "candidate_direction":
                direction,

            "entry":
                round_price(
                    entry
                ),

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                risk_reward,

            "score":
                score,

            "confidence":
                score,

            "atr":
                round(
                    atr,
                    4
                ),

            "rsi":
                round(
                    rsi,
                    2
                ),

            "ema20":
                round_price(
                    ema20
                ),

            "ema50":
                round_price(
                    ema50
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

            "reasons":
                confirmation[
                    "reasons"
                ],

            "confirmation":
                confirmation,

            "method":
                "Pattern → Confirmation → Trigger → Entry → TP/SL",

            "data_source":
                "Twelve Data XAU/USD"
        }

    # --------------------------------------------------------
    # VALID TRADE
    # --------------------------------------------------------

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
            "ENTRY_CONFIRMED",

        "valid":
            True,

        "patterns":
            patterns,

        "directional_patterns":
            directional,

        "candidate_direction":
            direction,

        "entry":
            round_price(
                entry
            ),

        "stop_loss":
            stop_loss,

        "take_profit":
            take_profit,

        "risk_reward":
            risk_reward,

        "score":
            score,

        "confidence":
            score,

        "atr":
            round(
                atr,
                4
            ),

        "rsi":
            round(
                rsi,
                2
            ),

        "ema20":
            round_price(
                ema20
            ),

        "ema50":
            round_price(
                ema50
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

        "trigger":
            trigger,

        "reasons":
            confirmation[
                "reasons"
            ],

        "confirmation":
            confirmation,

        "method":
            "Pattern → Confirmation → Trigger → Entry → TP/SL",

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
# TELEGRAM STARTUP
# ============================================================

def send_startup_notification():

    if STATE[
        "startup_sent"
    ]:

        return True

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram startup skipped: "
            "TELEGRAM_BOT_TOKEN missing"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "Telegram startup skipped: "
            "TELEGRAM_CHAT_ID missing"
        )

        return False

    message = (

        "🟢 <b>XAUUSD M5 BOT ONLINE</b>\n"
        "\n"

        "ระบบเริ่มทำงานเรียบร้อยแล้ว ✅\n"
        "\n"

        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"
        "<b>Data:</b> Twelve Data\n"
        "\n"

        "<b>ระบบวิเคราะห์:</b>\n"
        "Pattern Recognition\n"
        "→ Confirmation\n"
        "→ Trigger\n"
        "→ Entry\n"
        "→ TP/SL\n"
        "\n"

        "<b>Pattern:</b> ENABLED\n"
        "<b>Confirmation:</b> ENABLED\n"
        "<b>Trigger:</b> ENABLED\n"
        "<b>Entry:</b> ENABLED\n"
        "<b>TP/SL:</b> ENABLED\n"
        "<b>Backtest:</b> ENABLED\n"
        "\n"

        "🟢 BUY พร้อมตรวจสอบ\n"
        "🔴 SELL พร้อมตรวจสอบ\n"
        "\n"

        "📡 <b>Telegram Signal:</b> ENABLED\n"
        "\n"

        "ระบบจะไม่ส่งออเดอร์จนกว่า\n"
        "<b>Pattern + Confirmation + Trigger</b>\n"
        "จะผ่านเงื่อนไขครบ"
    )

    ok, error = send_telegram(
        message
    )

    if ok:

        STATE[
            "startup_sent"
        ] = True

        print(
            "Telegram startup notification "
            "sent successfully"
        )

        return True

    print(
        "Telegram startup notification failed:",
        error
    )

    return False


# ============================================================
# TELEGRAM SIGNAL
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

    emoji = (
        "🟢"
        if direction == "BUY"
        else "🔴"
    )

    patterns = signal.get(
        "patterns",
        []
    )

    pattern_text = (
        ", ".join(patterns)
        if patterns
        else "-"
    )

    trigger = signal.get(
        "trigger",
        {}
    )

    trigger_type = trigger.get(
        "type",
        "-"
    )

    return (

        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        "\n"

        f"<b>SIGNAL:</b> {direction}\n"
        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"
        f"<b>Confidence:</b> "
        f"{signal['confidence']:.2f}%\n"
        "\n"

        f"<b>Pattern:</b>\n"
        f"{pattern_text}\n"
        "\n"

        f"<b>Trigger:</b> "
        f"{trigger_type}\n"
        "\n"

        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"

        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"

        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"

        f"<b>R:R:</b> "
        f"{signal['risk_reward']:.2f}\n"
        "\n"

        f"<b>ATR:</b> "
        f"{signal['atr']:.4f}\n"

        f"<b>RSI:</b> "
        f"{signal['rsi']:.2f}\n"

        f"<b>Trend:</b> "
        f"{signal['trend']}\n"

        f"<b>Momentum:</b> "
        f"{signal['momentum']}\n"
        "\n"

        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"
        "\n"

        "<i>Pattern → Confirmation → "
        "Trigger → Entry → TP/SL</i>"
    )


# ============================================================
# RUN SIGNAL
# ============================================================

def run_signal(
    send_notification=True
):

    candles = get_candles()

    signal = analyze_market(
        candles
    )

    STATE[
        "last_update"
    ] = utc_now().isoformat()

    STATE[
        "last_error"
    ] = None

    # --------------------------------------------------------
    # Telegram only for confirmed real signals
    # --------------------------------------------------------

    if (
        send_notification
        and signal["signal"]
        in [
            "BUY",
            "SELL"
        ]
        and signal.get(
            "valid",
            False
        )
    ):

        signal_key = (

            str(
                signal["timestamp"]
            )
            + "_"
            + signal["signal"]
            + "_"
            + str(
                signal["entry"]
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
            "Pattern → Confirmation → Trigger → Entry → TP/SL",

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

        "startup_notification":
            STATE[
                "startup_sent"
            ],

        "rules": {

            "minimum_atr":
                MINIMUM_ATR,

            "minimum_score":
                MINIMUM_SCORE,

            "minimum_risk_reward":
                MINIMUM_RISK_REWARD,

            "atr_sl_multiplier":
                ATR_SL_MULTIPLIER,

            "risk_reward":
                RISK_REWARD,

            "forward_bars":
                FORWARD_BARS
        },

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
            "healthy",

        "system":
            "Pattern → Confirmation → Trigger → Entry → TP/SL",

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

        "telegram_startup":
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

            "error":
                str(exc)
        }), 500


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (

        "🧪 <b>XAUUSD M5 BOT TEST</b>\n"
        "\n"

        "Telegram connection ทำงานปกติ ✅\n"
        "\n"

        f"<b>Symbol:</b> {SYMBOL}\n"
        "<b>Timeframe:</b> M5\n"
        "<b>System:</b> Pattern Recognition\n"
        "\n"

        "Pattern → Confirmation → Trigger "
        "→ Entry → TP/SL"
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

        "telegram":
            False,

        "error":
            error
    }), 500


# ============================================================
# BACKTEST HELPERS
# ============================================================

def calculate_trade_result(
    candles,
    entry_index,
    direction,
    entry,
    stop_loss,
    take_profit,
    forward_bars
):

    last_index = min(

        entry_index
        + forward_bars,

        len(candles)
        - 1
    )

    result = "TIMEOUT"

    exit_price = None

    exit_index = last_index

    mfe = 0.0

    mae = 0.0

    for j in range(

        entry_index,

        last_index + 1
    ):

        candle = candles[j]

        high = candle["high"]

        low = candle["low"]

        if direction == "BUY":

            favorable = (

                (
                    high
                    - entry
                )
                / entry
                * 100.0
            )

            adverse = (

                (
                    entry
                    - low
                )
                / entry
                * 100.0
            )

            mfe = max(
                mfe,
                favorable
            )

            mae = max(
                mae,
                adverse
            )

            hit_sl = (
                low
                <= stop_loss
            )

            hit_tp = (
                high
                >= take_profit
            )

            # ------------------------------------------------
            # Same conservative execution rule
            # ------------------------------------------------
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

                (
                    entry
                    - low
                )
                / entry
                * 100.0
            )

            adverse = (

                (
                    high
                    - entry
                )
                / entry
                * 100.0
            )

            mfe = max(
                mfe,
                favorable
            )

            mae = max(
                mae,
                adverse
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

    if exit_price is None:

        exit_price = candles[
            exit_index
        ]["close"]

    if direction == "BUY":

        pnl_percent = (

            (
                exit_price
                - entry
            )
            / entry
            * 100.0
        )

    else:

        pnl_percent = (

            (
                entry
                - exit_price
            )
            / entry
            * 100.0
        )

    return {

        "result":
            result,

        "exit_price":
            exit_price,

        "exit_index":
            exit_index,

        "pnl_percent":
            pnl_percent,

        "mfe_percent":
            mfe,

        "mae_percent":
            mae
    }


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

        minimum_history = max(
            EMA_SLOW + 20,
            100
        )

        end = (
            total_candles
            - FORWARD_BARS
        )

        if end <= minimum_history:

            return jsonify({

                "status":
                    "error",

                "error":
                    "Not enough candles for backtest"
            }), 400

        # ----------------------------------------------------
        # Test latest 200 possible entries
        # ----------------------------------------------------

        test_points = min(
            200,
            end
            - minimum_history
        )

        start = (
            end
            - test_points
        )

        trades = []

        pattern_frequency = {}

        wins = 0

        losses = 0

        timeouts = 0

        total_profit = 0.0

        total_loss = 0.0

        mfe_values = []

        mae_values = []

        score_values = []

        rr_values = []

        buy_count = 0

        sell_count = 0

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # We analyze candles[:i]
        #
        # The LAST candle in candles[:i] is the candle
        # where the real signal decision is made.
        #
        # Entry is ONLY accepted if:
        #
        # Pattern
        # + Confirmation
        # + Trigger
        #
        # are all satisfied.
        #
        # This is the SAME engine used by /signal.
        # ----------------------------------------------------

        for i in range(
            start,
            end
        ):

            history = candles[
                :i
            ]

            try:

                analysis = analyze_market(
                    history
                )

            except Exception:

                continue

            direction = analysis.get(
                "signal"
            )

            # ------------------------------------------------
            # Only REAL entries
            # ------------------------------------------------

            if direction not in [
                "BUY",
                "SELL"
            ]:

                continue

            if not analysis.get(
                "valid",
                False
            ):

                continue

            entry = analysis.get(
                "entry"
            )

            stop_loss = analysis.get(
                "stop_loss"
            )

            take_profit = analysis.get(
                "take_profit"
            )

            if (
                entry is None
                or stop_loss is None
                or take_profit is None
            ):

                continue

            entry = float(entry)

            stop_loss = float(
                stop_loss
            )

            take_profit = float(
                take_profit
            )

            score = float(
                analysis.get(
                    "score",
                    0
                )
            )

            risk_reward = float(
                analysis.get(
                    "risk_reward",
                    0
                )
            )

            # ------------------------------------------------
            # Pattern frequency
            # ------------------------------------------------

            for pattern in analysis.get(
                "patterns",
                []
            ):

                pattern_frequency[
                    pattern
                ] = (
                    pattern_frequency.get(
                        pattern,
                        0
                    )
                    + 1
                )

            # ------------------------------------------------
            # Direction count
            # ------------------------------------------------

            if direction == "BUY":

                buy_count += 1

            else:

                sell_count += 1

            # ------------------------------------------------
            # Simulate REAL execution
            # starting from NEXT candle
            #
            # This is important:
            #
            # Signal candle = decision
            #
            # Next candle = execution window
            # ------------------------------------------------

            result = calculate_trade_result(

                candles,

                i,

                direction,

                entry,

                stop_loss,

                take_profit,

                FORWARD_BARS
            )

            pnl = result[
                "pnl_percent"
            ]

            if result[
                "result"
            ] == "WIN":

                wins += 1

                total_profit += max(
                    pnl,
                    0.0
                )

            elif result[
                "result"
            ] == "LOSS":

                losses += 1

                total_loss += abs(
                    min(
                        pnl,
                        0.0
                    )
                )

            else:

                timeouts += 1

            mfe_values.append(
                result[
                    "mfe_percent"
                ]
            )

            mae_values.append(
                result[
                    "mae_percent"
                )

            score_values.append(
                score
            )

            rr_values.append(
                risk_reward
            )

            trades.append({

                "timestamp":
                    analysis[
                        "timestamp"
                    ],

                "signal":
                    direction,

                "patterns":
                    analysis.get(
                        "patterns",
                        []
                    ),

                "score":
                    round(
                        score,
                        2
                    ),

                "entry":
                    round(
                        entry,
                        2
                    ),

                "stop_loss":
                    round(
                        stop_loss,
                        2
                    ),

                "take_profit":
                    round(
                        take_profit,
                        2
                    ),

                "risk_reward":
                    round(
                        risk_reward,
                        2
                    ),

                "result":
                    result[
                        "result"
                    ],

                "exit_price":
                    round(
                        result[
                            "exit_price"
                        ],
                        2
                    ),

                "pnl_percent":
                    round(
                        pnl,
                        4
                    ),

                "mfe_percent":
                    round(
                        result[
                            "mfe_percent"
                        ],
                        4
                    ),

                "mae_percent":
                    round(
                        result[
                            "mae_percent"
                        ],
                        4
                    ),

                "bars_held":
                    (
                        result[
                            "exit_index"
                        ]
                        - i
                        + 1
                    )
            })

        # ====================================================
        # PERFORMANCE
        # ====================================================

        signals = len(
            trades
        )

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

            net_profit
            / signals

            if signals > 0

            else 0.0
        )

        average_mfe = (

            sum(mfe_values)
            / len(mfe_values)

            if mfe_values

            else 0.0
        )

        average_mae = (

            sum(mae_values)
            / len(mae_values)

            if mae_values

            else 0.0
        )

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

        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "status":
                "completed",

            "symbol":
                SYMBOL,

            "timeframe":
                "M5",

            "system":
                "Pattern → Confirmation → Trigger → Entry → TP/SL",

            "data_source":
                "Twelve Data XAU/USD",

            "candles_available":
                total_candles,

            "test_points":
                test_points,

            "rules": {

                "minimum_atr":
                    MINIMUM_ATR,

                "minimum_score":
                    MINIMUM_SCORE,

                "minimum_risk_reward":
                    MINIMUM_RISK_REWARD,

                "atr_sl_multiplier":
                    ATR_SL_MULTIPLIER,

                "risk_reward":
                    RISK_REWARD,

                "forward_bars":
                    FORWARD_BARS
            },

            "signals": {

                "total":
                    signals,

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
                    ),

                "average_risk_reward":
                    round(
                        average_rr,
                        2
                    )
            },

            "signal_quality": {

                "average_score":
                    round(
                        average_score,
                        2
                    )
            },

            "pattern_frequency":
                pattern_frequency,

            "recent_trades":
                trades[-20:],

            "engine_consistency": {

                "pattern":
                    True,

                "confirmation":
                    True,

                "trigger":
                    True,

                "entry":
                    True,

                "tp_sl":
                    True,

                "backtest_uses_same_engine":
                    True
            },

            "warning":
                "Historical simulation only. "
                "Spread, slippage, execution delay "
                "and broker-specific pricing are not included."
        })

    except Exception as exc:

        return jsonify({

            "status":
                "error",

            "error":
                str(exc)
        }), 500


# ============================================================
# STARTUP NOTIFICATION
#
# IMPORTANT:
#
# This executes when Gunicorn imports:
#
#     gunicorn app:app
#
# Therefore it does NOT depend on /signal.
# ============================================================

try:

    send_startup_notification()

except Exception as startup_error:

    print(
        "Telegram startup exception:",
        startup_error
    )


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

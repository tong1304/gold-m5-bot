import os
import html
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
# INDICATORS
# ============================================================

EMA_FAST = 20

EMA_SLOW = 50

RSI_PERIOD = 14

ATR_PERIOD = 14


# ============================================================
# ENTRY RULES
# ============================================================

MIN_ATR = 0.50

MIN_SCORE = 70.0

MIN_RISK_REWARD = 1.30


# ============================================================
# ENTRY TRIGGER
# ============================================================

TRIGGER_LOOKAHEAD = 3


# ============================================================
# TP / SL
# ============================================================

SL_ATR_MULTIPLIER = 1.00

TP_RR = 1.30


# ============================================================
# BACKTEST
# ============================================================

BACKTEST_POINTS = 200

FORWARD_BARS = 12


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

}


STARTUP_SENT = False


# ============================================================
# BASIC FUNCTIONS
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


def round_number(
    value,
    digits=2
):

    return round(
        float(value),
        digits
    )


def candle_body(
    candle
):

    return abs(
        candle["close"]
        - candle["open"]
    )


def candle_range(
    candle
):

    return max(
        candle["high"]
        - candle["low"],
        1e-9
    )


def upper_wick(
    candle
):

    return (
        candle["high"]
        - max(
            candle["open"],
            candle["close"]
        )
    )


def lower_wick(
    candle
):

    return (
        min(
            candle["open"],
            candle["close"]
        )
        - candle["low"]
    )


def is_bull(
    candle
):

    return (
        candle["close"]
        > candle["open"]
    )


def is_bear(
    candle
):

    return (
        candle["close"]
        < candle["open"]
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
            "UTC",

    }


    response = requests.get(

        url,

        params=params,

        timeout=30

    )


    response.raise_for_status()


    data = response.json()


    if data.get(
        "status"
    ) == "error":

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
                    str(
                        item["datetime"]
                    ),

                "open":
                    float(
                        item["open"]
                    ),

                "high":
                    float(
                        item["high"]
                    ),

                "low":
                    float(
                        item["low"]
                    ),

                "close":
                    float(
                        item["close"]
                    ),

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

            f"Not enough M5 candles: "
            f"{len(candles)} < "
            f"{minimum_required}"

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


    result = [

        float(
            values[0]
        )

    ]


    multiplier = (

        2.0
        / (
            period
            + 1.0
        )

    )


    for value in values[1:]:

        next_value = (

            multiplier
            * float(value)

            +

            (
                1.0
                - multiplier
            )
            * result[-1]

        )


        result.append(
            next_value
        )


    return result


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    values,
    period=14
):

    if len(values) < period + 1:

        return 50.0


    gains = []

    losses = []


    for i in range(
        1,
        len(values)
    ):

        change = (

            values[i]
            - values[i - 1]

        )


        gains.append(
            max(
                change,
                0.0
            )
        )


        losses.append(
            max(
                -change,
                0.0
            )
        )


    avg_gain = (

        sum(
            gains[:period]
        )
        / period

    )


    avg_loss = (

        sum(
            losses[:period]
        )
        / period

    )


    for i in range(
        period,
        len(gains)
    ):

        avg_gain = (

            (
                avg_gain
                * (
                    period - 1
                )
            )
            + gains[i]

        ) / period


        avg_loss = (

            (
                avg_loss
                * (
                    period - 1
                )
            )
            + losses[i]

        ) / period


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
            / (
                1.0 + rs
            )
        )

    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=14
):

    if len(candles) < period + 1:

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


        true_range = max(

            tr1,
            tr2,
            tr3

        )


        true_ranges.append(
            true_range
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
# MARKET SNAPSHOT
# ============================================================

def market_snapshot(
    candles
):

    closes = [

        candle["close"]

        for candle in candles

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


    rsi = calculate_rsi(

        closes,

        RSI_PERIOD

    )


    atr = calculate_atr(

        candles,

        ATR_PERIOD

    )


    current_close = candles[
        -1
    ]["close"]


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

        trend = "RANGE"


    recent = candles[
        -6:
    ]


    momentum_change = (

        recent[-1]["close"]
        - recent[0]["close"]

    )


    if momentum_change > (
        atr * 0.15
    ):

        momentum = "BULLISH"


    elif momentum_change < (
        -atr * 0.15
    ):

        momentum = "BEARISH"


    else:

        momentum = "NEUTRAL"


    lookback = candles[
        -50:
    ]


    support = min(

        candle["low"]

        for candle in lookback

    )


    resistance = max(

        candle["high"]

        for candle in lookback

    )


    return {

        "ema20":
            ema20,

        "ema50":
            ema50,

        "rsi":
            rsi,

        "atr":
            atr,

        "trend":
            trend,

        "momentum":
            momentum,

        "support":
            support,

        "resistance":
            resistance,

    }


# ============================================================
# PATTERN RECOGNITION
# ============================================================

def detect_patterns(
    candles
):

    if len(candles) < 60:

        return []


    patterns = []


    current = candles[
        -1
    ]

    previous = candles[
        -2
    ]

    previous2 = candles[
        -3
    ]


    body = candle_body(
        current
    )


    rng = candle_range(
        current
    )


    # ========================================================
    # BULLISH ENGULFING
    # ========================================================

    if (

        is_bull(current)

        and

        is_bear(previous)

        and

        current["open"]
        <= previous["close"]

        and

        current["close"]
        >= previous["open"]

        and

        body
        >= candle_body(
            previous
        ) * 0.90

    ):

        patterns.append(
            "Bullish Engulfing"
        )


    # ========================================================
    # BEARISH ENGULFING
    # ========================================================

    if (

        is_bear(current)

        and

        is_bull(previous)

        and

        current["open"]
        >= previous["close"]

        and

        current["close"]
        <= previous["open"]

        and

        body
        >= candle_body(
            previous
        ) * 0.90

    ):

        patterns.append(
            "Bearish Engulfing"
        )


    # ========================================================
    # HAMMER
    # ========================================================

    if (

        body
        <= rng * 0.40

        and

        lower_wick(
            current
        )
        >= body * 2.0

    ):

        patterns.append(
            "Hammer"
        )


    # ========================================================
    # SHOOTING STAR
    # ========================================================

    if (

        body
        <= rng * 0.40

        and

        upper_wick(
            current
        )
        >= body * 2.0

    ):

        patterns.append(
            "Shooting Star"
        )


    # ========================================================
    # MORNING STAR
    # ========================================================

    if (

        is_bear(previous2)

        and

        candle_body(
            previous
        )
        <= candle_range(
            previous
        ) * 0.40

        and

        is_bull(current)

        and

        current["close"]
        >
        (
            previous2["open"]
            + previous2["close"]
        ) / 2.0

    ):

        patterns.append(
            "Morning Star"
        )


    # ========================================================
    # EVENING STAR
    # ========================================================

    if (

        is_bull(previous2)

        and

        candle_body(
            previous
        )
        <= candle_range(
            previous
        ) * 0.40

        and

        is_bear(current)

        and

        current["close"]
        <
        (
            previous2["open"]
            + previous2["close"]
        ) / 2.0

    ):

        patterns.append(
            "Evening Star"
        )


    # ========================================================
    # BREAKOUT
    # ========================================================

    previous20 = candles[
        -21:-1
    ]


    if previous20:

        previous_high = max(

            candle["high"]

            for candle in previous20

        )


        previous_low = min(

            candle["low"]

            for candle in previous20

        )


        if (

            current["close"]
            > previous_high

        ):

            patterns.append(
                "Bullish Breakout"
            )


        if (

            current["close"]
            < previous_low

        ):

            patterns.append(
                "Bearish Breakout"
            )


    # ========================================================
    # PULLBACK
    # ========================================================

    snapshot = market_snapshot(
        candles
    )


    if snapshot["trend"] == "UPTREND":

        if (

            current["low"]
            <= snapshot["ema20"]
            * 1.0015

            and

            current["close"]
            >= snapshot["ema20"]

        ):

            patterns.append(
                "Pullback"
            )


    elif snapshot["trend"] == "DOWNTREND":

        if (

            current["high"]
            >= snapshot["ema20"]
            * 0.9985

            and

            current["close"]
            <= snapshot["ema20"]

        ):

            patterns.append(
                "Pullback"
            )


    # ========================================================
    # DOUBLE BOTTOM / DOUBLE TOP
    # ========================================================

    recent = candles[
        -30:-1
    ]


    if len(recent) >= 10:

        lows = sorted(

            (
                candle["low"]

                for candle in recent

            )

        )


        highs = sorted(

            (
                candle["high"]

                for candle in recent

            ),

            reverse=True

        )


        low1 = lows[0]

        low2 = lows[
            min(
                5,
                len(lows) - 1
            )
        ]


        high1 = highs[0]

        high2 = highs[
            min(
                5,
                len(highs) - 1
            )
        ]


        tolerance = max(

            snapshot["atr"]
            * 0.75,

            current["close"]
            * 0.0008

        )


        if (

            abs(
                low1 - low2
            )
            <= tolerance

            and

            current["close"]
            >
            low1 + tolerance

        ):

            patterns.append(
                "Double Bottom"
            )


        if (

            abs(
                high1 - high2
            )
            <= tolerance

            and

            current["close"]
            <
            high1 - tolerance

        ):

            patterns.append(
                "Double Top"
            )


    return list(
        dict.fromkeys(
            patterns
        )
    )


# ============================================================
# DIRECTION
# ============================================================

def get_direction(
    patterns,
    snapshot
):

    bullish_patterns = {

        "Bullish Engulfing",

        "Hammer",

        "Morning Star",

        "Bullish Breakout",

        "Double Bottom",

    }


    bearish_patterns = {

        "Bearish Engulfing",

        "Shooting Star",

        "Evening Star",

        "Bearish Breakout",

        "Double Top",

    }


    bullish = [

        pattern

        for pattern in patterns

        if pattern in bullish_patterns

    ]


    bearish = [

        pattern

        for pattern in patterns

        if pattern in bearish_patterns

    ]


    if bullish and not bearish:

        return "BUY", bullish


    if bearish and not bullish:

        return "SELL", bearish


    if "Pullback" in patterns:

        if snapshot["trend"] == "UPTREND":

            return "BUY", [
                "Pullback"
            ]


        if snapshot["trend"] == "DOWNTREND":

            return "SELL", [
                "Pullback"
            ]


    return None, []


# ============================================================
# CONFIRMATION ENGINE
# ============================================================

def confirmation_engine(
    candles,
    patterns
):

    snapshot = market_snapshot(
        candles
    )


    direction, directional_patterns = (
        get_direction(
            patterns,
            snapshot
        )
    )


    if direction is None:

        return {

            "candidate_direction":
                None,

            "score":
                0.0,

            "valid":
                False,

            "checks":
                {},

            "reasons": [

                "No clear directional pattern"

            ],

            "directional_patterns":
                [],

            "snapshot":
                snapshot,

        }


    checks = {

        "pattern":
            True,

        "trend":
            False,

        "momentum":
            False,

        "rsi":
            False,

        "location":
            False,

        "volatility":
            snapshot["atr"]
            >= MIN_ATR,

        "trigger":
            False,

    }


    reasons = [

        f"{len(patterns)} pattern(s) detected"

    ]


    current = candles[
        -1
    ]

    previous = candles[
        -2
    ]


    # ========================================================
    # BUY
    # ========================================================

    if direction == "BUY":

        checks["trend"] = (

            snapshot["trend"]
            == "UPTREND"

        )


        checks["momentum"] = (

            snapshot["momentum"]
            == "BULLISH"

        )


        checks["rsi"] = (

            50.0
            <= snapshot["rsi"]
            <= 70.0

        )


        near_support = (

            abs(

                current["close"]
                - snapshot["support"]

            )
            <= snapshot["atr"]
            * 1.5

        )


        breakout_zone = (

            current["close"]
            >=
            snapshot["resistance"]
            - snapshot["atr"]
            * 0.25

        )


        checks["location"] = (

            near_support
            or breakout_zone

        )


        if checks["trend"]:

            reasons.append(
                "Aligned with uptrend"
            )

        else:

            reasons.append(
                "Trend not confirmed for BUY"
            )


        if checks["momentum"]:

            reasons.append(
                "Momentum confirmed BUY"
            )

        else:

            reasons.append(
                "Momentum not confirmed"
            )


        if checks["rsi"]:

            reasons.append(
                "RSI supports BUY"
            )

        else:

            reasons.append(
                "RSI does not support BUY"
            )


        if checks["location"]:

            reasons.append(
                "BUY location confirmed"
            )

        else:

            reasons.append(
                "BUY location not ideal"
            )


    # ========================================================
    # SELL
    # ========================================================

    else:

        checks["trend"] = (

            snapshot["trend"]
            == "DOWNTREND"

        )


        checks["momentum"] = (

            snapshot["momentum"]
            == "BEARISH"

        )


        checks["rsi"] = (

            30.0
            <= snapshot["rsi"]
            <= 50.0

        )


        near_resistance = (

            abs(

                current["close"]
                - snapshot["resistance"]

            )
            <= snapshot["atr"]
            * 1.5

        )


        breakdown_zone = (

            current["close"]
            <=
            snapshot["support"]
            + snapshot["atr"]
            * 0.25

        )


        checks["location"] = (

            near_resistance
            or breakdown_zone

        )


        if checks["trend"]:

            reasons.append(
                "Aligned with downtrend"
            )

        else:

            reasons.append(
                "Trend not confirmed for SELL"
            )


        if checks["momentum"]:

            reasons.append(
                "Momentum confirmed SELL"
            )

        else:

            reasons.append(
                "Momentum not confirmed"
            )


        if checks["rsi"]:

            reasons.append(
                "RSI supports SELL"
            )

        else:

            reasons.append(
                "RSI does not support SELL"
            )


        if checks["location"]:

            reasons.append(
                "SELL location confirmed"
            )

        else:

            reasons.append(
                "SELL location not ideal"
            )


    # ========================================================
    # VOLATILITY
    # ========================================================

    if checks["volatility"]:

        reasons.append(
            "ATR sufficient"
        )

    else:

        reasons.append(
            "ATR too low"
        )


    # ========================================================
    # SCORE BEFORE TRIGGER
    # ========================================================

    score = 20.0


    if checks["trend"]:

        score += 20.0


    if checks["momentum"]:

        score += 15.0


    if checks["rsi"]:

        score += 15.0


    if checks["location"]:

        score += 10.0


    if checks["volatility"]:

        score += 10.0


    # ========================================================
    # REAL ENTRY TRIGGER
    # ========================================================

    if direction == "BUY":

        checks["trigger"] = (

            current["close"]
            > previous["high"]

        )


    else:

        checks["trigger"] = (

            current["close"]
            < previous["low"]

        )


    if checks["trigger"]:

        score += 10.0

        reasons.append(

            f"{direction} trigger confirmed"

        )

    else:

        reasons.append(

            f"Waiting for {direction} trigger"

        )


    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    valid = (

        score >= MIN_SCORE

        and checks["pattern"]

        and checks["trend"]

        and checks["momentum"]

        and checks["rsi"]

        and checks["volatility"]

        and checks["trigger"]

    )


    return {

        "candidate_direction":
            direction,

        "score":
            round(
                score,
                2
            ),

        "valid":
            valid,

        "checks":
            checks,

        "reasons":
            reasons,

        "directional_patterns":
            directional_patterns,

        "snapshot":
            snapshot,

    }


# ============================================================
# ENTRY / TP / SL
# ============================================================

def calculate_trade_levels(
    candles,
    direction
):

    snapshot = market_snapshot(
        candles
    )


    entry = candles[
        -1
    ]["close"]


    atr = max(

        snapshot["atr"],

        MIN_ATR

    )


    # ========================================================
    # BUY
    # ========================================================

    if direction == "BUY":

        structural_sl = (

            candles[-1]["low"]
            - atr * 0.10

        )


        atr_sl = (

            entry
            - atr
            * SL_ATR_MULTIPLIER

        )


        stop_loss = min(

            structural_sl,

            atr_sl

        )


        risk = (

            entry
            - stop_loss

        )


        take_profit = (

            entry
            + risk
            * TP_RR

        )


    # ========================================================
    # SELL
    # ========================================================

    else:

        structural_sl = (

            candles[-1]["high"]
            + atr * 0.10

        )


        atr_sl = (

            entry
            + atr
            * SL_ATR_MULTIPLIER

        )


        stop_loss = max(

            structural_sl,

            atr_sl

        )


        risk = (

            stop_loss
            - entry

        )


        take_profit = (

            entry
            - risk
            * TP_RR

        )


    if risk <= 0:

        return None


    risk_reward = (

        abs(
            take_profit
            - entry
        )

        /

        abs(
            entry
            - stop_loss
        )

    )


    if (

        risk_reward
        < MIN_RISK_REWARD

    ):

        return None


    return {

        "entry":
            round_number(
                entry
            ),

        "stop_loss":
            round_number(
                stop_loss
            ),

        "take_profit":
            round_number(
                take_profit
            ),

        "risk_reward":
            round(
                risk_reward,
                2
            ),

        "atr":
            round(
                atr,
                4
            ),

    }


# ============================================================
# ANALYZE MARKET
# ============================================================

def analyze_market(
    candles
):

    patterns = detect_patterns(
        candles
    )


    confirmation = (
        confirmation_engine(
            candles,
            patterns
        )
    )


    snapshot = confirmation[
        "snapshot"
    ]


    direction = confirmation[
        "candidate_direction"
    ]


    result = {

        "timestamp":
            candles[-1]["datetime"],

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "system":
            "Pattern Recognition",

        "method":
            "Pattern -> Confirmation -> Entry -> TP/SL",

        "data_source":
            "Twelve Data XAU/USD",

        "patterns":
            patterns,

        "directional_patterns":
            confirmation[
                "directional_patterns"
            ],

        "candidate_direction":
            direction,

        "trend":
            snapshot["trend"],

        "momentum":
            snapshot["momentum"],

        "ema20":
            round_number(
                snapshot["ema20"]
            ),

        "ema50":
            round_number(
                snapshot["ema50"]
            ),

        "rsi":
            round_number(
                snapshot["rsi"]
            ),

        "atr":
            round_number(
                snapshot["atr"],
                4
            ),

        "support":
            round_number(
                snapshot["support"]
            ),

        "resistance":
            round_number(
                snapshot["resistance"]
            ),

        "score":
            confirmation["score"],

        "confidence":
            confirmation["score"],

        "confirmation": {

            "candidate_direction":
                confirmation[
                    "candidate_direction"
                ],

            "score":
                confirmation[
                    "score"
                ],

            "valid":
                confirmation[
                    "valid"
                ],

            "checks":
                confirmation[
                    "checks"
                ],

            "reasons":
                confirmation[
                    "reasons"
                ],

        },

        "signal":
            "WAIT_CONFIRMATION",

        "status":
            (
                "PATTERN_DETECTED"
                if patterns
                else
                "NO_PATTERN"
            ),

        "valid":
            False,

        "entry":
            None,

        "stop_loss":
            None,

        "take_profit":
            None,

        "risk_reward":
            0.0,

        "rules": {

            "minimum_atr":
                MIN_ATR,

            "minimum_score":
                MIN_SCORE,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "trigger_lookahead":
                TRIGGER_LOOKAHEAD,

        },

    }


    if not patterns:

        result["signal"] = (
            "NO_TRADE"
        )

        result["status"] = (
            "NO_PATTERN"
        )

        return result


    if direction is None:

        result["signal"] = (
            "WAIT_CONFIRMATION"
        )

        result["status"] = (
            "AMBIGUOUS_PATTERN"
        )

        return result


    if not confirmation["valid"]:

        result["signal"] = (
            "WAIT_CONFIRMATION"
        )

        result["status"] = (
            "WAITING_FOR_TRIGGER"
        )

        return result


    levels = calculate_trade_levels(

        candles,

        direction

    )


    if not levels:

        result["signal"] = (
            "NO_TRADE"
        )

        result["status"] = (
            "INVALID_RISK"
        )

        return result


    result.update(
        levels
    )


    result["signal"] = (
        direction
    )

    result["status"] = (
        "ENTRY_CONFIRMED"
    )

    result["valid"] = True


    return result


# ============================================================
# TELEGRAM SEND
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


        data = response.json()


        if not data.get(
            "ok"
        ):

            return (

                False,

                data.get(

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

    global STARTUP_SENT


    if STARTUP_SENT:

        return


    message = (

        "🟢 <b>XAUUSD M5 BOT ONLINE</b>\n"
        "\n"

        "ระบบเริ่มทำงานเรียบร้อยแล้ว\n"
        "\n"

        f"<b>Symbol:</b> "
        f"{html.escape(SYMBOL)}\n"

        "<b>Timeframe:</b> M5\n"

        "<b>Data:</b> Twelve Data\n"

        "<b>Engine:</b> "
        "Pattern → Confirmation → Entry → TP/SL\n"
        "\n"

        "ระบบพร้อมตรวจสอบกราฟ\n"

        "และจะส่งสัญญาณเฉพาะเมื่อ "
        "Entry Trigger ผ่านกติกา\n"
        "\n"

        "<b>Backtest:</b> "
        "ใช้กติกา Entry เดียวกับระบบจริง"

    )


    ok, error = send_telegram(
        message
    )


    if ok:

        STARTUP_SENT = True


        print(

            "Telegram startup/welcome "
            "message sent successfully",

            flush=True

        )


    else:

        print(

            "Telegram startup message failed: "
            f"{error}",

            flush=True

        )


# ============================================================
# TELEGRAM SIGNAL
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


    patterns = ", ".join(

        signal[
            "patterns"
        ]

    )


    reasons = "\n".join(

        f"• {html.escape(str(reason))}"

        for reason

        in signal[
            "confirmation"
        ][
            "reasons"
        ]

    )


    return (

        f"{emoji} "
        "<b>XAUUSD M5 SIGNAL</b>\n"
        "\n"

        f"<b>SIGNAL:</b> "
        f"{direction}\n"

        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"

        f"<b>Pattern:</b> "
        f"{html.escape(patterns)}\n"
        "\n"

        f"<b>ENTRY:</b> "
        f"{signal['entry']:.2f}\n"

        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"

        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n"

        f"<b>RR:</b> "
        f"{signal['risk_reward']:.2f}\n"
        "\n"

        f"<b>Trend:</b> "
        f"{signal['trend']}\n"

        f"<b>Momentum:</b> "
        f"{signal['momentum']}\n"

        f"<b>RSI:</b> "
        f"{signal['rsi']:.2f}\n"

        f"<b>ATR:</b> "
        f"{signal['atr']:.4f}\n"
        "\n"

        "<b>CONFIRMATION</b>\n"

        f"{reasons}\n"
        "\n"

        f"<b>Time:</b> "
        f"{html.escape(signal['timestamp'])}\n"
        "\n"

        "<i>"
        "Pattern Recognition + Confirmation "
        "+ Real Entry Trigger"
        "</i>"

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


    if (

        send_notification

        and

        signal["signal"]
        in [
            "BUY",
            "SELL"
        ]

        and

        signal["valid"]

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


                    print(

                        "Telegram signal failed: "
                        f"{error}",

                        flush=True

                    )


                else:

                    print(

                        "Telegram signal "
                        "sent successfully",

                        flush=True

                    )


            STATE[
                "last_signal_key"
            ] = signal_key


    STATE[
        "last_signal"
    ] = signal


    return signal


# ============================================================
# BACKTEST SETUP
# ============================================================

def evaluate_setup_at(
    candles,
    setup_index
):

    if setup_index < 60:

        return None


    history = candles[
        :setup_index + 1
    ]


    patterns = detect_patterns(
        history
    )


    if not patterns:

        return None


    confirmation = (
        confirmation_engine(
            history,
            patterns
        )
    )


    direction = confirmation[
        "candidate_direction"
    ]


    if direction is None:

        return None


    checks = confirmation[
        "checks"
    ].copy()


    # The trigger is evaluated separately
    # in the future trigger window.

    pretrigger_score = (

        confirmation[
            "score"
        ]

        -

        (
            10.0

            if checks.get(
                "trigger",
                False
            )

            else

            0.0
        )

    )


    qualified = (

        pretrigger_score
        >= (
            MIN_SCORE
            - 10.0
        )

        and checks.get(
            "pattern",
            False
        )

        and checks.get(
            "trend",
            False
        )

        and checks.get(
            "momentum",
            False
        )

        and checks.get(
            "rsi",
            False
        )

        and checks.get(
            "volatility",
            False
        )

    )


    if not qualified:

        return None


    return {

        "setup_index":
            setup_index,

        "direction":
            direction,

        "patterns":
            patterns,

        "pretrigger_score":
            round(
                pretrigger_score,
                2
            ),

    }


# ============================================================
# TRIGGER
# ============================================================

def trigger_at(
    candles,
    index,
    direction
):

    if (

        index <= 0

        or

        index >= len(
            candles
        )

    ):

        return False


    current = candles[
        index
    ]


    previous = candles[
        index - 1
    ]


    # ========================================================
    # BUY
    # ========================================================

    if direction == "BUY":

        return (

            current["close"]
            > previous["high"]

        )


    # ========================================================
    # SELL
    # ========================================================

    return (

        current["close"]
        < previous["low"]

    )


# ============================================================
# BACKTEST TRADE
# ============================================================

def backtest_trade(
    candles,
    setup_index,
    trigger_index,
    direction
):

    # ========================================================
    # VERY IMPORTANT
    #
    # Entry / SL / TP are calculated from the trigger candle.
    #
    # This is the same calculation used by live trading.
    # ========================================================

    history = candles[
        :trigger_index + 1
    ]


    levels = calculate_trade_levels(

        history,

        direction

    )


    if not levels:

        return None


    entry = float(
        levels["entry"]
    )


    stop_loss = float(
        levels["stop_loss"]
    )


    take_profit = float(
        levels["take_profit"]
    )


    max_index = min(

        trigger_index
        + FORWARD_BARS,

        len(candles)
        - 1

    )


    result = "TIMEOUT"


    exit_price = float(

        candles[
            max_index
        ]["close"]

    )


    exit_index = max_index


    mfe = 0.0

    mae = 0.0


    # ========================================================
    # WALK FORWARD
    # ========================================================

    for j in range(

        trigger_index + 1,

        max_index + 1

    ):

        candle = candles[
            j
        ]


        # ====================================================
        # BUY
        # ====================================================

        if direction == "BUY":

            favorable = (

                (
                    candle["high"]
                    - entry
                )

                /

                entry

            ) * 100.0


            adverse = (

                (
                    entry
                    - candle["low"]
                )

                /

                entry

            ) * 100.0


            mfe = max(

                mfe,

                favorable

            )


            mae = max(

                mae,

                adverse

            )


            hit_sl = (

                candle["low"]
                <= stop_loss

            )


            hit_tp = (

                candle["high"]
                >= take_profit

            )


            # Conservative rule:
            # if same candle touches both,
            # assume SL happened first.

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


        # ====================================================
        # SELL
        # ====================================================

        else:

            favorable = (

                (
                    entry
                    - candle["low"]
                )

                /

                entry

            ) * 100.0


            adverse = (

                (
                    candle["high"]
                    - entry
                )

                /

                entry

            ) * 100.0


            mfe = max(

                mfe,

                favorable

            )


            mae = max(

                mae,

                adverse

            )


            hit_sl = (

                candle["high"]
                >= stop_loss

            )


            hit_tp = (

                candle["low"]
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


    # ========================================================
    # PNL
    # ========================================================

    if direction == "BUY":

        pnl_percent = (

            (
                exit_price
                - entry
            )

            /

            entry

        ) * 100.0


    else:

        pnl_percent = (

            (
                entry
                - exit_price
            )

            /

            entry

        ) * 100.0


    # ========================================================
    # SCORE AT ENTRY
    # ========================================================

    trigger_history = candles[
        :trigger_index + 1
    ]


    trigger_patterns = (
        detect_patterns(
            trigger_history
        )
    )


    trigger_confirmation = (
        confirmation_engine(
            trigger_history,
            trigger_patterns
        )
    )


    score = trigger_confirmation[
        "score"
    ]


    return {

        "setup_timestamp":
            candles[
                setup_index
            ]["datetime"],

        "timestamp":
            candles[
                trigger_index
            ]["datetime"],

        "signal":
            direction,

        "patterns":
            detect_patterns(
                candles[
                    :setup_index + 1
                ]
            ),

        "score":
            round(
                score,
                2
            ),

        "entry":
            round_number(
                entry
            ),

        "stop_loss":
            round_number(
                stop_loss
            ),

        "take_profit":
            round_number(
                take_profit
            ),

        "risk_reward":
            round(

                abs(
                    take_profit
                    - entry
                )

                /

                abs(
                    entry
                    - stop_loss
                ),

                2

            ),

        "result":
            result,

        "exit_price":
            round_number(
                exit_price
            ),

        "pnl_percent":
            round(
                pnl_percent,
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
            exit_index
            - trigger_index,

    }


# ============================================================
# BACKTEST ENGINE
# ============================================================

def run_backtest(
    candles
):

    total_candles = len(
        candles
    )


    end = (

        total_candles
        - FORWARD_BARS
        - 1

    )


    start = max(

        60,

        end
        - BACKTEST_POINTS

    )


    trades = []


    pattern_frequency = {}


    index = start


    # ========================================================
    # WALK THROUGH HISTORY
    # ========================================================

    while index <= end:

        setup = evaluate_setup_at(

            candles,

            index

        )


        if setup is None:

            index += 1

            continue


        direction = setup[
            "direction"
        ]


        # ====================================================
        # WAIT FOR THE SAME TRIGGER
        # ====================================================

        trigger_index = None


        last_trigger_index = min(

            index
            + TRIGGER_LOOKAHEAD,

            end

        )


        for j in range(

            index,

            last_trigger_index + 1

        ):

            if trigger_at(

                candles,

                j,

                direction

            ):

                trigger_index = j

                break


        if trigger_index is None:

            index += 1

            continue


        # ====================================================
        # ENTER TRADE
        # ====================================================

        trade = backtest_trade(

            candles,

            index,

            trigger_index,

            direction

        )


        if trade:

            trades.append(
                trade
            )


            for pattern in trade[
                "patterns"
            ]:

                pattern_frequency[
                    pattern
                ] = (

                    pattern_frequency.get(
                        pattern,
                        0
                    )

                    + 1

                )


            # =================================================
            # NO OVERLAPPING TRADES
            # =================================================

            index = (

                trigger_index

                +

                max(

                    1,

                    trade[
                        "bars_held"
                    ]

                )

            )


        else:

            index = (
                trigger_index
                + 1
            )


    # ========================================================
    # STATISTICS
    # ========================================================

    total = len(
        trades
    )


    wins = sum(

        1

        for trade in trades

        if trade["result"]
        == "WIN"

    )


    losses = sum(

        1

        for trade in trades

        if trade["result"]
        == "LOSS"

    )


    timeouts = sum(

        1

        for trade in trades

        if trade["result"]
        == "TIMEOUT"

    )


    buy_trades = sum(

        1

        for trade in trades

        if trade["signal"]
        == "BUY"

    )


    sell_trades = sum(

        1

        for trade in trades

        if trade["signal"]
        == "SELL"

    )


    total_profit = sum(

        max(
            trade["pnl_percent"],
            0.0
        )

        for trade in trades

    )


    total_loss = sum(

        abs(

            min(

                trade[
                    "pnl_percent"
                ],

                0.0

            )

        )

        for trade in trades

    )


    net_profit = (

        total_profit
        - total_loss

    )


    # ========================================================
    # DRAWDOWN
    # ========================================================

    equity = 0.0

    peak_equity = 0.0

    max_drawdown = 0.0


    for trade in trades:

        equity += trade[
            "pnl_percent"
        ]


        peak_equity = max(

            peak_equity,

            equity

        )


        drawdown = (

            peak_equity
            - equity

        )


        max_drawdown = max(

            max_drawdown,

            drawdown

        )


    # ========================================================
    # PERFORMANCE
    # ========================================================

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


        expectancy = (

            net_profit
            / total

        )


        average_mfe = (

            sum(

                trade[
                    "mfe_percent"
                ]

                for trade in trades

            )

            / total

        )


        average_mae = (

            sum(

                trade[
                    "mae_percent"
                ]

                for trade in trades

            )

            / total

        )


        average_rr = (

            sum(

                trade[
                    "risk_reward"
                ]

                for trade in trades

            )

            / total

        )


        average_score = (

            sum(

                trade[
                    "score"
                ]

                for trade in trades

            )

            / total

        )


    else:

        win_rate = 0.0

        loss_rate = 0.0

        timeout_rate = 0.0

        expectancy = 0.0

        average_mfe = 0.0

        average_mae = 0.0

        average_rr = 0.0

        average_score = 0.0


    if total_loss > 0:

        profit_factor = (

            total_profit
            / total_loss

        )


    elif total_profit > 0:

        profit_factor = "infinite"


    else:

        profit_factor = 0.0


    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "status":
            "completed",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "system":
            "Pattern Recognition",

        "data_source":
            "Twelve Data XAU/USD",

        "candles_available":
            total_candles,

        "test_points":
            max(
                0,
                end - start + 1
            ),

        "rules": {

            "minimum_atr":
                MIN_ATR,

            "minimum_score":
                MIN_SCORE,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "trigger_lookahead":
                TRIGGER_LOOKAHEAD,

            "forward_bars":
                FORWARD_BARS,

            "sl_atr_multiplier":
                SL_ATR_MULTIPLIER,

            "tp_risk_reward":
                TP_RR,

        },

        "architecture": [

            "Pattern Recognition",

            "Confirmation",

            "Entry Trigger",

            "TP/SL",

            "Telegram",

        ],

        "signals": {

            "total":
                total,

            "buy":
                buy_trades,

            "sell":
                sell_trades,

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

                    if isinstance(
                        profit_factor,
                        float
                    )

                    else
                    profit_factor
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
                ),

            "average_score":
                round(
                    average_score,
                    2
                ),

        },

        "pattern_frequency":
            pattern_frequency,

        "recent_trades":
            trades[
                -20:
            ],

        "warning":

            "Historical simulation only. "
            "Spread, slippage, execution delay "
            "and broker-specific pricing are not included.",

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

        "architecture": [

            "Pattern Recognition",

            "Confirmation",

            "Entry Trigger",

            "TP/SL",

            "Telegram",

        ],

        "data_source":
            "Twelve Data",

        "symbol":
            SYMBOL,

        "timeframe":
            "M5",

        "telegram":
            bool(

                TELEGRAM_BOT_TOKEN

                and

                TELEGRAM_CHAT_ID

            ),

        "patterns":
            PATTERNS,

        "rules": {

            "minimum_atr":
                MIN_ATR,

            "minimum_score":
                MIN_SCORE,

            "minimum_risk_reward":
                MIN_RISK_REWARD,

            "trigger_lookahead":
                TRIGGER_LOOKAHEAD,

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

        "status":
            "healthy",

        "service":
            "XAUUSD M5 Pattern Recognition Bot",

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

                and

                TELEGRAM_CHAT_ID

            ),

        "startup_notification_sent":
            STARTUP_SENT,

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
# TEST DATA
# ============================================================

@app.route("/test-data")
def test_data():

    try:

        candles = get_candles()


        latest = candles[
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
                len(candles),

            "latest":
                latest,

        })


    except Exception as exc:

        STATE[
            "last_error"
        ] = str(exc)


        return jsonify({

            "status":
                "error",

            "error":
                str(exc),

        }), 500


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram")
def test_telegram():

    message = (

        "🟢 <b>XAUUSD M5 TELEGRAM TEST</b>\n"
        "\n"

        "Telegram เชื่อมต่อสำเร็จ\n"

        "ระบบสามารถส่งข้อความแจ้งเตือนได้\n"
        "\n"

        f"<b>Time:</b> "
        f"{html.escape("
            utc_now().isoformat()
        )}"

    )


    ok, error = send_telegram(
        message
    )


    if not ok:

        return jsonify({

            "status":
                "error",

            "telegram":
                False,

            "error":
                error,

        }), 500


    return jsonify({

        "status":
            "success",

        "message":
            "Telegram test message sent successfully",

        "telegram":
            True,

    })


# ============================================================
# SIGNAL
# ============================================================

@app.route("/signal")
def signal_endpoint():

    try:

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

            "status":
                "error",

            "signal":
                "ERROR",

            "error":
                str(exc),

        }), 500


# ============================================================
# BACKTEST
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

            "status":
                "error",

            "error":
                str(exc),

        }), 500


# ============================================================
# STARTUP
# ============================================================

# IMPORTANT:
#
# This is intentionally executed when Gunicorn imports:
#
#     gunicorn app:app
#
# Therefore the Telegram welcome message does NOT depend
# on someone opening /signal.
#
# ============================================================

send_startup_notification()


# ============================================================
# LOCAL RUN
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

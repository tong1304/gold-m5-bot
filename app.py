import os
import time
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify

# ============================================================
# CONFIG
# ============================================================

app = Flask(__name__)

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

SYMBOL = "XAU/USD"
INTERVAL = "5min"

# จำนวนแท่งที่ดึงจาก Twelve Data
CANDLE_LIMIT = 1000

# จำนวนแท่งที่ใช้สร้าง Pattern
PATTERN_LENGTH = 12

# จำนวน Pattern ที่นำมาวิเคราะห์
MAX_MATCHES = 40

# ความคล้ายขั้นต่ำ
MIN_SIMILARITY = 0.60

# ------------------------------------------------------------
# Signal settings
# ------------------------------------------------------------

# ผู้ใช้ต้องการ Score >= 65
MIN_SCORE = 65.0

# Probability ขั้นต่ำสำหรับการออกออเดอร์
MIN_PROBABILITY = 70.0

# Pattern อย่างน้อย
MIN_MATCHES = 20

# ATR multiplier สำหรับ safety SL
SL_ATR_MULTIPLIER = 1.0

# ============================================================
# STATE
# ============================================================

state = {
    "last_signal": None,
    "last_update": None,
    "last_error": None,
}


# ============================================================
# UTILITY
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


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
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured")

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
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

    if "status" in data and data["status"] == "error":
        raise RuntimeError(
            data.get("message", "Twelve Data API error")
        )

    values = data.get("values")

    if not values:
        raise RuntimeError("No candle data received from Twelve Data")

    df = pd.DataFrame(values)

    required = [
        "datetime",
        "open",
        "high",
        "low",
        "close",
    ]

    for column in required:
        if column not in df.columns:
            raise RuntimeError(
                f"Missing candle column: {column}"
            )

    for column in [
        "open",
        "high",
        "low",
        "close",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "datetime",
            "open",
            "high",
            "low",
            "close",
        ]
    )

    # Twelve Data returns newest first
    df = df.sort_values("datetime")

    df = df.reset_index(drop=True)

    return df


# ============================================================
# ATR
# ============================================================

def calculate_atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    atr = true_range.rolling(
        period
    ).mean()

    return atr


# ============================================================
# PATTERN CREATION
# ============================================================

def create_pattern(df):
    """
    สร้าง Pattern จากกราฟราคาโดย normalize
    เพื่อให้เปรียบเทียบรูปทรงของกราฟได้
    แม้ราคาจะอยู่คนละระดับ
    """

    closes = df["close"].values.astype(float)

    if len(closes) < PATTERN_LENGTH:
        return None

    closes = closes[-PATTERN_LENGTH:]

    base = closes[0]

    if base == 0:
        return None

    normalized = (
        closes / base
    ) - 1.0

    return normalized


# ============================================================
# PATTERN SIMILARITY
# ============================================================

def pattern_similarity(pattern_a, pattern_b):
    if pattern_a is None or pattern_b is None:
        return 0.0

    if len(pattern_a) != len(pattern_b):
        return 0.0

    distance = np.sqrt(
        np.mean(
            (pattern_a - pattern_b) ** 2
        )
    )

    # Convert distance to similarity
    similarity = np.exp(
        -distance * 25.0
    )

    return float(
        np.clip(
            similarity,
            0.0,
            1.0,
        )
    )


# ============================================================
# HISTORICAL PATTERN SEARCH
# ============================================================

def find_historical_patterns(df):
    current_pattern = create_pattern(df)

    if current_pattern is None:
        return []

    matches = []

    # ต้องเหลือแท่งหลัง Pattern
    # เพื่อดูว่า Pattern ในอดีตไปทางไหน
    start_index = PATTERN_LENGTH
    end_index = (
        len(df)
        - PATTERN_LENGTH
        - 1
    )

    for i in range(
        start_index,
        end_index + 1,
    ):

        historical_window = df.iloc[
            i - PATTERN_LENGTH:i
        ]

        historical_pattern = create_pattern(
            historical_window
        )

        if historical_pattern is None:
            continue

        similarity = pattern_similarity(
            current_pattern,
            historical_pattern,
        )

        if similarity < MIN_SIMILARITY:
            continue

        historical_close = safe_float(
            df.iloc[i - 1]["close"]
        )

        next_close = safe_float(
            df.iloc[i]["close"]
        )

        if historical_close <= 0:
            continue

        movement = (
            next_close
            - historical_close
        ) / historical_close * 100.0

        if movement > 0:
            direction = "BUY"
        elif movement < 0:
            direction = "SELL"
        else:
            direction = "FLAT"

        matches.append(
            {
                "index": i,
                "similarity": similarity,
                "movement_percent": movement,
                "direction": direction,
            }
        )

    matches.sort(
        key=lambda x: x["similarity"],
        reverse=True,
    )

    return matches[:MAX_MATCHES]


# ============================================================
# HISTORICAL STATISTICS
# ============================================================

def calculate_statistics(matches):
    if not matches:
        return {
            "sample_size": 0,
            "buy_probability": 0.0,
            "sell_probability": 0.0,
            "flat_probability": 0.0,
            "average_similarity": 0.0,
            "best_similarity": 0.0,
            "expected_up_percent": 0.0,
            "expected_down_percent": 0.0,
        }

    buy = [
        x
        for x in matches
        if x["direction"] == "BUY"
    ]

    sell = [
        x
        for x in matches
        if x["direction"] == "SELL"
    ]

    flat = [
        x
        for x in matches
        if x["direction"] == "FLAT"
    ]

    total = len(matches)

    buy_probability = (
        len(buy) / total * 100
    )

    sell_probability = (
        len(sell) / total * 100
    )

    flat_probability = (
        len(flat) / total * 100
    )

    positive_moves = [
        x["movement_percent"]
        for x in matches
        if x["movement_percent"] > 0
    ]

    negative_moves = [
        x["movement_percent"]
        for x in matches
        if x["movement_percent"] < 0
    ]

    expected_up = (
        float(np.mean(positive_moves))
        if positive_moves
        else 0.0
    )

    expected_down = (
        abs(float(np.mean(negative_moves)))
        if negative_moves
        else 0.0
    )

    return {
        "sample_size": total,
        "buy_probability": round(
            buy_probability,
            2,
        ),
        "sell_probability": round(
            sell_probability,
            2,
        ),
        "flat_probability": round(
            flat_probability,
            2,
        ),
        "average_similarity": round(
            float(
                np.mean(
                    [
                        x["similarity"]
                        for x in matches
                    ]
                )
            ),
            4,
        ),
        "best_similarity": round(
            max(
                x["similarity"]
                for x in matches
            ),
            4,
        ),
        "expected_up_percent": round(
            expected_up,
            4,
        ),
        "expected_down_percent": round(
            expected_down,
            4,
        ),
    }


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    probability,
    matches,
    average_similarity,
):
    """
    Score ไม่ใช่ Probability

    Probability = ผลจาก Pattern ในอดีต

    Score = ความแข็งแรงโดยรวมของ Pattern
    """

    probability_score = min(
        probability,
        100.0,
    )

    sample_score = min(
        len(matches) / MAX_MATCHES * 100.0,
        100.0,
    )

    similarity_score = (
        average_similarity * 100.0
    )

    score = (
        probability_score * 0.55
        + sample_score * 0.20
        + similarity_score * 0.25
    )

    return round(
        float(score),
        2,
    )


# ============================================================
# ENTRY / SL / TP
# ============================================================

def calculate_trade_levels(
    direction,
    entry,
    atr,
    statistics,
):
    """
    Dynamic TP/SL

    ใช้ ATR + สถิติ Pattern
    """

    if atr <= 0:
        atr = entry * 0.001

    up_probability = (
        statistics["buy_probability"]
    )

    down_probability = (
        statistics["sell_probability"]
    )

    if direction == "BUY":

        confidence_factor = max(
            1.0,
            min(
                2.0,
                up_probability / 50.0,
            ),
        )

        sl_distance = (
            atr
            * SL_ATR_MULTIPLIER
        )

        tp_distance = (
            atr
            * confidence_factor
        )

        stop_loss = (
            entry
            - sl_distance
        )

        take_profit = (
            entry
            + tp_distance
        )

    else:

        confidence_factor = max(
            1.0,
            min(
                2.0,
                down_probability / 50.0,
            ),
        )

        sl_distance = (
            atr
            * SL_ATR_MULTIPLIER
        )

        tp_distance = (
            atr
            * confidence_factor
        )

        stop_loss = (
            entry
            + sl_distance
        )

        take_profit = (
            entry
            - tp_distance
        )

    return (
        round(entry, 2),
        round(stop_loss, 2),
        round(take_profit, 2),
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(df):

    if len(df) < (
        PATTERN_LENGTH * 2 + 20
    ):
        raise RuntimeError(
            "Not enough candle data"
        )

    matches = find_historical_patterns(
        df
    )

    statistics = calculate_statistics(
        matches
    )

    if not matches:
        return {
            "timestamp": str(
                df.iloc[-1]["datetime"]
            ),
            "symbol": SYMBOL,
            "timeframe": "M5",
            "signal": "NO_TRADE",
            "score": 0.0,
            "entry": safe_float(
                df.iloc[-1]["close"]
            ),
            "stop_loss": None,
            "take_profit": None,
            "historical_statistics": statistics,
            "matched_patterns": 0,
            "method": (
                "M5 historical pattern matching"
            ),
            "data_source": (
                "Twelve Data XAU/USD"
            ),
        }

    buy_probability = statistics[
        "buy_probability"
    ]

    sell_probability = statistics[
        "sell_probability"
    ]

    average_similarity = statistics[
        "average_similarity"
    ]

    entry = safe_float(
        df.iloc[-1]["close"]
    )

    atr_series = calculate_atr(df)

    atr = safe_float(
        atr_series.iloc[-1],
        entry * 0.001,
    )

    # --------------------------------------------------------
    # เลือก Probability สูงสุด
    # --------------------------------------------------------

    if buy_probability > sell_probability:
        direction = "BUY"
        probability = buy_probability

    elif sell_probability > buy_probability:
        direction = "SELL"
        probability = sell_probability

    else:
        direction = "NO_TRADE"
        probability = 0.0

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = calculate_score(
        probability,
        matches,
        average_similarity,
    )

    # --------------------------------------------------------
    # SIGNAL FILTER
    # --------------------------------------------------------

    valid_signal = (
        direction in ["BUY", "SELL"]
        and probability >= MIN_PROBABILITY
        and score >= MIN_SCORE
        and len(matches) >= MIN_MATCHES
    )

    if not valid_signal:

        return {
            "timestamp": str(
                df.iloc[-1]["datetime"]
            ),
            "symbol": SYMBOL,
            "timeframe": "M5",
            "signal": "NO_TRADE",
            "score": score,
            "probability": round(
                probability,
                2,
            ),
            "entry": round(
                entry,
                2,
            ),
            "stop_loss": None,
            "take_profit": None,
            "atr": round(
                atr,
                4,
            ),
            "historical_statistics": statistics,
            "matched_patterns": len(
                matches
            ),
            "method": (
                "M5 historical pattern matching"
            ),
            "data_source": (
                "Twelve Data XAU/USD"
            ),
        }

    # --------------------------------------------------------
    # TRADE LEVELS
    # --------------------------------------------------------

    (
        entry,
        stop_loss,
        take_profit,
    ) = calculate_trade_levels(
        direction,
        entry,
        atr,
        statistics,
    )

    return {
        "timestamp": str(
            df.iloc[-1]["datetime"]
        ),
        "symbol": SYMBOL,
        "timeframe": "M5",
        "signal": direction,
        "score": score,
        "probability": round(
            probability,
            2,
        ),
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "atr": round(
            atr,
            4,
        ),
        "historical_statistics": statistics,
        "matched_patterns": len(
            matches
        ),
        "method": (
            "M5 historical pattern matching"
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
        return False, (
            "TELEGRAM_BOT_TOKEN "
            "is not configured"
        )

    if not TELEGRAM_CHAT_ID:
        return False, (
            "TELEGRAM_CHAT_ID "
            "is not configured"
        )

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
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

        return True, None

    except Exception as e:

        return False, str(e)


def format_signal_message(signal):

    direction = signal["signal"]

    if direction == "BUY":

        emoji = "🟢"

    elif direction == "SELL":

        emoji = "🔴"

    else:

        return None

    stats = signal[
        "historical_statistics"
    ]

    message = (
        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n\n"
        f"<b>Signal:</b> {direction}\n"
        f"<b>Probability:</b> "
        f"{signal['probability']:.2f}%\n"
        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n\n"
        f"<b>Entry:</b> "
        f"{signal['entry']:.2f}\n"
        f"<b>TP:</b> "
        f"{signal['take_profit']:.2f}\n"
        f"<b>SL:</b> "
        f"{signal['stop_loss']:.2f}\n\n"
        f"<b>Patterns:</b> "
        f"{signal['matched_patterns']}\n"
        f"<b>Similarity:</b> "
        f"{stats['average_similarity']:.4f}\n\n"
        f"<b>Time:</b> "
        f"{signal['timestamp']}\n\n"
        f"<i>Historical Pattern Analysis</i>"
    )

    return message


# ============================================================
# SIGNAL EXECUTION
# ============================================================

def run_signal():

    df = get_candles()

    signal = generate_signal(df)

    state["last_update"] = utc_now().isoformat()
    state["last_error"] = None

    # --------------------------------------------------------
    # ส่ง Telegram เฉพาะ BUY / SELL
    # --------------------------------------------------------

    if signal["signal"] in [
        "BUY",
        "SELL",
    ]:

        # ป้องกันการส่ง Signal เดิมซ้ำ
        signal_key = (
            f"{signal['timestamp']}_"
            f"{signal['signal']}"
        )

        previous = state.get(
            "last_signal_key"
        )

        if previous != signal_key:

            message = format_signal_message(
                signal
            )

            if message:

                ok, error = send_telegram(
                    message
                )

                if not ok:
                    state[
                        "last_error"
                    ] = error

            state[
                "last_signal_key"
            ] = signal_key

    state["last_signal"] = signal

    return signal


# ============================================================
# BACKGROUND LOOP
# ============================================================

def background_worker():

    while True:

        try:

            run_signal()

        except Exception as e:

            state[
                "last_error"
            ] = str(e)

        # เช็กทุก 60 วินาที
        time.sleep(60)


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():

    return jsonify(
        {
            "name": (
                "XAUUSD M5 Telegram Signal"
            ),
            "status": "online",
            "data_source": "Twelve Data",
            "symbol": SYMBOL,
            "timeframe": "M5",
            "signal_rule": (
                "Probability >= 70% "
                "and Score >= 65"
            ),
            "endpoints": [
                "/signal",
                "/backtest",
                "/health",
            ],
        }
    )


@app.route("/health")
def health():

    return jsonify(
        {
            "status": "healthy",
            "data_source": "Twelve Data",
            "symbol": SYMBOL,
            "timeframe": "M5",
            "telegram": bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),
            "last_update": state[
                "last_update"
            ],
            "last_signal": state[
                "last_signal"
            ],
            "error": state[
                "last_error"
            ],
        }
    )


@app.route("/signal")
def signal_endpoint():

    try:

        signal = run_signal()

        return jsonify(signal)

    except Exception as e:

        state[
            "last_error"
        ] = str(e)

        return jsonify(
            {
                "signal": "ERROR",
                "error": str(e),
            }
        ), 500


# ============================================================
# SIMPLE BACKTEST
# ============================================================

@app.route("/backtest")
def backtest():

    try:

        df = get_candles()

        total = 0
        wins = 0
        losses = 0

        # ใช้ข้อมูลย้อนหลัง
        # จำลอง Signal จาก Pattern

        for i in range(
            PATTERN_LENGTH * 2,
            len(df) - 1,
        ):

            historical_df = df.iloc[
                :i
            ].copy()

            try:

                signal = generate_signal(
                    historical_df
                )

            except Exception:
                continue

            if signal["signal"] not in [
                "BUY",
                "SELL",
            ]:
                continue

            total += 1

            current_close = safe_float(
                df.iloc[i]["close"]
            )

            next_close = safe_float(
                df.iloc[i + 1]["close"]
            )

            if (
                signal["signal"]
                == "BUY"
            ):

                if next_close > current_close:
                    wins += 1
                else:
                    losses += 1

            elif (
                signal["signal"]
                == "SELL"
            ):

                if next_close < current_close:
                    wins += 1
                else:
                    losses += 1

        win_rate = (
            wins / total * 100
            if total > 0
            else 0.0
        )

        return jsonify(
            {
                "symbol": SYMBOL,
                "timeframe": "M5",
                "minimum_probability": (
                    MIN_PROBABILITY
                ),
                "minimum_score": (
                    MIN_SCORE
                ),
                "signals": total,
                "wins": wins,
                "losses": losses,
                "win_rate": round(
                    win_rate,
                    2,
                ),
                "method": (
                    "Historical Pattern "
                    "Backtest"
                ),
            }
        )

    except Exception as e:

        return jsonify(
            {
                "error": str(e)
            }
        ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    # Background analysis
    thread = threading.Thread(
        target=background_worker,
        daemon=True,
    )

    thread.start()

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

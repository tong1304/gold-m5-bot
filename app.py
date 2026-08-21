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
# SYSTEM CONFIGURATION
# ============================================================

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"

# จำนวนแท่งที่ดึงจาก Twelve Data
CANDLE_LIMIT = 1000

# ความยาว Pattern ที่นำมาเปรียบเทียบ
PATTERN_LENGTH = 12

# จำนวน Pattern ที่เก็บหลังจากเรียงตาม similarity
MAX_MATCHES = 40

# Similarity ขั้นต่ำ
MIN_SIMILARITY = 0.60

# ============================================================
# USER SIGNAL RULE
# ============================================================

# Probability ต้อง >= 70%
MIN_PROBABILITY = 70.0

# Score ต้อง >= 65
MIN_SCORE = 65.0

# Pattern อย่างน้อย
MIN_MATCHES = 20


# ============================================================
# STATE
# ============================================================

STATE = {
    "last_update": None,
    "last_signal": None,
    "last_signal_key": None,
    "last_error": None,
}


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def round_price(value):
    return round(float(value), 2)


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
                "Twelve Data API error"
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

            candle = {
                "datetime": item["datetime"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
            }

            candles.append(candle)

        except Exception:
            continue

    # Twelve Data มักส่งข้อมูล newest -> oldest
    # เราต้องการ oldest -> newest
    candles.reverse()

    if len(candles) < (
        PATTERN_LENGTH * 2 + 10
    ):
        raise RuntimeError(
            "Not enough candle data"
        )

    return candles


# ============================================================
# ATR
# ============================================================

def calculate_atr(candles, period=14):

    if len(candles) < period + 1:
        return 0.0

    true_ranges = []

    for i in range(1, len(candles)):

        current = candles[i]
        previous = candles[i - 1]

        high = current["high"]
        low = current["low"]
        previous_close = previous["close"]

        tr1 = high - low
        tr2 = abs(high - previous_close)
        tr3 = abs(low - previous_close)

        true_range = max(
            tr1,
            tr2,
            tr3,
        )

        true_ranges.append(
            true_range
        )

    recent = true_ranges[-period:]

    if not recent:
        return 0.0

    return sum(recent) / len(recent)


# ============================================================
# PRICE PATTERN
# ============================================================

def make_pattern(candles):

    if len(candles) < PATTERN_LENGTH:
        return None

    window = candles[
        -PATTERN_LENGTH:
    ]

    first_close = window[0]["close"]

    if first_close <= 0:
        return None

    pattern = []

    for candle in window:

        normalized = (
            candle["close"]
            / first_close
            - 1.0
        )

        pattern.append(
            normalized
        )

    return pattern


# ============================================================
# PATTERN SIMILARITY
# ============================================================

def pattern_similarity(
    pattern_a,
    pattern_b,
):

    if not pattern_a or not pattern_b:
        return 0.0

    if len(pattern_a) != len(pattern_b):
        return 0.0

    squared = 0.0

    for a, b in zip(
        pattern_a,
        pattern_b,
    ):

        diff = a - b
        squared += diff * diff

    mse = (
        squared
        / len(pattern_a)
    )

    distance = math.sqrt(mse)

    similarity = math.exp(
        -distance * 25.0
    )

    if similarity < 0:
        similarity = 0

    if similarity > 1:
        similarity = 1

    return similarity


# ============================================================
# FIND HISTORICAL PATTERNS
# ============================================================

def find_matches(candles):

    current_pattern = make_pattern(
        candles
    )

    if current_pattern is None:
        return []

    matches = []

    # ต้องมีแท่งอนาคตอย่างน้อย 1 แท่ง
    last_index = (
        len(candles)
        - PATTERN_LENGTH
        - 1
    )

    for i in range(
        PATTERN_LENGTH,
        last_index + 1,
    ):

        historical_window = candles[
            i - PATTERN_LENGTH:i
        ]

        historical_pattern = make_pattern(
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

        historical_close = candles[
            i - 1
        ]["close"]

        future_close = candles[
            i
        ]["close"]

        if historical_close <= 0:
            continue

        movement_percent = (
            (
                future_close
                - historical_close
            )
            / historical_close
        ) * 100.0

        if movement_percent > 0:
            direction = "BUY"

        elif movement_percent < 0:
            direction = "SELL"

        else:
            direction = "FLAT"

        matches.append(
            {
                "index": i,
                "similarity": similarity,
                "movement_percent": movement_percent,
                "direction": direction,
            }
        )

    # เรียงจาก Pattern ที่คล้ายที่สุด
    matches.sort(
        key=lambda x: x["similarity"],
        reverse=True,
    )

    return matches[
        :MAX_MATCHES
    ]


# ============================================================
# HISTORICAL STATISTICS
# ============================================================

def historical_statistics(matches):

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

    buy_count = 0
    sell_count = 0
    flat_count = 0

    similarities = []

    up_moves = []
    down_moves = []

    for match in matches:

        direction = match[
            "direction"
        ]

        similarity = match[
            "similarity"
        ]

        movement = match[
            "movement_percent"
        ]

        similarities.append(
            similarity
        )

        if direction == "BUY":

            buy_count += 1

            if movement > 0:
                up_moves.append(
                    movement
                )

        elif direction == "SELL":

            sell_count += 1

            if movement < 0:
                down_moves.append(
                    abs(movement)
                )

        else:

            flat_count += 1

    total = len(matches)

    buy_probability = (
        buy_count
        / total
        * 100.0
    )

    sell_probability = (
        sell_count
        / total
        * 100.0
    )

    flat_probability = (
        flat_count
        / total
        * 100.0
    )

    average_similarity = (
        sum(similarities)
        / len(similarities)
    )

    best_similarity = max(
        similarities
    )

    expected_up = (
        sum(up_moves)
        / len(up_moves)
        if up_moves
        else 0.0
    )

    expected_down = (
        sum(down_moves)
        / len(down_moves)
        if down_moves
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
            average_similarity,
            4,
        ),
        "best_similarity": round(
            best_similarity,
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

    # Probability เป็นองค์ประกอบหลัก
    probability_component = min(
        probability,
        100.0,
    )

    # จำนวน Pattern
    sample_component = min(
        (
            len(matches)
            / MAX_MATCHES
        ) * 100.0,
        100.0,
    )

    # ความคล้าย
    similarity_component = (
        average_similarity
        * 100.0
    )

    score = (
        probability_component
        * 0.60
        +
        sample_component
        * 0.15
        +
        similarity_component
        * 0.25
    )

    return round(
        score,
        2,
    )


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    direction,
    entry,
    atr,
    statistics,
):

    if atr <= 0:
        atr = entry * 0.001

    if direction == "BUY":

        probability = statistics[
            "buy_probability"
        ]

        # Probability สูงขึ้น
        # ให้ TP กว้างขึ้นเล็กน้อย
        tp_multiplier = (
            1.0
            + (
                probability
                - 70.0
            ) / 100.0
        )

        # SL 1 ATR
        sl_distance = atr

        # TP ประมาณ 1.0 - 1.3 ATR
        tp_distance = (
            atr
            * tp_multiplier
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

        probability = statistics[
            "sell_probability"
        ]

        tp_multiplier = (
            1.0
            + (
                probability
                - 70.0
            ) / 100.0
        )

        sl_distance = atr

        tp_distance = (
            atr
            * tp_multiplier
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
        round_price(entry),
        round_price(stop_loss),
        round_price(take_profit),
    )


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(candles):

    latest = candles[-1]

    entry = latest["close"]

    atr = calculate_atr(
        candles
    )

    matches = find_matches(
        candles
    )

    statistics = historical_statistics(
        matches
    )

    if not matches:

        return {
            "timestamp": latest[
                "datetime"
            ],
            "symbol": SYMBOL,
            "timeframe": "M5",
            "signal": "NO_TRADE",
            "score": 0.0,
            "probability": 0.0,
            "entry": round_price(
                entry
            ),
            "stop_loss": None,
            "take_profit": None,
            "atr": round(
                atr,
                4,
            ),
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

    # เลือกทิศทางที่ Probability สูงกว่า
    if (
        buy_probability
        > sell_probability
    ):

        direction = "BUY"

        probability = (
            buy_probability
        )

    elif (
        sell_probability
        > buy_probability
    ):

        direction = "SELL"

        probability = (
            sell_probability
        )

    else:

        direction = "NO_TRADE"

        probability = 0.0

    score = calculate_score(
        probability,
        matches,
        statistics[
            "average_similarity"
        ],
    )

    # ========================================================
    # STRICT FILTER
    # ========================================================

    valid = (
        direction
        in [
            "BUY",
            "SELL",
        ]
        and probability
        >= MIN_PROBABILITY
        and score
        >= MIN_SCORE
        and len(matches)
        >= MIN_MATCHES
    )

    # ========================================================
    # NO TRADE
    # ========================================================

    if not valid:

        return {
            "timestamp": latest[
                "datetime"
            ],
            "symbol": SYMBOL,
            "timeframe": "M5",
            "signal": "NO_TRADE",
            "score": score,
            "probability": round(
                probability,
                2,
            ),
            "entry": round_price(
                entry
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

    # ========================================================
    # BUY / SELL
    # ========================================================

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
        "timestamp": latest[
            "datetime"
        ],
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
# TELEGRAM MESSAGE
# ============================================================

def format_telegram_message(
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

    stats = signal[
        "historical_statistics"
    ]

    message = (
        f"{emoji} <b>XAUUSD M5 SIGNAL</b>\n"
        f"\n"
        f"<b>Signal:</b> {direction}\n"
        f"<b>Probability:</b> "
        f"{signal['probability']:.2f}%\n"
        f"<b>Score:</b> "
        f"{signal['score']:.2f}\n"
        f"\n"
        f"<b>Entry:</b> "
        f"{signal['entry']:.2f}\n"
        f"<b>Take Profit:</b> "
        f"{signal['take_profit']:.2f}\n"
        f"<b>Stop Loss:</b> "
        f"{signal['stop_loss']:.2f}\n"
        f"\n"
        f"<b>Patterns:</b> "
        f"{signal['matched_patterns']}\n"
        f"<b>Average Similarity:</b> "
        f"{stats['average_similarity']:.4f}\n"
        f"<b>Best Similarity:</b> "
        f"{stats['best_similarity']:.4f}\n"
        f"\n"
        f"<b>BUY:</b> "
        f"{stats['buy_probability']:.2f}%\n"
        f"<b>SELL:</b> "
        f"{stats['sell_probability']:.2f}%\n"
        f"\n"
        f"<b>Time:</b> "
        f"{signal['timestamp']}\n"
        f"\n"
        f"<i>Historical Pattern Analysis</i>"
    )

    return message


# ============================================================
# RUN SIGNAL
# ============================================================

def run_signal(
    send_notification=True
):

    candles = get_candles()

    signal = generate_signal(
        candles
    )

    STATE[
        "last_update"
    ] = utc_now().isoformat()

    STATE[
        "last_error"
    ] = None

    # ========================================================
    # TELEGRAM
    # ========================================================

    if (
        send_notification
        and signal["signal"]
        in [
            "BUY",
            "SELL",
        ]
    ):

        signal_key = (
            str(
                signal["timestamp"]
            )
            + "_"
            + signal["signal"]
        )

        # ป้องกัน Signal ซ้ำ
        if (
            STATE[
                "last_signal_key"
            ]
            != signal_key
        ):

            message = (
                format_telegram_message(
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

    STATE[
        "last_signal"
    ] = signal

    return signal


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify(
        {
            "name": (
                "XAUUSD M5 Telegram Signal"
            ),
            "status": "online",
            "data_source": (
                "Twelve Data"
            ),
            "symbol": SYMBOL,
            "timeframe": "M5",
            "rules": {
                "minimum_probability": (
                    MIN_PROBABILITY
                ),
                "minimum_score": (
                    MIN_SCORE
                ),
                "minimum_patterns": (
                    MIN_MATCHES
                ),
                "minimum_similarity": (
                    MIN_SIMILARITY
                ),
            },
            "telegram": bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),
            "endpoints": [
                "/",
                "/health",
                "/signal",
                "/backtest",
            ],
        }
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    try:

        # เช็ก API Key เท่านั้น
        # ไม่ยิง Twelve Data ทุก health check
        api_configured = bool(
            TWELVE_DATA_API_KEY
        )

        telegram_configured = bool(
            TELEGRAM_BOT_TOKEN
            and TELEGRAM_CHAT_ID
        )

        return jsonify(
            {
                "status": "healthy",
                "data_source": (
                    "Twelve Data"
                ),
                "symbol": SYMBOL,
                "timeframe": "M5",
                "candles": CANDLE_LIMIT,
                "telegram": (
                    telegram_configured
                ),
                "twelve_data": (
                    api_configured
                ),
                "last_update": STATE[
                    "last_update"
                ],
                "last_signal": STATE[
                    "last_signal"
                ],
                "error": STATE[
                    "last_error"
                ],
            }
        )

    except Exception as exc:

        return jsonify(
            {
                "status": "error",
                "error": str(exc),
            }
        ), 500


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

        return jsonify(
            {
                "signal": "ERROR",
                "error": str(exc),
            }
        ), 500


# ============================================================
# BACKTEST
# ============================================================

@app.route("/backtest")
def backtest():

    try:

        candles = get_candles()

        signals = 0
        wins = 0
        losses = 0

        # จำกัดจำนวนจุดเพื่อไม่ให้ Render Free หนักเกินไป
        start = max(
            PATTERN_LENGTH * 2,
            50,
        )

        end = len(candles) - 1

        # ใช้เฉพาะช่วงล่าสุด
        # สำหรับ Backtest แบบเบา
        max_test_points = 120

        if (
            end - start
            > max_test_points
        ):

            start = (
                end
                - max_test_points
            )

        for i in range(
            start,
            end,
        ):

            historical_candles = (
                candles[:i]
            )

            try:

                signal = generate_signal(
                    historical_candles
                )

            except Exception:

                continue

            if signal[
                "signal"
            ] not in [
                "BUY",
                "SELL",
            ]:

                continue

            signals += 1

            current_close = candles[
                i
            ]["close"]

            next_close = candles[
                i + 1
            ]["close"]

            if (
                signal["signal"]
                == "BUY"
            ):

                if (
                    next_close
                    > current_close
                ):

                    wins += 1

                else:

                    losses += 1

            elif (
                signal["signal"]
                == "SELL"
            ):

                if (
                    next_close
                    < current_close
                ):

                    wins += 1

                else:

                    losses += 1

        if signals > 0:

            win_rate = (
                wins
                / signals
                * 100.0
            )

        else:

            win_rate = 0.0

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
                "minimum_patterns": (
                    MIN_MATCHES
                ),
                "test_points": (
                    max_test_points
                ),
                "signals": signals,
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
                "warning": (
                    "This is a simple "
                    "historical test and "
                    "does not guarantee "
                    "future performance."
                ),
            }
        )

    except Exception as exc:

        return jsonify(
            {
                "error": str(exc)
            }
        ), 500


# ============================================================
# MAIN
# ============================================================

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

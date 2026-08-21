import os
import requests
import pandas as pd
import yfinance as yf
from time import sleep
import threading
from flask import Flask
from datetime import datetime, timezone

# --- 1. DUMMY WEB SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "M5 Pure Aggressive Scalper Bot is Live!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
SYMBOL = "GC=F"
TIMEFRAME = "5m"
CHECK_INTERVAL = 60  # สแกนทุก 60 วินาที ให้สัญญาณมาไวที่สุด

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

# --- 3. NEWS FILTER (30 Mins Buffer) ---
def check_high_impact_news(buffer_minutes=30):
    url = "https://n3.forexfactory1.com/ff_calendar_thisweek.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return False
        
        events = response.json()
        now_utc = datetime.now(timezone.utc)

        for event in events:
            if event.get('impact') == 'High' and 'USD' in event.get('country', ''):
                event_date_str = event.get('date')
                if event_date_str:
                    event_time = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
                    time_diff = abs((event_time - now_utc).total_seconds() / 60)
                    if time_diff <= buffer_minutes:
                        return True
    except Exception as e:
        print(f"News Filter Error: {e}")
        return False
    return False

# --- 4. AGGRESSIVE M5 SCANNER ---
def scan_m5_pure():
    print("Scanning M5 Pure Aggressive Setup...")
    
    if check_high_impact_news(buffer_minutes=30):
        print("⏭️ Skipped due to USD High-Impact News Buffer.")
        return

    try:
        df = yf.download(tickers=SYMBOL, period="2d", interval=TIMEFRAME, progress=False)
        
        if df.empty or len(df) < 20:
            return

        # Swing High/Low ย้อนหลัง 10 แท่ง M5
        df['Swing_High'] = df['High'].shift(2).rolling(window=10).max()
        df['Swing_Low'] = df['Low'].shift(2).rolling(window=10).min()

        c_close = df['Close'].iloc[-2]
        c_open = df['Open'].iloc[-2]
        c_high = df['High'].iloc[-2]
        c_low = df['Low'].iloc[-2]

        p_close = df['Close'].iloc[-3]
        p_open = df['Open'].iloc[-3]

        swing_high = df['Swing_High'].iloc[-2]
        swing_low = df['Swing_Low'].iloc[-2]

        body = abs(c_close - c_open)
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)

        entry_price = round(c_close, 2)

        # 🟢 BUY SIGNAL: กวาด Low + เกิด Rejection / Engulfing
        is_sweep_low = c_low < swing_low
        is_bullish_action = (c_close > c_open and c_close > p_open) or (lower_wick >= body * 1.2)

        if is_sweep_low and is_bullish_action:
            sl_price = round(c_low - 0.50, 2)
            tp_price = round(entry_price + (abs(entry_price - sl_price) * 1.5), 2)

            msg = (
                f"⚡ *PURE M5 SCALPER: BUY SIGNAL*\n\n"
                f"📌 *สินค้า:* Gold (XAUUSD)\n"
                f"📈 *คำสั่ง:* BUY\n"
                f"🎯 *Entry:* `{entry_price}`\n"
                f"🛑 *SL:* `{sl_price}`\n"
                f"🎯 *TP:* `{tp_price}`\n\n"
                f"💡 *Setup:* M5 Sweep Low + Rejection/Engulfing\n"
                f"⏰ _Timeframe: M5 | Pure Price Action_"
            )
            send_telegram(msg)
            print("Sent Aggressive Buy Signal!")

        # 🔴 SELL SIGNAL: กวาด High + เกิด Rejection / Engulfing
        is_sweep_high = c_high > swing_high
        is_bearish_action = (c_close < c_open and c_close < p_open) or (upper_wick >= body * 1.2)

        if is_sweep_high and is_bearish_action:
            sl_price = round(c_high + 0.50, 2)
            tp_price = round(entry_price - (abs(sl_price - entry_price) * 1.5), 2)

            msg = (
                f"⚡ *PURE M5 SCALPER: SELL SIGNAL*\n\n"
                f"📌 *สินค้า:* Gold (XAUUSD)\n"
                f"📉 *คำสั่ง:* SELL\n"
                f"🎯 *Entry:* `{entry_price}`\n"
                f"🛑 *SL:* `{sl_price}`\n"
                f"🎯 *TP:* `{tp_price}`\n\n"
                f"💡 *Setup:* M5 Sweep High + Rejection/Engulfing\n"
                f"⏰ _Timeframe: M5 | Pure Price Action_"
            )
            send_telegram(msg)
            print("Sent Aggressive Sell Signal!")

    except Exception as e:
        print(f"Error scanning Pure M5 Setup: {e}")

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Pure M5 Aggressive Bot is starting...")
    send_telegram("🚀 *ระบบสแกน M5 Pure Aggressive (ปลดล็อกเงื่อนไขความเสี่ยง) พร้อมทำงานแล้ว!*")
    
    while True:
        try:
            scan_m5_pure()
        except Exception as e:
            print(f"Main Loop Error: {e}")
        sleep(CHECK_INTERVAL)

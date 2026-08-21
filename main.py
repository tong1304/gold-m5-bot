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
    return "XM Standard $50 - Pure Babyforex Price Action Bot is Live!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
SYMBOL = "GC=F"       # สัญลักษณ์มาตรฐานทองคำบน Yahoo Finance
TIMEFRAME = "1m"
CHECK_INTERVAL = 90   # 90 วินาที ป้องกัน Rate Limit

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

# --- 3. NEWS FILTER (30 Mins) ---
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

# --- 4. BABYFOREX PURE PRICE ACTION SCANNER ---
def scan_babyforex_setup():
    print("Scanning Babyforex M1 Pure Price Action...")
    
    if check_high_impact_news(buffer_minutes=30):
        print("⏭️ Skipped due to USD High-Impact News Buffer.")
        return

    try:
        # ใช้ yf.download ดึงข้อมูลโดยตรงสำหรับ GC=F
        df = yf.download(tickers=SYMBOL, period="1d", interval=TIMEFRAME, progress=False)
        
        if df.empty or len(df) < 25:
            return

        # คำนวณ Swing High / Low ล่าสุด (Lookback 10 แท่ง M1)
        df['Swing_High'] = df['High'].shift(2).rolling(window=10).max()
        df['Swing_Low'] = df['Low'].shift(2).rolling(window=10).min()

        # แท่งล่าสุดที่เพิ่งปิด (-2)
        c_close = df['Close'].iloc[-2]
        c_open = df['Open'].iloc[-2]
        c_high = df['High'].iloc[-2]
        c_low = df['Low'].iloc[-2]

        # แท่งก่อนหน้า (-3)
        p_close = df['Close'].iloc[-3]
        p_open = df['Open'].iloc[-3]

        swing_high = df['Swing_High'].iloc[-2]
        swing_low = df['Swing_Low'].iloc[-2]

        # คำนวณลักษณะองค์ประกอบของแท่งเทียน
        body = abs(c_close - c_open)
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)
        
        entry_price = round(c_close, 2)

        # 🟢 BUY SETUP: Sweep Low + Rejection Pinbar / Engulfing
        is_sweep_low = c_low < swing_low
        is_bullish_engulfing = (c_close > c_open) and (c_close > p_open) and (c_close > p_close)
        is_pinbar_rejection = (lower_wick >= body * 1.5) and (c_close > c_open)

        if is_sweep_low and (is_bullish_engulfing or is_pinbar_rejection):
            sl_price = round(c_low - 0.40, 2)
            sl_distance = round((entry_price - sl_price), 2)
            
            # กรองเฉพาะจุดเข้าที่ SL ไม่เกิน 120 จุด ($1.20) เพื่อพอร์ต $50
            if 0.50 <= sl_distance <= 1.20:
                tp_price = round(entry_price + (sl_distance * 1.5), 2)

                msg = (
                    f"🔥 *BABYFOREX STYLE: M1 BUY REJECTION*\n\n"
                    f"📌 *สินค้า:* Gold (XAUUSD / GC=F)\n"
                    f"📈 *คำสั่ง:* BUY\n"
                    f"🎯 *Entry:* `{entry_price}`\n"
                    f"🛑 *SL:* `{sl_price}` (-${sl_distance})\n"
                    f"🎯 *TP:* `{tp_price}` (+${round(sl_distance * 1.5, 2)})\n\n"
                    f"💡 *Setup:* แท่ง M1 เจาะแนวรับหลอก + ทิ้งไส้ดีดกลับ\n"
                    f"⚠️ *XM Standard $50:* ออกออเดอร์ **0.01 Lot** เท่านั้น\n"
                    f"⏰ _Timeframe: M1 | Risk: Safe_"
                )
                send_telegram(msg)
                print("Sent Babyforex Buy Signal!")

        # 🔴 SELL SETUP: Sweep High + Rejection Pinbar / Engulfing
        is_sweep_high = c_high > swing_high
        is_bearish_engulfing = (c_close < c_open) and (c_close < p_open) and (c_close < p_close)
        is_pinbar_sell = (upper_wick >= body * 1.5) and (c_close < c_open)

        if is_sweep_high and (is_bearish_engulfing or is_pinbar_sell):
            sl_price = round(c_high + 0.40, 2)
            sl_distance = round((sl_price - entry_price), 2)

            if 0.50 <= sl_distance <= 1.20:
                tp_price = round(entry_price - (sl_distance * 1.5), 2)

                msg = (
                    f"🔥 *BABYFOREX STYLE: M1 SELL REJECTION*\n\n"
                    f"📌 *สินค้า:* Gold (XAUUSD / GC=F)\n"
                    f"📉 *คำสั่ง:* SELL\n"
                    f"🎯 *Entry:* `{entry_price}`\n"
                    f"🛑 *SL:* `{sl_price}` (-${sl_distance})\n"
                    f"🎯 *TP:* `{tp_price}` (+${round(sl_distance * 1.5, 2)})\n\n"
                    f"💡 *Setup:* แท่ง M1 เจาะแนวต้านหลอก + ทิ้งไส้ตบลง\n"
                    f"⚠️ *XM Standard $50:* ออกออเดอร์ **0.01 Lot** เท่านั้น\n"
                    f"⏰ _Timeframe: M1 | Risk: Safe_"
                )
                send_telegram(msg)
                print("Sent Babyforex Sell Signal!")

    except Exception as e:
        print(f"Error scanning Babyforex Setup: {e}")

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Babyforex Scalper Bot is starting...")
    send_telegram("🚀 *ระบบสแกน Babyforex M1 (ใช้ข้อมูล GC=F) เชื่อมต่อสำเร็จและเริ่มทำงานแล้ว!*")
    
    while True:
        try:
            scan_babyforex_setup()
        except Exception as e:
            print(f"Main Loop Error: {e}")
        sleep(CHECK_INTERVAL)

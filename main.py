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
    return "XM Standard $50 - High-WinRate M5 Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
SYMBOL = "GC=F"
TIMEFRAME = "5m"
CHECK_INTERVAL = 120  # สแกนทุก 2 นาที

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

# --- 4. HIGH CONFLUENCE M5 SCANNER ---
def scan_m5_setup():
    print("Scanning M5 High-Confluence Setup...")
    
    if check_high_impact_news(buffer_minutes=30):
        print("⏭️ Skipped due to USD High-Impact News Buffer.")
        return

    try:
        df = yf.download(tickers=SYMBOL, period="5d", interval=TIMEFRAME, progress=False)
        if df.empty or len(df) < 50:
            return

        # คำนวณ EMA 200 เพื่อระบุเทรนด์หลัก
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # คำนวณ Swing High/Low ย้อนหลัง 20 แท่ง M5
        df['Swing_High'] = df['High'].shift(2).rolling(window=20).max()
        df['Swing_Low'] = df['Low'].shift(2).rolling(window=20).min()

        c_close = df['Close'].iloc[-2]
        c_open = df['Open'].iloc[-2]
        c_high = df['High'].iloc[-2]
        c_low = df['Low'].iloc[-2]
        ema200 = df['EMA200'].iloc[-2]

        swing_high = df['Swing_High'].iloc[-2]
        swing_low = df['Swing_Low'].iloc[-2]

        body = abs(c_close - c_open)
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)

        entry_price = round(c_close, 2)

        # 🟢 BUY SETUP: เทรนด์หลักเป็นขาขึ้น (ราคา > EMA200) + กวาด Liquidity Low + Rejection
        is_uptrend = c_close > ema200
        is_sweep_low = c_low < swing_low
        is_bullish_rejection = (c_close > c_open) and (lower_wick >= body * 1.5)

        if is_uptrend and is_sweep_low and is_bullish_reversal:
            sl_price = round(c_low - 0.50, 2)
            sl_distance = round((entry_price - sl_price), 2)

            if 0.80 <= sl_distance <= 1.50:
                tp_price = round(entry_price + (sl_distance * 1.5), 2)

                msg = (
                    f"🎯 *M5 HIGH-WINRATE SIGNAL: BUY*\n\n"
                    f"📌 *สินค้า:* Gold (XAUUSD)\n"
                    f"📈 *คำสั่ง:* BUY (ตามเทรนด์หลัก M5/EMA200)\n"
                    f"🎯 *Entry:* `{entry_price}`\n"
                    f"🛑 *SL:* `{sl_price}` (-${sl_distance})\n"
                    f"🎯 *TP:* `{tp_price}` (+${round(sl_distance * 1.5, 2)})\n\n"
                    f"💡 *Setup:* Sweep Liquidity + EMA200 Confluence\n"
                    f"⚠️ *XM Standard $50:* ออกออเดอร์ **0.01 Lot** เท่านั้น\n"
                    f"⏰ _Timeframe: M5_"
                )
                send_telegram(msg)
                print("Sent M5 Buy Signal!")

        # 🔴 SELL SETUP: เทรนด์หลักเป็นขาลง (ราคา < EMA200) + กวาด Liquidity High + Rejection
        is_downtrend = c_close < ema200
        is_sweep_high = c_high > swing_high
        is_bearish_rejection = (c_close < c_open) and (upper_wick >= body * 1.5)

        if is_downtrend and is_sweep_high and is_bearish_rejection:
            sl_price = round(c_high + 0.50, 2)
            sl_distance = round((sl_price - entry_price), 2)

            if 0.80 <= sl_distance <= 1.50:
                tp_price = round(entry_price - (sl_distance * 1.5), 2)

                msg = (
                    f"🎯 *M5 HIGH-WINRATE SIGNAL: SELL*\n\n"
                    f"📌 *สินค้า:* Gold (XAUUSD)\n"
                    f"📉 *คำสั่ง:* SELL (ตามเทรนด์หลัก M5/EMA200)\n"
                    f"🎯 *Entry:* `{entry_price}`\n"
                    f"🛑 *SL:* `{sl_price}` (-${sl_distance})\n"
                    f"🎯 *TP:* `{tp_price}` (+${round(sl_distance * 1.5, 2)})\n\n"
                    f"💡 *Setup:* Sweep Liquidity + EMA200 Confluence\n"
                    f"⚠️ *XM Standard $50:* ออกออเดอร์ **0.01 Lot** เท่านั้น\n"
                    f"⏰ _Timeframe: M5_"
                )
                send_telegram(msg)
                print("Sent M5 Sell Signal!")

    except Exception as e:
        print(f"Error scanning M5 Setup: {e}")

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("M5 High-Confluence Bot is starting...")
    send_telegram("🚀 *ระบบสแกน M5 High-Confluence (EMA200 + Sweep) พร้อมทำงานแล้ว!*")
    
    while True:
        try:
            scan_m5_setup()
        except Exception as e:
            print(f"Main Loop Error: {e}")
        sleep(CHECK_INTERVAL)

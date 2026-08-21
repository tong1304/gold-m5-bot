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
    return "XM Standard $50 - M5 Statistical Bot is Live!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
SYMBOL = "GC=F"
TIMEFRAME = "5m"
CHECK_INTERVAL = 120      # สแกนทุก 2 นาที
WINRATE_THRESHOLD = 0.70  # กรองเฉพาะ Setup ที่สถิตีย้อนหลังชนะเกิน 70%

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

# --- 4. STATISTICAL BACKTEST ENGINE ---
def calculate_pattern_winrate(df, signal_type, sl_pips=1.0, tp_pips=1.5):
    """ ค้นหาพฤติกรรมย้อนหลังใน DataFrame แล้วคำนวณ Win Rate """
    total_trades = 0
    wins = 0

    # วนลูปเช็กข้อมูลย้อนหลัง (เว้น 20 แท่งล่าสุดไว้เป็นปัจจุบัน)
    for i in range(30, len(df) - 10):
        c_close = df['Close'].iloc[i]
        c_open = df['Open'].iloc[i]
        c_high = df['High'].iloc[i]
        c_low = df['Low'].iloc[i]
        swing_low = df['Low'].iloc[i-15:i].min()
        swing_high = df['High'].iloc[i-15:i].max()

        body = abs(c_close - c_open)
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)

        # ตรวจหา Pattern ในอดีต
        match = False
        if signal_type == "BUY" and (c_low < swing_low) and (lower_wick >= body * 1.5):
            match = True
            entry = c_close
            sl = entry - sl_pips
            tp = entry + tp_pips

        elif signal_type == "SELL" and (c_high > swing_high) and (upper_wick >= body * 1.5):
            match = True
            entry = c_close
            sl = entry + sl_pips
            tp = entry - tp_pips

        # หากเจอ Pattern เดียวกันในอดีต ให้ดูว่าอีก 10 แท่งถัดมา ชน TP หรือ SL ก่อน
        if match:
            total_trades += 1
            future_bars = df.iloc[i+1:i+10]
            
            for _, bar in future_bars.iterrows():
                if signal_type == "BUY":
                    if bar['Low'] <= sl:
                        break  # Loss
                    if bar['High'] >= tp:
                        wins += 1; break  # Win
                elif signal_type == "SELL":
                    if bar['High'] >= sl:
                        break  # Loss
                    if bar['Low'] <= tp:
                        wins += 1; break  # Win

    if total_trades < 5:  # สถิติน้อยเกินไป ไม่นับ
        return 0.0, 0

    winrate = wins / total_trades
    return winrate, total_trades

# --- 5. STATISTICAL SCANNER ---
def scan_statistical_m5():
    print("Analyzing Historical Statistics for M5 Pattern...")
    
    if check_high_impact_news(buffer_minutes=30):
        print("⏭️ Skipped due to USD High-Impact News Buffer.")
        return

    try:
        # ดึงข้อมูลย้อนหลัง 7 วันเพื่อทำ Statistical Backtest
        df = yf.download(tickers=SYMBOL, period="7d", interval=TIMEFRAME, progress=False)
        
        if df.empty or len(df) < 200:
            return

        df['Swing_High'] = df['High'].shift(2).rolling(window=15).max()
        df['Swing_Low'] = df['Low'].shift(2).rolling(window=15).min()

        c_close = df['Close'].iloc[-2]
        c_open = df['Open'].iloc[-2]
        c_high = df['High'].iloc[-2]
        c_low = df['Low'].iloc[-2]

        swing_high = df['Swing_High'].iloc[-2]
        swing_low = df['Swing_Low'].iloc[-2]

        body = abs(c_close - c_open)
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)

        entry_price = round(c_close, 2)

        # 🟢 CHECK BUY PATTERN CURRENTLY
        if (c_low < swing_low) and (lower_wick >= body * 1.5):
            winrate, samples = calculate_pattern_winrate(df, "BUY", sl_pips=1.0, tp_pips=1.5)
            
            if winrate >= WINRATE_THRESHOLD:
                sl_price = round(entry_price - 1.00, 2)
                tp_price = round(entry_price + 1.50, 2)

                msg = (
                    f"📊 *STATISTICAL MODEL: BUY SIGNAL (M5)*\n\n"
                    f"📌 *สินค้า:* Gold (XAUUSD)\n"
                    f"📈 *คำสั่ง:* BUY\n"
                    f"🎯 *Entry:* `{entry_price}`\n"
                    f"🛑 *SL:* `{sl_price}` (-$1.00)\n"
                    f"🎯 *TP:* `{tp_price}` (+$1.50)\n\n"
                    f"📈 *ผลวิเคราะห์สถิติย้อนหลัง (Historical Probability):*\n"
                    f"• *Win Rate ในอดีต:* `{round(winrate * 100, 1)}%`\n"
                    f"• *จำนวนตัวอย่างที่เคยเกิด:* {samples} ครั้ง\n\n"
                    f"⚠️ *XM Standard $50:* ออกออเดอร์ **0.01 Lot** เท่านั้น\n"
                    f"⏰ _Timeframe: M5_"
                )
                send_telegram(msg)
                print(f"Sent Buy Signal with {round(winrate*100, 1)}% Historical Win Rate!")

        # 🔴 CHECK SELL PATTERN CURRENTLY
        if (c_high > swing_high) and (upper_wick >= body * 1.5):
            winrate, samples = calculate_pattern_winrate(df, "SELL", sl_pips=1.0, tp_pips=1.5)
            
            if winrate >= WINRATE_THRESHOLD:
                sl_price = round(entry_price + 1.00, 2)
                tp_price = round(entry_price - 1.50, 2)

                msg = (
                    f"📊 *STATISTICAL MODEL: SELL SIGNAL (M5)*\n\n"
                    f"📌 *สินค้า:* Gold (XAUUSD)\n"
                    f"📉 *คำสั่ง:* SELL\n"
                    f"🎯 *Entry:* `{entry_price}`\n"
                    f"🛑 *SL:* `{sl_price}` (-$1.00)\n"
                    f"🎯 *TP:* `{tp_price}` (+$1.50)\n\n"
                    f"📈 *ผลวิเคราะห์สถิติย้อนหลัง (Historical Probability):*\n"
                    f"• *Win Rate ในอดีต:* `{round(winrate * 100, 1)}%`\n"
                    f"• *จำนวนตัวอย่างที่เคยเกิด:* {samples} ครั้ง\n\n"
                    f"⚠️ *XM Standard $50:* ออกออเดอร์ **0.01 Lot** เท่านั้น\n"
                    f"⏰ _Timeframe: M5_"
                )
                send_telegram(msg)
                print(f"Sent Sell Signal with {round(winrate*100, 1)}% Historical Win Rate!")

    except Exception as e:
        print(f"Error scanning Statistical M5: {e}")

# --- 6. MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("M5 Statistical Bot is starting...")
    send_telegram("🚀 *ระบบสแกน M5 วิเคราะห์สถิติมุมมองย้อนหลัง (Historical Backtest Model) เริ่มทำงานแล้ว!*")
    
    while True:
        try:
            scan_statistical_m5()
        except Exception as e:
            print(f"Main Loop Error: {e}")
        sleep(CHECK_INTERVAL)

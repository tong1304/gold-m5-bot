import os
import requests
import pandas as pd
import yfinance as yf
from time import sleep
import threading
from flask import Flask
from datetime import datetime, timezone

# --- 1. DUMMY WEB SERVER (รันฟรีบน Render Web Service) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "XAUUSD M5 Scalper Bot is running live and free on Render!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
SYMBOL = "GC=F"         # Gold Futures / XAUUSD
TIMEFRAME = "5m"        # ไทม์เฟรม 5 นาที
CHECK_INTERVAL = 60     # สแกนทุก 1 นาที (เช็กความไวสำหรับ M5)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

# --- 3. NEWS FILTER SYSTEM (เช็กข่าว USD) ---
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
                        print(f"⚠️ Gold News Warning: {event.get('title')} in {round(time_diff)} mins!")
                        return True
    except Exception as e:
        print(f"News Filter Error: {e}")
        return False
    return False

# --- 4. SUPERTREND CALCULATION ---
def calculate_supertrend(df, period=10, multiplier=3):
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # ATR Calculation
    price_diff1 = high - low
    price_diff2 = abs(high - close.shift(1))
    price_diff3 = abs(low - close.shift(1))
    tr = pd.concat([price_diff1, price_diff2, price_diff3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    
    # Basic Upper/Lower Bands
    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    final_upper = pd.Series(0.0, index=df.index)
    final_lower = pd.Series(0.0, index=df.index)
    supertrend = pd.Series(0.0, index=df.index)
    direction = pd.Series(1, index=df.index)
    
    for i in range(1, len(df)):
        if basic_upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]
            
        if basic_lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]
            
        if supertrend.iloc[i-1] == final_upper.iloc[i-1]:
            if close.iloc[i] > final_upper.iloc[i]:
                direction.iloc[i] = 1
            else:
                direction.iloc[i] = -1
        else:
            if close.iloc[i] < final_lower.iloc[i]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = 1
                
        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
        
    return supertrend, direction

# --- 5. SCANNER FUNCTION ---
def scan_gold_m5():
    print(f"Scanning Gold (XAUUSD) M5 Scalping Setup...")
    
    if check_high_impact_news():
        print("⏭️ Skipped Gold M5 scanning due to USD High-Impact News Buffer.")
        return

    try:
        df = yf.download(tickers=SYMBOL, period="2d", interval=TIMEFRAME, progress=False)
        if df.empty or len(df) < 50:
            return

        # Indicators
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['Vol_SMA20'] = df['Volume'].rolling(window=20).mean()
        df['Supertrend'], df['ST_Dir'] = calculate_supertrend(df)

        # ATR 14 Dynamic Risk
        high_low = df['High'] - df['Low']
        high_cp = (df['High'] - df['Close'].shift(1)).abs()
        low_cp = (df['Low'] - df['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=14).mean()

        # Last closed candle (-2) & previous (-3)
        close_price = df['Close'].iloc[-2]
        
        prev_ema9 = df['EMA9'].iloc[-3]
        prev_ema21 = df['EMA21'].iloc[-3]
        curr_ema9 = df['EMA9'].iloc[-2]
        curr_ema21 = df['EMA21'].iloc[-2]

        st_direction = df['ST_Dir'].iloc[-2]
        curr_volume = df['Volume'].iloc[-2]
        avg_volume = df['Vol_SMA20'].iloc[-2]
        atr_val = df['ATR'].iloc[-2]

        entry_price = round(close_price, 2)
        sl_distance = atr_val * 1.5
        tp_distance = sl_distance * 1.5  # RR 1:1.5 สำหรับ Scalping M5

        # 🟢 BUY SIGNAL (EMA9 ตัดขึ้น 21 + Supertrend ขาขึ้น + Volume ซื้อแน่น)
        if (prev_ema9 <= prev_ema21 and curr_ema9 > curr_ema21) and \
           (st_direction == 1) and \
           (curr_volume > avg_volume):

            sl_price = round(entry_price - sl_distance, 2)
            tp_price = round(entry_price + tp_distance, 2)

            msg = (
                f"⚡ *GOLD (XAUUSD) M5 FAST BUY SIGNAL*\n\n"
                f"📌 *สินค้า:* Gold (XAUUSD)\n"
                f"📈 *คำสั่ง:* BUY\n"
                f"🎯 *Entry:* `{entry_price}`\n"
                f"🛑 *Stop Loss:* `{sl_price}`\n"
                f"🎯 *Take Profit:* `{tp_price}`\n\n"
                f"📊 *เงื่อนไข:* EMA9/21 Cross + Supertrend Up + High Volume\n"
                f"⏰ _Timeframe: M5 | RR: 1:1.5_"
            )
            send_telegram(msg)
            print("Sent Gold M5 Buy Signal!")

        # 🔴 SELL SIGNAL (EMA9 ตัดลง 21 + Supertrend ขาลง + Volume ขายแน่น)
        elif (prev_ema9 >= prev_ema21 and curr_ema9 < curr_ema21) and \
             (st_direction == -1) and \
             (curr_volume > avg_volume):

            sl_price = round(entry_price + sl_distance, 2)
            tp_price = round(entry_price - tp_distance, 2)

            msg = (
                f"⚡ *GOLD (XAUUSD) M5 FAST SELL SIGNAL*\n\n"
                f"📌 *สินค้า:* Gold (XAUUSD)\n"
                f"📉 *คำสั่ง:* SELL\n"
                f"🎯 *Entry:* `{entry_price}`\n"
                f"🛑 *Stop Loss:* `{sl_price}`\n"
                f"🎯 *Take Profit:* `{tp_price}`\n\n"
                f"📊 *เงื่อนไข:* EMA9/21 Cross + Supertrend Down + High Volume\n"
                f"⏰ _Timeframe: M5 | RR: 1:1.5_"
            )
            send_telegram(msg)
            print("Sent Gold M5 Sell Signal!")

    except Exception as e:
        print(f"Error scanning Gold M5: {e}")

# --- 6. MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Gold M5 Scalper Bot is starting...")
    send_telegram("🏆 *บอทสแกนทองคำระยะสั้น M5 (Gold Scalper) เริ่มทำงานแล้ว!*")
    
    while True:
        try:
            scan_gold_m5()
        except Exception as e:
            print(f"Main Loop Error: {e}")
        sleep(CHECK_INTERVAL)

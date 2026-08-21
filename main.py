import os
import requests
import pandas as pd
import yfinance as yf
from time import sleep
import threading
from flask import Flask
from datetime import datetime, timezone

# --- 1. DUMMY WEB SERVER (รันฟรีบน Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "XM Standard $50 Gold M1 Trap Bot is running live!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
SYMBOL = "GC=F"         # Gold Futures
TIMEFRAME = "1m"        # M1 ไทม์เฟรมสำหรับสแกนรอบไว
CHECK_INTERVAL = 60     # สแกนทุกๆ 1 นาที

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

# --- 3. NEWS FILTER (กรองข่าวแรง 30 นาที) ---
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
                        print(f"⚠️ News Buffer Active: {event.get('title')} in {round(time_diff)} mins!")
                        return True
    except Exception as e:
        print(f"News Filter Error: {e}")
        return False
    return False

# --- 4. SCANNER FUNCTION (M1 LIQUIDITY TRAP) ---
def scan_m1_trap():
    print("Scanning M1 Liquidity Trap Setup...")
    
    # 🛑 เช็กข่าวแรงก่อนวิเคราะห์
    if check_high_impact_news(buffer_minutes=30):
        print("⏭️ Skipped due to USD High-Impact News Buffer.")
        return

    try:
        df = yf.download(tickers=SYMBOL, period="1d", interval=TIMEFRAME, progress=False)
        if df.empty or len(df) < 30:
            return

        # คำนวณราคา High/Low ย้อนหลัง 15 แท่งเพื่อดู Liquidity Zone
        df['Swing_High_15'] = df['High'].shift(2).rolling(window=15).max()
        df['Swing_Low_15'] = df['Low'].shift(2).rolling(window=15).min()

        # แท่งก่อนหน้า (-2) และแท่งปัจจุบัน (-1)
        prev_close = df['Close'].iloc[-2]
        prev_open = df['Open'].iloc[-2]
        prev_high = df['High'].iloc[-2]
        prev_low = df['Low'].iloc[-2]
        
        swing_high = df['Swing_High_15'].iloc[-2]
        swing_low = df['Swing_Low_15'].iloc[-2]

        # คำนวณขนาดไส้เทียน
        body_size = abs(prev_close - prev_open)
        lower_wick = min(prev_open, prev_close) - prev_low
        upper_wick = prev_high - max(prev_open, prev_close)

        entry_price = round(prev_close, 2)

        # 🟢 BUY TRAP: ราคาทิ่มหลุด Swing Low เดิมแต่กลับตัวปิดเขียว/ทิ้งไส้ล่างยาว
        is_buy_sweep = (prev_low < swing_low) and (prev_close > swing_low)
        is_bullish_reversal = (prev_close > prev_open) or (lower_wick > (body_size * 1.5))

        if is_buy_sweep and is_bullish_reversal:
            # คำนวณ SL/TP แบบฟิกซ์แคบสำหรับ Standard Account ($50 Risk)
            sl_price = round(entry_price - 1.00, 2)  # SL แคบเพียง 100 จุด ($1.00)
            tp_price = round(entry_price + 1.20, 2)  # TP 120 จุด ($1.20) เพื่อข้ามค่า Spread XM

            msg = (
                f"⚡ *XM STANDARD $50: BUY TRAP SIGNAL (M1)*\n\n"
                f"📌 *สินค้า:* Gold (XAUUSD)\n"
                f"📈 *คำสั่ง:* BUY\n"
                f"🎯 *Entry:* `{entry_price}`\n"
                f"🛑 *SL:* `{sl_price}` (เสี่ยงประมาณ $1.00 ที่ 0.01 Lot)\n"
                f"🎯 *TP:* `{tp_price}`\n\n"
                f"💡 *คำแนะนำสำหรับ XM Standard ($50):*\n"
                f"• ควรใช้ Lot ขนาด **0.01** เท่านั้น\n"
                f"• กวาด Liquidity M1 เรียบร้อย ฟ้าบวกกดเก็บทันที!\n"
                f"🛡️ *News Status:* Safe (No USD News Buffer)\n"
                f"⏰ _Timeframe: M1_"
            )
            send_telegram(msg)
            print("Sent M1 Buy Trap Signal!")

        # 🔴 SELL TRAP: ราคาดันทะลุ Swing High เดิมแต่เจอตบกลับปิดแดง/ทิ้งไส้บนยาว
        is_sell_sweep = (prev_high > swing_high) and (prev_close < swing_high)
        is_bearish_reversal = (prev_close < prev_open) or (upper_wick > (body_size * 1.5))

        if is_sell_sweep and is_bearish_reversal:
            sl_price = round(entry_price + 1.00, 2)  # SL แคบเพียง 100 จุด ($1.00)
            tp_price = round(entry_price - 1.20, 2)  # TP 120 จุด ($1.20)

            msg = (
                f"⚡ *XM STANDARD $50: SELL TRAP SIGNAL (M1)*\n\n"
                f"📌 *สินค้า:* Gold (XAUUSD)\n"
                f"📉 *คำสั่ง:* SELL\n"
                f"🎯 *Entry:* `{entry_price}`\n"
                f"🛑 *SL:* `{sl_price}` (เสี่ยงประมาณ $1.00 ที่ 0.01 Lot)\n"
                f"🎯 *TP:* `{tp_price}`\n\n"
                f"💡 *คำแนะนำสำหรับ XM Standard ($50):*\n"
                f"• ควรใช้ Lot ขนาด **0.01** เท่านั้น\n"
                f"• กวาด Liquidity M1 เรียบร้อย ฟ้าบวกกดเก็บทันที!\n"
                f"🛡️ *News Status:* Safe (No USD News Buffer)\n"
                f"⏰ _Timeframe: M1_"
            )
            send_telegram(msg)
            print("Sent M1 Sell Trap Signal!")

    except Exception as e:
        print(f"Error scanning M1 Trap: {e}")

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("XM Standard $50 Bot is starting...")
    send_telegram("🚀 *บอทสแกนทอง M1 Liquidity Trap (สำหรับ XM Standard $50) เริ่มทำงานแล้ว!*")
    
    while True:
        try:
            scan_m1_trap()
        except Exception as e:
            print(f"Main Loop Error: {e}")
        sleep(CHECK_INTERVAL)

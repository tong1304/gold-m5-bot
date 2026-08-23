import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")
DEFAULT_DB = os.getenv("SIGNAL_HISTORY_DB", "signal_history.db")


class SignalHistory:
    def __init__(self, path=DEFAULT_DB):
        self.path = path
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    candle_time TEXT,
                    created_at TEXT NOT NULL,
                    entry REAL,
                    sl REAL,
                    tp REAL,
                    risk_reward REAL,
                    result TEXT NOT NULL DEFAULT 'OPEN',
                    r_multiple REAL,
                    resolved_at TEXT,
                    telegram_sent INTEGER NOT NULL DEFAULT 1,
                    payload_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_result ON signals(result)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")

    def record_signal(self, signal):
        levels = signal.get("trade_levels") or {}
        signal_id = str(signal.get("signal_id") or "").strip()
        if not signal_id or signal.get("signal") not in ("BUY", "SELL"):
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO signals
                (signal_id, symbol, direction, candle_time, created_at, entry, sl, tp, risk_reward, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id,
                str(signal.get("symbol", "")),
                str(signal.get("signal")),
                str(signal.get("closed_candle", "")),
                now,
                _num(levels.get("entry")),
                _num(levels.get("sl")),
                _num(levels.get("tp")),
                _num(levels.get("risk_reward")),
                json.dumps(signal, ensure_ascii=False, default=str),
            ))
            return conn.total_changes > 0

    def set_result(self, signal_id, result, r_multiple, resolved_at=None):
        result = str(result).upper()
        if result not in ("WIN", "LOSS", "AMBIGUOUS", "EXPIRED"):
            raise ValueError("invalid signal result")
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE signals SET result=?, r_multiple=?, resolved_at=?
                WHERE signal_id=? AND result='OPEN'
            """, (result, _num(r_multiple), resolved_at or datetime.now(timezone.utc).isoformat(), signal_id))

    def pending(self, limit=200):
        with self._lock, self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM signals WHERE result='OPEN' ORDER BY created_at ASC LIMIT ?", (int(limit),)
            ).fetchall()]

    def evaluate_candles(self, signal_id, candles):
        row = self.get(signal_id)
        if not row or row["result"] != "OPEN":
            return row
        entry, sl, tp = row["entry"], row["sl"], row["tp"]
        direction = row["direction"]
        candle_time = _parse_dt(row["candle_time"])
        for candle in candles:
            dt = _parse_dt(candle.get("datetime"))
            if candle_time and dt and dt <= candle_time:
                continue
            high, low = _num(candle.get("high")), _num(candle.get("low"))
            if high is None or low is None:
                continue
            if direction == "BUY":
                hit_sl, hit_tp = low <= sl, high >= tp
                if hit_sl and hit_tp:
                    self.set_result(signal_id, "AMBIGUOUS", 0.0, str(candle.get("datetime")))
                    break
                if hit_tp:
                    self.set_result(signal_id, "WIN", _rr(entry, sl, tp), str(candle.get("datetime")))
                    break
                if hit_sl:
                    self.set_result(signal_id, "LOSS", -1.0, str(candle.get("datetime")))
                    break
            else:
                hit_sl, hit_tp = high >= sl, low <= tp
                if hit_sl and hit_tp:
                    self.set_result(signal_id, "AMBIGUOUS", 0.0, str(candle.get("datetime")))
                    break
                if hit_tp:
                    self.set_result(signal_id, "WIN", _rr(entry, sl, tp), str(candle.get("datetime")))
                    break
                if hit_sl:
                    self.set_result(signal_id, "LOSS", -1.0, str(candle.get("datetime")))
                    break
        return self.get(signal_id)

    def get(self, signal_id):
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE signal_id=?", (signal_id,)).fetchone()
            return dict(row) if row else None

    def list_signals(self, days=30, symbol=None, result=None, limit=200):
        days = max(0, min(int(days), 3650))
        where = ["created_at >= datetime('now', ?)"]
        params = [f"-{days} days"]
        if symbol and symbol.upper() in ("BTC", "GOLD"):
            where.append("symbol=?"); params.append(symbol.upper())
        if result and result.upper() in ("OPEN", "WIN", "LOSS", "AMBIGUOUS", "EXPIRED"):
            where.append("result=?"); params.append(result.upper())
        params.append(max(1, min(int(limit), 1000)))
        query = f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?"
        with self._lock, self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def statistics(self, days=30, symbol=None):
        rows = self.list_signals(days=days, symbol=symbol, limit=10000)
        wins = sum(r["result"] == "WIN" for r in rows)
        losses = sum(r["result"] == "LOSS" for r in rows)
        open_ = sum(r["result"] == "OPEN" for r in rows)
        ambiguous = sum(r["result"] == "AMBIGUOUS" for r in rows)
        decided = wins + losses
        net_r = round(sum(float(r["r_multiple"] or 0) for r in rows if r["result"] in ("WIN", "LOSS")), 4)
        win_rate = round((wins / decided) * 100, 2) if decided else 0.0
        return {"period_days": days, "symbol": symbol or "ALL", "total": len(rows), "wins": wins,
                "losses": losses, "open": open_, "ambiguous": ambiguous, "decided": decided,
                "win_rate": win_rate, "net_r": net_r, "rows": rows}


def _num(value):
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _rr(entry, sl, tp):
    risk = abs(float(entry) - float(sl))
    reward = abs(float(tp) - float(entry))
    return round(reward / risk, 4) if risk else 0.0


def _parse_dt(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


history = SignalHistory()

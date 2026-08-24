import json,os,sqlite3,threading
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
BANGKOK=ZoneInfo("Asia/Bangkok"); DEFAULT_DB=os.getenv("SIGNAL_HISTORY_DB","signal_history.db")
class SignalHistory:
    def __init__(self,path=DEFAULT_DB):
        self.path=os.path.abspath(os.path.expanduser(path)); parent=os.path.dirname(self.path)
        if parent:os.makedirs(parent,exist_ok=True)
        self._lock=threading.RLock(); self._init_db()
    def _connect(self):
        conn=sqlite3.connect(self.path,timeout=30,isolation_level="DEFERRED"); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA busy_timeout=30000"); conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA synchronous=NORMAL"); return conn
    def _init_db(self):
        with self._lock,self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS signals (signal_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,direction TEXT NOT NULL,candle_time TEXT,created_at TEXT NOT NULL,entry REAL,sl REAL,tp REAL,risk_reward REAL,result TEXT NOT NULL DEFAULT 'OPEN',r_multiple REAL,resolved_at TEXT,telegram_sent INTEGER NOT NULL DEFAULT 1,payload_json TEXT)")
            cols={r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()}
            if "setup_key" not in cols:conn.execute("ALTER TABLE signals ADD COLUMN setup_key TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC)"); conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_result ON signals(result)"); conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)"); conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_setup_key ON signals(setup_key,result)")
    def record_signal(self,signal):
        levels=signal.get("trade_levels") or {}; signal_id=str(signal.get("signal_id") or "").strip(); setup_key=str(signal.get("setup_key") or "").strip()
        if not signal_id or signal.get("signal") not in ("BUY","SELL"):return False
        created_at=str(signal.get("created_at") or datetime.now(timezone.utc).isoformat())
        with self._lock,self._connect() as conn:
            before=conn.total_changes
            conn.execute("INSERT OR IGNORE INTO signals (signal_id,symbol,direction,candle_time,created_at,entry,sl,tp,risk_reward,result,telegram_sent,payload_json,setup_key) VALUES (?,?,?,?,?,?,?,?,?,'OPEN',?,?,?)",(signal_id,str(signal.get("symbol","")),str(signal.get("signal")),str(signal.get("closed_candle",signal.get("candle_time",""))),created_at,_num(levels.get("entry")),_num(levels.get("sl")),_num(levels.get("tp")),_num(levels.get("risk_reward",levels.get("effective_rr"))),1,json.dumps(signal,ensure_ascii=False,default=str),setup_key))
            return conn.total_changes>before
    def active_for_symbol(self,symbol):
        symbol=str(symbol).upper()
        with self._lock,self._connect() as conn:return [dict(r) for r in conn.execute("SELECT * FROM signals WHERE symbol=? AND result='OPEN' ORDER BY created_at DESC",(symbol,)).fetchall()]
    def active_setup(self,setup_key):
        if not setup_key:return None
        with self._lock,self._connect() as conn:
            r=conn.execute("SELECT * FROM signals WHERE setup_key=? AND result='OPEN' ORDER BY created_at DESC LIMIT 1",(setup_key,)).fetchone(); return dict(r) if r else None
    def record_no_trade(self,signal):
        signal_id=str(signal.get("signal_id") or "").strip(); symbol=str(signal.get("symbol") or "").strip().upper(); candle_time=str(signal.get("closed_candle") or signal.get("candle_time") or "")
        if not signal_id or symbol not in ("BTC","GOLD") or not candle_time:return False
        reasons=signal.get("rejection_reasons") or []; reasons=reasons if isinstance(reasons,list) else [str(reasons)]; payload=dict(signal); payload.update({"signal":"NO_TRADE","result":"NO_TRADE","no_trade_reasons":[str(x) for x in reasons]}); created_at=str(signal.get("created_at") or datetime.now(timezone.utc).isoformat())
        with self._lock,self._connect() as conn:
            before=conn.total_changes; conn.execute("INSERT OR IGNORE INTO signals (signal_id,symbol,direction,candle_time,created_at,entry,sl,tp,risk_reward,result,r_multiple,resolved_at,telegram_sent,payload_json,setup_key) VALUES (?,?,'NO_TRADE',?,?,NULL,NULL,NULL,NULL,'NO_TRADE',NULL,?,0,?,NULL)",(signal_id,symbol,candle_time,created_at,candle_time,json.dumps(payload,ensure_ascii=False,default=str))); return conn.total_changes>before
    def set_result(self,signal_id,result,r_multiple,resolved_at=None):
        result=str(result).upper()
        if result not in ("WIN","LOSS","AMBIGUOUS","EXPIRED"):raise ValueError("invalid signal result")
        with self._lock,self._connect() as conn:conn.execute("UPDATE signals SET result=?,r_multiple=?,resolved_at=? WHERE signal_id=? AND result='OPEN'",(result,_num(r_multiple),resolved_at or datetime.now(timezone.utc).isoformat(),signal_id))
    def resolve_open_for_symbol(self,symbol,candles):
        rows=self.active_for_symbol(symbol); resolved=[]
        for row in rows:
            before=row.get("result"); after=self.evaluate_candles(row["signal_id"],candles)
            if before=="OPEN" and after and after.get("result")!="OPEN":resolved.append(after)
        return resolved
    def pending(self,limit=200):
        with self._lock,self._connect() as conn:return [dict(row) for row in conn.execute("SELECT * FROM signals WHERE result='OPEN' ORDER BY created_at ASC LIMIT ?",(int(limit),)).fetchall()]
    def evaluate_candles(self,signal_id,candles):
        row=self.get(signal_id)
        if not row or row["result"]!="OPEN":return row
        entry,sl,tp=row["entry"],row["sl"],row["tp"]; direction=row["direction"]; candle_time=_parse_dt(row["candle_time"])
        for candle in candles:
            dt=_parse_dt(candle.get("datetime"));
            if candle_time and dt and dt<=candle_time:continue
            high,low=_num(candle.get("high")),_num(candle.get("low"))
            if high is None or low is None:continue
            hit_sl=low<=sl if direction=="BUY" else high>=sl; hit_tp=high>=tp if direction=="BUY" else low<=tp
            if hit_sl and hit_tp:self.set_result(signal_id,"AMBIGUOUS",0.0,str(candle.get("datetime")));break
            if hit_tp:self.set_result(signal_id,"WIN",_rr(entry,sl,tp),str(candle.get("datetime")));break
            if hit_sl:self.set_result(signal_id,"LOSS",-1.0,str(candle.get("datetime")));break
        return self.get(signal_id)
    def get(self,signal_id):
        with self._lock,self._connect() as conn:
            row=conn.execute("SELECT * FROM signals WHERE signal_id=?",(signal_id,)).fetchone(); return dict(row) if row else None
    def list_signals(self,days=30,symbol=None,result=None,limit=200):
        days=max(0,min(int(days),3650)); where=["datetime(created_at)>=datetime('now',?)"]; params=[f"-{days} days"]
        if symbol and symbol.upper() in ("BTC","GOLD"):where.append("symbol=?");params.append(symbol.upper())
        allowed=("OPEN","WIN","LOSS","AMBIGUOUS","EXPIRED","NO_TRADE")
        if result and result.upper() in allowed:where.append("result=?");params.append(result.upper())
        params.append(max(1,min(int(limit),1000))); query=f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY datetime(created_at) DESC LIMIT ?"
        with self._lock,self._connect() as conn:return [dict(r) for r in conn.execute(query,params).fetchall()]
    def statistics(self,days=30,symbol=None):
        rows=self.list_signals(days,symbol,limit=10000); wins=sum(r["result"]=="WIN" for r in rows); losses=sum(r["result"]=="LOSS" for r in rows); open_=sum(r["result"]=="OPEN" for r in rows); no_trade=sum(r["result"]=="NO_TRADE" for r in rows); ambiguous=sum(r["result"]=="AMBIGUOUS" for r in rows); decided=wins+losses; net_r=round(sum(float(r["r_multiple"] or 0) for r in rows if r["result"] in ("WIN","LOSS")),4); return {"period_days":days,"symbol":symbol or "ALL","total":len(rows),"trade_count":wins+losses+open_+ambiguous,"no_trade":no_trade,"wins":wins,"losses":losses,"open":open_,"ambiguous":ambiguous,"decided":decided,"win_rate":round(wins/decided*100,2) if decided else 0.0,"net_r":net_r,"rows":rows}

def _num(value):
    try:value=float(value);return value if value==value and abs(value)!=float("inf") else None
    except (TypeError,ValueError):return None
def _rr(entry,sl,tp):
    risk=abs(float(entry)-float(sl));reward=abs(float(tp)-float(entry));return round(reward/risk,4) if risk else 0.0
def _parse_dt(value):
    if not value:return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"));return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError,ValueError):return None
history=SignalHistory()

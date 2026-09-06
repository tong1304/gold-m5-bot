from __future__ import annotations
import json, logging, os
from pathlib import Path
from threading import RLock
from typing import Any

logger=logging.getLogger(__name__); _LOCK=RLock(); _DEFAULT_PATH="./data/production_v2_opportunity_lifecycle.json"; _TABLE="production_v2_opportunity_lifecycle"; _LAST_ERROR:str|None=None

def _database_url()->str:return str(os.getenv("OPPORTUNITY_MEMORY_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
def _path()->Path:return Path(os.getenv("OPPORTUNITY_MEMORY_PATH",_DEFAULT_PATH)).expanduser()
def _postgres_enabled()->bool:return _database_url().lower().startswith(("postgres://","postgresql://"))
def backend()->str:return "POSTGRES" if _postgres_enabled() else "FILE"
def last_error()->str|None:
    with _LOCK:return _LAST_ERROR

def require_persistent_backend()->None:
    """Production guard: lifecycle continuity must survive process restart/deploy."""
    required=str(os.getenv("PRODUCTION_V2_REQUIRE_PERSISTENT_MEMORY","")).strip().lower() in {"1","true","yes","on"}
    if required and not _postgres_enabled():
        raise RuntimeError("Persistent opportunity memory is required in production; configure OPPORTUNITY_MEMORY_DATABASE_URL or DATABASE_URL with PostgreSQL")

def _record_error(exc:Exception,operation:str)->None:
    global _LAST_ERROR; _LAST_ERROR=f"{type(exc).__name__}: {exc}"; logger.exception("[PRODUCTION V2] OPPORTUNITY_MEMORY %s failed backend=%s",operation,backend())
def _clear_error()->None:
    global _LAST_ERROR; _LAST_ERROR=None

def _pg_connect():
    try: import psycopg
    except ImportError as exc: raise RuntimeError("PostgreSQL opportunity memory requires psycopg") from exc
    return psycopg.connect(_database_url(),autocommit=True)
def _ensure_postgres()->None:
    with _pg_connect() as conn:
        with conn.cursor() as cur:cur.execute(f"CREATE TABLE IF NOT EXISTS {_TABLE} (symbol TEXT PRIMARY KEY,state_json TEXT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
def _load_postgres()->dict[str,dict[str,Any]]:
    _ensure_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:cur.execute(f"SELECT symbol,state_json FROM {_TABLE}"); rows=cur.fetchall()
    out={}
    for symbol,state_json in rows:
        try: state=json.loads(state_json)
        except Exception as exc: logger.error("[PRODUCTION V2] invalid lifecycle state symbol=%s error=%s",symbol,exc); continue
        if isinstance(state,dict):out[str(symbol).upper()]=dict(state)
    return out

def _memory_summary(state:dict[str,Any])->str:
    opportunities=state.get("opportunities") if isinstance(state.get("opportunities"),dict) else {}
    directions=[]
    for direction in ("BUY","SELL"):
        item=opportunities.get(direction) if isinstance(opportunities.get(direction),dict) else {}
        if item:
            directions.append(f"{direction}:{item.get('state','IDLE')}:{item.get('opportunity_id')}")
    return ",".join(directions) or "NONE"

def load_all()->dict[str,dict[str,Any]]:
    with _LOCK:
        try:
            if _postgres_enabled():
                result=_load_postgres(); _clear_error(); return result
            path=_path()
            if not path.exists(): _clear_error(); return {}
            payload=json.loads(path.read_text(encoding="utf-8")); result={str(s).upper():dict(v) for s,v in payload.items() if isinstance(v,dict)} if isinstance(payload,dict) else {}; _clear_error(); return result
        except Exception as exc:
            _record_error(exc,"LOAD")
            if _postgres_enabled():raise RuntimeError("Configured PostgreSQL opportunity memory is unavailable") from exc
            return {}

def load(symbol:str)->dict[str,Any]:
    normalized=str(symbol or "UNKNOWN").upper()
    state=dict(load_all().get(normalized) or {})
    logger.info("[PRODUCTION V2] OPPORTUNITY_MEMORY_RESTORE symbol=%s backend=%s found=%s leader=%s active_directions=%s state=%s directions=%s",normalized,backend(),bool(state),state.get("leader"),state.get("active_directions"),state.get("state"),_memory_summary(state))
    return state

def save(symbol:str,state:dict[str,Any])->None:
    symbol=str(symbol or "UNKNOWN").upper()
    require_persistent_backend()
    with _LOCK:
        try:
            if _postgres_enabled():
                _ensure_postgres()
                with _pg_connect() as conn:
                    with conn.cursor() as cur:cur.execute(f"INSERT INTO {_TABLE} (symbol,state_json,updated_at) VALUES (%s,%s,NOW()) ON CONFLICT (symbol) DO UPDATE SET state_json=EXCLUDED.state_json,updated_at=NOW()",(symbol,json.dumps(dict(state),ensure_ascii=False,sort_keys=True)))
            else:
                path=_path(); path.parent.mkdir(parents=True,exist_ok=True); payload=load_all(); payload[symbol]=dict(state); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True),encoding="utf-8"); os.replace(tmp,path)
            _clear_error()
            logger.info("[PRODUCTION V2] OPPORTUNITY_MEMORY_PERSIST symbol=%s backend=%s leader=%s active_directions=%s state=%s directions=%s",symbol,backend(),state.get("leader"),state.get("active_directions"),state.get("state"),_memory_summary(state))
        except Exception as exc:_record_error(exc,"SAVE"); raise

def remove(symbol:str)->None:
    symbol=str(symbol or "UNKNOWN").upper()
    with _LOCK:
        try:
            if _postgres_enabled():
                _ensure_postgres()
                with _pg_connect() as conn:
                    with conn.cursor() as cur:cur.execute(f"DELETE FROM {_TABLE} WHERE symbol=%s",(symbol,))
            else:
                path=_path(); payload=load_all(); payload.pop(symbol,None); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True),encoding="utf-8"); os.replace(tmp,path)
            _clear_error()
        except Exception as exc:_record_error(exc,"REMOVE"); raise

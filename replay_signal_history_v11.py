"""CLI for the native V11 replay pipeline. No legacy engine imports."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
import pandas as pd
from v11 import replay
from live_scanner_v11 import _lse_frame

def main():
    p=argparse.ArgumentParser(); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--symbol",choices=["BTC","GOLD","ALL"],default="ALL"); p.add_argument("--dry-run",action="store_true"); args=p.parse_args()
    symbols=[args.symbol] if args.symbol!="ALL" else ["BTC","GOLD"]; reports=[]
    start=datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc); end=datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)+pd.Timedelta(days=1)
    for symbol in symbols:
        m5=_lse_frame(symbol,"5m",5000); m15=_lse_frame(symbol,"15m",5000)
        m5=m5[(m5.datetime>=start)&(m5.datetime<end)].reset_index(drop=True)
        if m5.empty:
            reports.append({"status":"no_data","symbol":symbol,"engine_version":"11.1-HARDENED"}); continue
        m15=m15[m15.datetime<=m5.iloc[-1].datetime].reset_index(drop=True)
        reports.append({**replay.replay_frames(m5,m15,symbol,limit=None),"start":args.start,"end":args.end,"dry_run":bool(args.dry_run)})
    return {"status":"dry-run" if args.dry_run else "completed","engine_version":"11.1-HARDENED","source":"LSE_HISTORICAL_OHLCV","symbols":symbols,"reports":reports,"live_orders_allowed":False}

if __name__=="__main__": print(json.dumps(main(),ensure_ascii=False,default=str))

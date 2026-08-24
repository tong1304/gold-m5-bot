from __future__ import annotations

import math
import pandas as pd

from .contracts import StrategyResult
from .common import atr14

GOLD_NEW_ENGINE_NAMES = {
    "G1": "LIQUIDITY_SWEEP_CHOCH",
    "G2": "CONTINUATION_FVG_PULLBACK",
    "G3": "SESSION_BREAKOUT_RETEST",
}
GOLD_NEW_ENGINE_MIN_RR = {"G1": 2.0, "G2": 2.0, "G3": 1.5}


def _n(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _body(c): return abs(_n(c.close) - _n(c.open))
def _rng(c): return max(_n(c.high) - _n(c.low), 1e-12)
def _bull(c): return _n(c.close) > _n(c.open)
def _bear(c): return _n(c.close) < _n(c.open)


def _atr(x):
    a = atr14(x).dropna() if x is not None and not x.empty else pd.Series(dtype=float)
    return _n(a.iloc[-1], 1.0) if len(a) else max(_n((x.high-x.low).tail(14).mean(), 1.0), 1e-12)


def _pivots(x, span=2):
    highs, lows = [], []
    for i in range(span, len(x)-span):
        h, l = _n(x.high.iloc[i]), _n(x.low.iloc[i])
        if h >= _n(x.high.iloc[i-span:i+span+1].max()): highs.append((i, h))
        if l <= _n(x.low.iloc[i-span:i+span+1].min()): lows.append((i, l))
    return highs, lows


def _fvg(x, i, direction):
    if i < 2: return None
    a, c = x.iloc[i-2], x.iloc[i]
    if direction == "BUY" and _n(c.low) > _n(a.high):
        return {"bottom": _n(a.high), "top": _n(c.low), "ce": (_n(a.high)+_n(c.low))/2, "index": i, "type": "BULLISH_FVG"}
    if direction == "SELL" and _n(c.high) < _n(a.low):
        return {"bottom": _n(c.high), "top": _n(a.low), "ce": (_n(a.low)+_n(c.high))/2, "index": i, "type": "BEARISH_FVG"}
    return None


def _latest_fvg(x, direction, start=2, end=None):
    end = len(x) if end is None else min(end, len(x))
    for i in range(end-1, max(start, 2)-1, -1):
        f = _fvg(x, i, direction)
        if f: return f
    return None


def _ob(x, direction, end):
    for i in range(end-1, max(0, end-8), -1):
        c = x.iloc[i]
        if direction == "BUY" and _bear(c): return {"low": _n(c.low), "high": _n(c.open), "index": i, "type": "BULLISH_OB"}
        if direction == "SELL" and _bull(c): return {"low": _n(c.open), "high": _n(c.high), "index": i, "type": "BEARISH_OB"}
    return None


def _result(strategy, direction, evidence, quality, entry_type):
    return StrategyResult.pass_(strategy, direction, evidence, quality, 0)


def _fail(strategy, direction, reason, evidence=None):
    return StrategyResult.fail(strategy, direction, [reason], evidence)


def _htf_ok(ctx, direction):
    bias = str(ctx.get("h1_bias") or "NEUTRAL").upper()
    m15 = str((ctx.get("m15") or {}).get("direction") or "NEUTRAL").upper()
    poi = ctx.get("h1_poi") or ctx.get("poi") or {}
    poi_dir = str(poi.get("direction") or poi.get("bias") or "NEUTRAL").upper() if isinstance(poi, dict) else "NEUTRAL"
    if bias in ("BUY", "SELL") and bias != direction and poi_dir != direction: return False
    if m15 in ("BUY", "SELL") and m15 != direction and poi_dir != direction: return False
    return True


def liquidity_sweep_choch(m5, direction, ctx):
    strategy = "LIQUIDITY_SWEEP_CHOCH"
    x = m5.tail(120).reset_index(drop=True); a = _atr(x)
    if len(x) < 30: return _fail(strategy, direction, "INSUFFICIENT_M5_CONTEXT")
    if not _htf_ok(ctx, direction): return _fail(strategy, direction, "HTF_POI_ALIGNMENT_FAILED")
    highs, lows = _pivots(x)
    if direction == "BUY":
        level = lows[-1][1] if lows else None
        sweep = next(((i, x.iloc[i]) for i in range(len(x)-2, max(2,len(x)-18), -1) if level is not None and _n(x.iloc[i].low) < level and _n(x.iloc[i].close) > level), None)
        if not sweep: return _fail(strategy, direction, "LIQUIDITY_SWEEP_FAILED")
        si, sc = sweep
        internal = [h for i,h in highs if i < si and h > level]
        if not internal: return _fail(strategy, direction, "NO_SWING_HIGH_FOR_CHOCH")
        choch_level = internal[-1]
        ci = next((i for i in range(si+1,len(x)) if _n(x.iloc[i].close) > choch_level and _bull(x.iloc[i])), None)
        if ci is None: return _fail(strategy, direction, "CHOCH_CLOSE_FAILED")
        fvg = _latest_fvg(x, direction, si+1, ci+1)
        if not fvg: return _fail(strategy, direction, "NO_FVG_NO_ENTRY")
        ob = _ob(x, direction, ci)
        entry = fvg["ce"]; sl = _n(sc.low) - .10*a
        target = max([v for _,v in highs if v > entry] or [entry + 3*a])
    else:
        level = highs[-1][1] if highs else None
        sweep = next(((i, x.iloc[i]) for i in range(len(x)-2, max(2,len(x)-18), -1) if level is not None and _n(x.iloc[i].high) > level and _n(x.iloc[i].close) < level), None)
        if not sweep: return _fail(strategy, direction, "LIQUIDITY_SWEEP_FAILED")
        si, sc = sweep
        internal = [l for i,l in lows if i < si and l < level]
        if not internal: return _fail(strategy, direction, "NO_SWING_LOW_FOR_CHOCH")
        choch_level = internal[-1]
        ci = next((i for i in range(si+1,len(x)) if _n(x.iloc[i].close) < choch_level and _bear(x.iloc[i])), None)
        if ci is None: return _fail(strategy, direction, "CHOCH_CLOSE_FAILED")
        fvg = _latest_fvg(x, direction, si+1, ci+1)
        if not fvg: return _fail(strategy, direction, "NO_FVG_NO_ENTRY")
        ob = _ob(x, direction, ci)
        entry = fvg["ce"]; sl = _n(sc.high) + .10*a
        target = min([v for _,v in lows if v < entry] or [entry - 3*a])
    risk = abs(entry-sl); reward = abs(target-entry); rr = reward/max(risk,1e-12)
    if rr < 2.0: return _fail(strategy, direction, "RR_BELOW_2", {"risk_reward": rr})
    ev = {"sweep_level": level, "sweep_low": _n(sc.low) if direction=="BUY" else None, "sweep_high": _n(sc.high) if direction=="SELL" else None, "choch_level": choch_level, "choch_index": ci, "fvg": fvg, "order_block": ob, "entry_price": entry, "sl_price": sl, "tp_price": target, "risk_reward": rr, "atr": a}
    return _result(strategy, direction, ev, 94, "LIMIT")


def continuation_fvg_pullback(m5, direction, ctx):
    strategy = "CONTINUATION_FVG_PULLBACK"
    x = m5.tail(140).reset_index(drop=True); a = _atr(x)
    if len(x) < 40: return _fail(strategy, direction, "INSUFFICIENT_M5_CONTEXT")
    htf = str(ctx.get("h1_bias") or (ctx.get("m15") or {}).get("direction") or "NEUTRAL").upper()
    if htf != direction: return _fail(strategy, direction, "HTF_CLEAR_TREND_FAILED")
    if bool(ctx.get("high_impact_news") or ctx.get("news_blocked")): return _fail(strategy, direction, "HIGH_IMPACT_NEWS_BLOCK")
    highs, lows = _pivots(x)
    if direction == "BUY":
        level = highs[-1][1] if highs else None
        bi = next((i for i in range(max(5,len(x)-25),len(x)-1) if level is not None and _n(x.iloc[i].close)>level and _bull(x.iloc[i])), None)
    else:
        level = lows[-1][1] if lows else None
        bi = next((i for i in range(max(5,len(x)-25),len(x)-1) if level is not None and _n(x.iloc[i].close)<level and _bear(x.iloc[i])), None)
    if bi is None: return _fail(strategy, direction, "M5_BOS_CHOCH_FAILED")
    avg_body=max(_body(x.iloc[max(0,bi-20):bi].iloc[j]) for j in range(min(1,len(x.iloc[max(0,bi-20):bi])))) if False else max(_body(x.iloc[i]) for i in range(max(0,bi-10),bi))
    if _body(x.iloc[bi]) < max(avg_body*1.2,.6*a): return _fail(strategy, direction, "DISPLACEMENT_FAILED")
    fvg = _latest_fvg(x, direction, bi, min(len(x),bi+6))
    if not fvg: return _fail(strategy, direction, "M5_FVG_REQUIRED")
    pull = x.iloc[fvg["index"]+1:]
    if pull.empty: return _fail(strategy, direction, "NO_PULLBACK")
    if direction == "BUY":
        eq = any(abs(_n(pull.low.iloc[i])-_n(pull.low.iloc[j])) <= .15*a for i in range(max(0,len(pull)-10),len(pull)) for j in range(max(0,i-4),i))
        sweep = _n(pull.low.min()) <= fvg["top"]
        invalid = _n(pull.close.iloc[-1]) < fvg["bottom"] and _n(pull.low.min()) <= fvg["bottom"]
        sl_base = _n(x.low.iloc[fvg["index"]])
        targets=[v for _,v in highs if v>fvg["ce"]]
        target=max(targets or [fvg["ce"]+3*a])
    else:
        eq = any(abs(_n(pull.high.iloc[i])-_n(pull.high.iloc[j])) <= .15*a for i in range(max(0,len(pull)-10),len(pull)) for j in range(max(0,i-4),i))
        sweep = _n(pull.high.max()) >= fvg["bottom"]
        invalid = _n(pull.close.iloc[-1]) > fvg["top"] and _n(pull.high.max()) >= fvg["top"]
        sl_base = _n(x.high.iloc[fvg["index"]])
        targets=[v for _,v in lows if v<fvg["ce"]]
        target=min(targets or [fvg["ce"]-3*a])
    if not eq or not sweep: return _fail(strategy, direction, "PULLBACK_LIQUIDITY_BUILDUP_FAILED")
    if invalid: return _fail(strategy, direction, "FVG_INVALIDATED")
    entry=fvg["ce"]; sl=sl_base-.10*a if direction=="BUY" else sl_base+.10*a; rr=abs(target-entry)/max(abs(entry-sl),1e-12)
    if rr<2.0:return _fail(strategy,direction,"RR_BELOW_2",{"risk_reward":rr})
    m1=ctx.get("m1")
    conservative=False
    if isinstance(m1,pd.DataFrame) and len(m1)>=5:
        mh,ml=_pivots(m1.tail(80).reset_index(drop=True))
        if direction=="BUY": conservative=bool(mh and _n(m1.iloc[-1].close)>mh[-1][1])
        else: conservative=bool(ml and _n(m1.iloc[-1].close)<ml[-1][1])
    ev={"bos_level":level,"fvg":fvg,"liquidity_buildup":eq,"pullback_sweep":sweep,"entry_price":entry,"sl_price":sl,"tp_price":target,"risk_reward":rr,"entry_mode":"CONSERVATIVE_M1_CHOCH" if conservative else "AGGRESSIVE_CE50","atr":a}
    return _result(strategy,direction,ev,93,"MARKET" if conservative else "LIMIT")


def _thai_hour(ts):
    t=pd.to_datetime(ts,utc=True,errors="coerce")
    return None if pd.isna(t) else t.tz_convert("Asia/Bangkok")


def session_breakout_retest(m5, direction, ctx):
    strategy="SESSION_BREAKOUT_RETEST"
    x=m5.copy(); a=_atr(x)
    if "datetime" not in x.columns or len(x)<30:return _fail(strategy,direction,"DATETIME_REQUIRED")
    ts=pd.to_datetime(x.datetime,utc=True,errors="coerce"); now=_thai_hour(x.datetime.iloc[-1])
    if now is None:return _fail(strategy,direction,"INVALID_DATETIME")
    h=now.hour+now.minute/60
    session="LONDON" if 14<=h<17 else "NY" if 19.5<=h<22.5 else None
    if session is None:return _fail(strategy,direction,"OUTSIDE_EXECUTION_WINDOW")
    day=now.date(); local=ts.dt.tz_convert("Asia/Bangkok"); asian=x.loc[(local.dt.date==day)&(local.dt.hour>=6)&(local.dt.hour<13)]
    if len(asian)<12:return _fail(strategy,direction,"ASIAN_RANGE_NOT_READY")
    ah,al=_n(asian.high.max()),_n(asian.low.min()); rng=ah-al
    prior=ctx.get("session_trade_taken")
    if isinstance(prior,dict) and prior.get(session):return _fail(strategy,direction,"ONE_TRADE_PER_SESSION")
    breakout=None
    for i in range(len(x)-1,0,-1):
        local_i=local.iloc[i]; hh=local_i.hour+local_i.minute/60
        if (session=="LONDON" and not(14<=hh<17)) or (session=="NY" and not(19.5<=hh<22.5)): continue
        c=x.iloc[i]
        if direction=="BUY" and _n(c.close)>ah and _bull(c): breakout=(i,c);break
        if direction=="SELL" and _n(c.close)<al and _bear(c): breakout=(i,c);break
    if not breakout:return _fail(strategy,direction,"SESSION_BREAKOUT_FAILED",{"asian_high":ah,"asian_low":al})
    bi,bc=breakout
    bt=pd.to_datetime(x.datetime.iloc[bi],utc=True); age=pd.to_datetime(x.datetime.iloc[-1],utc=True)-bt
    if age>pd.Timedelta(hours=1):return _fail(strategy,direction,"RETEST_TIMEOUT_1H")
    post=x.iloc[bi+1:]
    if direction=="BUY":
        deepest=_n(post.low.min()) if not post.empty else 1e18; retest=deepest<=ah or bool((post.low<=ah).any()); middle=al+rng*.5; invalid=deepest<middle; trigger=_bull(x.iloc[-1])
        anchor=ah
    else:
        highest=_n(post.high.max()) if not post.empty else -1e18; retest=highest>=al or bool((post.high>=al).any()); middle=al+rng*.5; invalid=highest>ah-rng*.5; trigger=_bear(x.iloc[-1]); anchor=al
    if not retest:return _fail(strategy,direction,"RETEST_NOT_REACHED")
    if invalid:return _fail(strategy,direction,"ASIAN_RANGE_50_PERCENT_INVALIDATION")
    avg_vol=_n(pd.to_numeric(x.volume.iloc[max(0,bi-20):bi],errors="coerce").mean(),0) if "volume" in x else 0
    vol=_n(x.volume.iloc[bi],0) if "volume" in x else 0
    momentum=_body(bc)>=.6*a
    if avg_vol>0 and vol<avg_vol:return _fail(strategy,direction,"BREAKOUT_VOLUME_NOT_CONFIRMED")
    if not momentum:return _fail(strategy,direction,"BREAKOUT_MOMENTUM_NOT_CONFIRMED")
    if not trigger:return _fail(strategy,direction,"RETEST_TRIGGER_FAILED")
    entry=_n(x.close.iloc[-1]); sl=(_n(post.low.min())-.10*a if direction=="BUY" else _n(post.high.max())+.10*a)
    risk=abs(entry-sl); tp1=entry+risk*1.5 if direction=="BUY" else entry-risk*1.5
    highs,lows=_pivots(x); tp2=max([v for _,v in highs if v>entry] or [tp1]) if direction=="BUY" else min([v for _,v in lows if v<entry] or [tp1])
    rr=max(1.5,abs(tp2-entry)/max(risk,1e-12))
    if rr<1.5:return _fail(strategy,direction,"RR_BELOW_1_5")
    return _result(strategy,direction,{"asian_high":ah,"asian_low":al,"session":session,"breakout_index":bi,"breakout_volume_ratio":vol/max(avg_vol,1e-12) if avg_vol else None,"retest_anchor":anchor,"entry_price":entry,"sl_price":sl,"tp1":tp1,"tp2":tp2,"risk_reward":rr,"retest_timeout":"1H","range_mid":middle},88,"MARKET")


GOLD_NEW_REGISTRY={
    "G1": liquidity_sweep_choch,
    "G2": continuation_fvg_pullback,
    "G3": session_breakout_retest,
}


def evaluate_new_gold_engines(m5,m15,h1,regime):
    ctx={"h1_bias":regime.get("h1_bias"),"h1_poi":regime.get("h1_poi"),"poi":regime.get("poi"),"m15":regime.get("m15_context") or {}}
    out=[]; trace=[]
    for gid in ("G1","G2","G3"):
        for direction in ("BUY","SELL"):
            try:
                r=GOLD_NEW_REGISTRY[gid](m5,direction,ctx)
                item={"status":r.status,"engine":gid,"strategy":f"{gid}_{GOLD_NEW_ENGINE_NAMES[gid]}","direction":direction,"setup_anchor":(r.evidence or {}).get("setup_anchor"),"evidence":dict(r.evidence or {}),"quality":float(r.quality or 0),"trigger_signature":f"{gid}|{direction}|{(r.evidence or {}).get('entry_price')}","entry_type_hint":"LIMIT" if gid in ("G1","G2") else "MARKET","rejection_reasons":list(r.reasons or ())}
            except Exception as exc:
                item={"status":"FAIL","engine":gid,"strategy":f"{gid}_{GOLD_NEW_ENGINE_NAMES[gid]}","direction":direction,"quality":0.0,"rejection_reasons":[f"ENGINE_ERROR:{type(exc).__name__}:{exc}"]}
            trace.append(item)
            if item["status"]=="PASS":
                item["score_detail"]={"score":item["quality"],"qualified":True,"components":{"gold_new_engine_quality":item["quality"]}}
                out.append(item)
    out.sort(key=lambda z:(int(str(z["engine"])[1:]),-z.get("quality",0)))
    return out,trace

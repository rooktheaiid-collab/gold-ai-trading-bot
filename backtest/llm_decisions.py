"""
Phase 1 of the REAL-LLM backtest: fetch the LLM's decision at every
technically-valid candidate setup (the same ~528 points the rules-proxy fired).

Each candidate's LLM decision depends ONLY on market data at that bar (not on
whether we currently hold a position), so we fetch them in parallel and cache
to disk (resumable). Phase 2 (run_llm_backtest.py) then replays them through the
SAME trade engine, sequentially, acting only when flat.

Limitation (honest): we have no historical funding / open-interest / news for
this period, so those inputs are passed as N/A — the LLM decides on price +
technicals only (same blind spot as the proxy). News-sentiment edge is OFF.
"""
import os, sys, json, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "..")

# ── configure the LLM provider BEFORE importing config/llm_brain ──────────────
# Jangan hardcode API key di sini. Set lewat environment / .env (export LLM_API_KEY=...).
os.environ.setdefault("LLM_PROVIDER",   "openai")
os.environ.setdefault("LLM_BASE_URL",   "https://integrate.api.nvidia.com/v1")
os.environ.setdefault("LLM_MODEL",      os.environ.get("BT_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"))
os.environ.setdefault("LLM_MAX_TOKENS", "4000")   # reasoning model: needs room for think + JSON
os.environ.setdefault("LLM_TEMPERATURE","0.2")
if not os.environ.get("LLM_API_KEY"):
    raise SystemExit("Set LLM_API_KEY dulu (export LLM_API_KEY=...) sebelum jalankan backtest LLM.")

import pandas as pd
import run_backtest as BT
import technical_analysis as TA
import llm_brain as LB

CACHE = os.environ.get("BT_CACHE", "llm_cache.json")
MAX_WORKERS = 10

def build_payloads(only_indices=None):
    if only_indices is None and os.path.exists("proxy_entry_indices.json"):
        only_indices = set(json.load(open("proxy_entry_indices.json")))
    d15 = BT.load("15m"); d1h = BT.load("1h"); d1d = BT.load("1d")
    d15i, C = BT.precompute_15m(d15)
    b15 = BT.precompute_ema_bias(d15)["bias"].tolist()
    d1h_b = BT.precompute_ema_bias(d1h)["bias"].tolist()
    d1h_close = (d1h["timestamp"] + pd.Timedelta(hours=1)).tolist()
    piv = BT.daily_pivots(d1d)

    cols = {k: (d15i[v].tolist() if v else [None]*len(d15)) for k,v in C.items()}
    ts = d15["timestamp"].tolist(); cl = d15["close"].tolist()
    hi = d15["high"].tolist(); lo = d15["low"].tolist()
    d1d_dates = d1d["timestamp"].dt.date.tolist()

    # find candidate bars (proxy signal != None), then build LLM input payloads
    cands = []
    h1_ptr = 0
    for i in range(200, len(d15)):
        t = ts[i]; cand_close = t + pd.Timedelta(minutes=15)
        while h1_ptr + 1 < len(d1h_close) and d1h_close[h1_ptr+1] <= cand_close:
            h1_ptr += 1
        bias1h_simple = d1h_b[h1_ptr] if d1h_close[h1_ptr] <= cand_close else "NEUTRAL"
        dec = BT.make_decision(cl[i], cols["ema20"][i], cols["ema50"][i],
                               cols["ema200"][i], cols["macd"][i], cols["macds"][i],
                               cols["macd"][i-1], cols["macds"][i-1], cols["rsi"][i],
                               cols["bbu"][i], cols["bbm"][i], cols["bbl"][i],
                               cols["atr"][i], b15[i], bias1h_simple, piv.get(t.date()))
        if dec is None:
            continue
        if only_indices is not None and i not in only_indices:
            continue
        cands.append((i, t, cand_close))

    # precompute heavy real-indicator payloads (sequential, fast)
    payloads = {}
    # cache 1h close times for slicing
    for (i, t, cand_close) in cands:
        w15 = d15.iloc[max(0, i-299): i+1].copy()
        # daily_df up to current date (compute_pivots uses iloc[-2] = prior day)
        cur_date = t.date()
        ddf = d1d[[dt <= cur_date for dt in d1d_dates]].copy()
        # 1h window: candles closed by this 15m candle's close
        mask = (d1h["timestamp"] + pd.Timedelta(hours=1)) <= cand_close
        w1h = d1h[mask].tail(300).copy()
        if len(w1h) < 50:
            continue
        t15 = TA.compute_indicators(w15, ddf if len(ddf) >= 2 else None)
        t1h = TA.compute_indicators(w1h)
        bias = TA.compute_multi_tf_bias(w15, w1h)
        # ticker dict
        price = float(cl[i])
        j24 = max(0, i-96)
        prev24 = float(cl[j24])
        change_pct = round((price/prev24 - 1)*100, 2)
        window24 = d15.iloc[j24:i+1]
        ticker = dict(timestamp=str(t), price=price, change_pct=change_pct,
                      high_24h=float(window24["high"].max()),
                      low_24h=float(window24["low"].min()))
        payloads[i] = dict(ticker=ticker, t15=t15, t1h=t1h, bias=bias,
                           ts=str(t), close=price)
    return payloads

def fetch_all():
    payloads = build_payloads()
    print(f"candidates with full payload: {len(payloads)}")
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE))
    todo = [i for i in payloads if str(i) not in cache]
    print(f"already cached: {len(cache)} | to fetch: {len(todo)}")
    if not todo:
        return cache, payloads

    lock = threading.Lock()
    done = [0]; t0 = time.time()

    def work(i):
        p = payloads[i]
        try:
            dec = LB.analyze_market(p["ticker"], p["t15"], p["t1h"], p["bias"],
                                    funding={}, open_interest={}, news=[])
        except Exception as e:
            dec = {"signal":"HOLD","confidence":0,"trade_quality":"SKIP",
                   "reasoning":f"error: {str(e)[:120]}"}
        return i, dec

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(work, i): i for i in todo}
        for fut in as_completed(futs):
            i, dec = fut.result()
            with lock:
                cache[str(i)] = dec
                done[0] += 1
                if done[0] % 10 == 0:
                    json.dump(cache, open(CACHE,"w"))
                    el = time.time()-t0
                    rate = done[0]/el
                    print(f"  {done[0]}/{len(todo)}  ({rate:.2f}/s, ETA {int((len(todo)-done[0])/max(rate,0.01))}s)", flush=True)
    json.dump(cache, open(CACHE,"w"))
    print(f"DONE. cached {len(cache)} decisions.")
    return cache, payloads

if __name__ == "__main__":
    fetch_all()

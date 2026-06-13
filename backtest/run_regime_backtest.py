"""Backtest the REGIME (HTF 1h trend) + ADX gates on top of the session filter,
through the real _regime_ok() / _session_ok() code path. Replays the LLM cache.
HTF trend = 1h EMA20/50(/200) label (causal, last closed 1h bar); ADX = 15m ADX-14.
All other params at shipped defaults (slippage 2bps, MIN_RR=1.2, session 12-17 UTC)."""
import sys, json
sys.path.insert(0, "..")
import numpy as np, pandas as pd
import config, trade_engine as TE
import run_backtest as BT

START = 1000.0

def label_trend(price, e20, e50, e200):
    if not (e20 and e50) or np.isnan(e20) or np.isnan(e50):
        return "NEUTRAL"
    if e200 and not np.isnan(e200):
        if   price > e20 > e50 > e200: return "STRONG BULLISH"
        elif price < e20 < e50 < e200: return "STRONG BEARISH"
        elif price > e20 > e50:        return "BULLISH"
        elif price < e20 < e50:        return "BEARISH"
        return "NEUTRAL"
    if   price > e20 > e50: return "BULLISH"
    elif price < e20 < e50: return "BEARISH"
    return "NEUTRAL"

def precompute():
    d15 = BT.load("15m"); d1h = BT.load("1h")
    # 15m ADX-14 (causal rolling on full series)
    a = d15.copy(); a.ta.adx(length=14, append=True)
    adx15 = a["ADX_14"].tolist()
    # 1h trend label per closed 1h bar
    h = d1h.copy()
    h["e20"] = h["close"].ewm(span=20, adjust=False).mean()
    h["e50"] = h["close"].ewm(span=50, adjust=False).mean()
    h["e200"] = h["close"].ewm(span=200, adjust=False).mean()
    h1_ts = h["timestamp"].values
    h1_trend = [label_trend(h["close"].iat[j], h["e20"].iat[j], h["e50"].iat[j],
                            h["e200"].iat[j] if len(h) >= 200 else None)
                for j in range(len(h))]
    return d15, adx15, h1_ts, h1_trend

def htf_at(ts_i, h1_ts, h1_trend):
    # last 1h bar strictly before this 15m candle (causal, avoid lookahead)
    j = int(np.searchsorted(h1_ts, np.datetime64(ts_i), side="left")) - 1
    if j < 0:
        return "NEUTRAL"
    return h1_trend[j]

def run(label, regime, min_adx, d15, adx15, h1_ts, h1_trend):
    cache = json.load(open("llm_cache.json"))
    entry_set = set(json.load(open("proxy_entry_indices.json")))
    ts = d15["timestamp"].tolist(); cl = d15["close"].tolist()
    hi = d15["high"].tolist(); lo = d15["low"].tolist(); n = len(d15)
    TE.paper_state.update(dict(balance=START, position=None, trade_log=[],
                               total_pnl=0.0, wins=0, losses=0, fees_paid=0.0))
    config.TRADE_USDT = 50; config.LEVERAGE = 5
    config.TRADING_HOURS_UTC = config._parse_hours("12-17")  # session filter ON (default)
    config.REGIME_FILTER = regime
    config.MIN_ADX = min_adx
    for i in range(200, n):
        if TE.paper_state["position"]:
            TE.paper_check_close(cl[i], candle_high=hi[i], candle_low=lo[i])
        if not TE.paper_state["position"] and i in entry_set:
            dec = cache.get(str(i))
            if not dec:
                continue
            sig = (dec.get("signal") or "HOLD").upper()
            qual = dec.get("trade_quality") or "SKIP"
            if sig not in ("LONG", "SHORT") or qual in ("C", "SKIP"):
                continue
            # session gate (via real code) + regime gate (via real code)
            if not TE._session_ok(ts[i]):
                continue
            htf = htf_at(ts[i], h1_ts, h1_trend)
            adxv = adx15[i] if i < len(adx15) and not pd.isna(adx15[i]) else None
            ok, _ = TE._regime_ok(sig, htf, adxv)
            if not ok:
                continue
            d2 = dict(dec); d2["entry_price"] = cl[i]
            TE.paper_open_trade(d2, cl[i], at=ts[i])
    if TE.paper_state["position"]:
        TE._paper_close_remaining(cl[-1], "EOD_CLOSE")
    s = TE.get_paper_stats()
    eq = s["balance"] - START
    return dict(label=label, tr=s["total_trades"], wr=s["winrate"], wins=s["wins"],
                losses=s["losses"], pnl=round(eq, 2), ret=round(eq/START*100, 2))

def main():
    d15, adx15, h1_ts, h1_trend = precompute()
    combos = [
        ("Session saja (12-17)",            False, 0),
        ("+ Regime (tren 1h)",              True,  0),
        ("+ ADX>=20",                       False, 20),
        ("+ Regime + ADX>=20 (default baru)", True, 20),
    ]
    out = []
    print(f"{'Config':<36}{'Trade':>6}{'WinRate':>9}{'NetPnL':>10}{'Return':>9}")
    for lbl, reg, adx in combos:
        r = run(lbl, reg, adx, d15, adx15, h1_ts, h1_trend)
        out.append(r)
        print(f"{lbl:<36}{r['tr']:>6}{r['wr']:>8}%{r['pnl']:>+10.2f}{r['ret']:>+8.2f}%")
    json.dump(out, open("regime_result.json", "w"), indent=2)

if __name__ == "__main__":
    main()

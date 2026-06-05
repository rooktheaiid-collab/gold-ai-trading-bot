"""
Gold AI Trading Bot — Backtest on REAL historical XAUUSDT data
===============================================================
Data: Binance Futures (UM) official archive, XAUUSDT 15m/1h/1d, Jan–May 2026.

IMPORTANT / HONEST NOTE
-----------------------
The live bot makes each decision with an LLM. Calling an LLM ~14,000 times is
not feasible here (no API key, prohibitive cost/time). So this backtest uses a
DETERMINISTIC RULES PROXY that mirrors the bot's *hard rules* and indicator
pipeline (multi-timeframe trend alignment, RSI, MACD crossover, ATR-based
risk). It does NOT model the LLM's discretionary judgment or news sentiment.
Treat results as a sanity-check of the technical core + trade engine on real
data — not as the exact performance of the LLM-driven bot.

Faithfulness:
- Uses the bot's REAL trade_engine.py (paper fills via candle high/low,
  taker fee 0.04%/leg, partial TP1 50% + breakeven, SL-priority).
- Uses the SAME indicator definitions as technical_analysis.py (pandas-ta),
  precomputed CAUSALLY on the full series (each row uses only past+current
  data) and read walk-forward to avoid look-ahead bias.
- Daily pivots from the previous completed daily candle (intraday standard).
"""
import sys, json
sys.path.insert(0, "..")
import numpy as np
import pandas as pd
import pandas_ta as ta

import config
import trade_engine as TE

# ───────────────────────── Risk model (mirrors system prompt) ─────────────────
ATR_SL_MULT   = 1.2     # SL distance = 1.2 * ATR  (rule: 1.0–1.5 ATR)
RR_TP1        = 1.5     # TP1 at 1.5R (rule: min R:R 1:2 on full target; TP1 partial)
RR_TP2        = 3.0     # TP2 at 3.0R
CONF_GATE     = 65      # only trade quality >= B+ (confidence >= 65)
START_BAL     = 1000.0

# ───────────────────────── Data loading ──────────────────────────────────────
def load(tf):
    df = pd.read_csv(f"data/XAUUSDT_{tf}.csv")
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    return df[["timestamp","open","high","low","close","volume"]].reset_index(drop=True)

def _col(d, prefix):
    for c in d.columns:
        if c.startswith(prefix) and c not in ("timestamp","open","high","low","close","volume"):
            return c
    return None

# ───────────────────────── Causal indicator precompute (15m) ─────────────────
def precompute_15m(d):
    d = d.copy()
    d.ta.ema(length=20,  append=True)
    d.ta.ema(length=50,  append=True)
    d.ta.ema(length=200, append=True)
    d.ta.macd(fast=12, slow=26, signal=9, append=True)
    d.ta.rsi(length=14, append=True)
    d.ta.bbands(length=20, std=2, append=True)
    d.ta.atr(length=14, append=True)
    cols = dict(
        ema20=_col(d,"EMA_20"), ema50=_col(d,"EMA_50"), ema200=_col(d,"EMA_200"),
        macd=_col(d,"MACD_"), macds=_col(d,"MACDs_"),
        rsi=_col(d,"RSI_14"),
        bbu=_col(d,"BBU_"), bbm=_col(d,"BBM_"), bbl=_col(d,"BBL_"),
        atr=_col(d,"ATRr_") or _col(d,"ATR_"),
    )
    return d, cols

def precompute_ema_bias(df):
    """EMA20/50 for the simple multi-tf bias (matches compute_multi_tf_bias)."""
    e20 = df["close"].ewm(span=20, min_periods=20).mean()
    e50 = df["close"].ewm(span=50, min_periods=50).mean()
    bias = []
    for c, a, b in zip(df["close"], e20, e50):
        if pd.isna(a) or pd.isna(b):
            bias.append("NEUTRAL")
        elif c > a > b:
            bias.append("BULL")
        elif c < a < b:
            bias.append("BEAR")
        else:
            bias.append("NEUTRAL")
    out = df[["timestamp"]].copy()
    out["bias"] = bias
    out["close_time"] = out["timestamp"] + pd.Timedelta(minutes=0)  # placeholder
    return out

# ───────────────────────── Daily pivots per calendar day ─────────────────────
def daily_pivots(d1d):
    piv = {}  # date -> pivot dict using THAT date's PREVIOUS day candle
    rows = d1d.reset_index(drop=True)
    for i in range(1, len(rows)):
        prev = rows.iloc[i-1]
        h, l, c = float(prev.high), float(prev.low), float(prev.close)
        pp = (h+l+c)/3
        day = rows.iloc[i].timestamp.date()
        piv[day] = dict(pivot=pp, r1=2*pp-l, s1=2*pp-h, r2=pp+(h-l), s2=pp-(h-l),
                        r3=pp+2*(h-l), s3=pp-2*(h-l))
    return piv

# ───────────────────────── Signal proxy ──────────────────────────────────────
def make_decision(price, ema20, ema50, ema200, macd, macds, macd_prev, macds_prev,
                  rsi, bbu, bbm, bbl, atr, bias15, bias1h, piv):
    if any(v is None or (isinstance(v,float) and np.isnan(v)) for v in
           [price, ema20, ema50, macd, macds, rsi, atr]) or atr <= 0:
        return None

    # 15m trend label (same thresholds as technical_analysis.compute_indicators)
    trend = "NEUTRAL"
    if ema200 is not None and not np.isnan(ema200):
        if   price > ema20 > ema50 > ema200: trend = "STRONG BULLISH"
        elif price < ema20 < ema50 < ema200: trend = "STRONG BEARISH"
        elif price > ema20 > ema50:          trend = "BULLISH"
        elif price < ema20 < ema50:          trend = "BEARISH"
    else:
        if   price > ema20 > ema50: trend = "BULLISH"
        elif price < ema20 < ema50: trend = "BEARISH"

    # MACD crossover state (true cross via prev bar)
    macd_state = "NEUTRAL"
    if None not in (macd_prev, macds_prev) and not (np.isnan(macd_prev) or np.isnan(macds_prev)):
        up   = macd_prev <= macds_prev and macd > macds
        down = macd_prev >= macds_prev and macd < macds
        if   up:   macd_state = "BULL_CROSS"
        elif down: macd_state = "BEAR_CROSS"
        elif macd > macds: macd_state = "BULL"
        elif macd < macds: macd_state = "BEAR"

    # multi-tf alignment gate
    if   bias15 == "BULL" and bias1h == "BULL": align = "ALIGNED_BULL"
    elif bias15 == "BEAR" and bias1h == "BEAR": align = "ALIGNED_BEAR"
    elif bias15 == "NEUTRAL" or bias1h == "NEUTRAL": align = "NEUTRAL"
    else: align = "CONFLICTING"

    side = None
    if align == "ALIGNED_BULL" and trend in ("BULLISH","STRONG BULLISH") \
       and macd_state in ("BULL_CROSS","BULL") and rsi < 70:
        side = "LONG"
    elif align == "ALIGNED_BEAR" and trend in ("BEARISH","STRONG BEARISH") \
         and macd_state in ("BEAR_CROSS","BEAR") and rsi > 30:
        side = "SHORT"
    if side is None:
        return None

    # confidence / confluence scoring
    conf = 50
    if "STRONG" in trend: conf += 12
    else: conf += 6
    if macd_state in ("BULL_CROSS","BEAR_CROSS"): conf += 15
    else: conf += 8
    if side == "LONG"  and 50 <= rsi <= 65: conf += 10
    if side == "SHORT" and 35 <= rsi <= 50: conf += 10
    if bbu and bbl and bbm:
        if side == "LONG"  and price < bbm:  conf += 6   # buying a pullback
        if side == "SHORT" and price > bbm:  conf += 6
    conf = min(conf, 95)
    if conf < CONF_GATE:
        return None

    risk = ATR_SL_MULT * atr
    if side == "LONG":
        sl  = price - risk
        tp1 = price + RR_TP1 * risk
        tp2 = price + RR_TP2 * risk
    else:
        sl  = price + risk
        tp1 = price - RR_TP1 * risk
        tp2 = price - RR_TP2 * risk
    quality = "A+" if conf >= 85 else ("A" if conf >= 75 else "B")
    return dict(signal=side, entry_price=round(price,4), stop_loss=round(sl,4),
                take_profit_1=round(tp1,4), take_profit_2=round(tp2,4),
                confidence=conf, trade_quality=quality)

# ───────────────────────── Backtest loop ─────────────────────────────────────
def run():
    d15 = load("15m"); d1h = load("1h"); d1d = load("1d")
    d15i, C = precompute_15m(d15)
    b15 = precompute_ema_bias(d15)["bias"].tolist()
    # 1h bias with close timestamps
    d1h_b = precompute_ema_bias(d1h)
    d1h_close = (d1h["timestamp"] + pd.Timedelta(hours=1)).tolist()  # 1h candle close time
    d1h_bias = d1h_b["bias"].tolist()
    piv = daily_pivots(d1d)

    # reset engine state for clean run
    TE.paper_state.update(dict(balance=START_BAL, position=None, trade_log=[],
                               total_pnl=0.0, wins=0, losses=0, fees_paid=0.0))
    config.TRADE_USDT = 50; config.LEVERAGE = 5

    ema20 = d15i[C["ema20"]].tolist(); ema50 = d15i[C["ema50"]].tolist()
    ema200 = d15i[C["ema200"]].tolist() if C["ema200"] else [None]*len(d15)
    macd = d15i[C["macd"]].tolist(); macds = d15i[C["macds"]].tolist()
    rsi = d15i[C["rsi"]].tolist()
    bbu = d15i[C["bbu"]].tolist(); bbm = d15i[C["bbm"]].tolist(); bbl = d15i[C["bbl"]].tolist()
    atr = d15i[C["atr"]].tolist()
    ts  = d15["timestamp"].tolist()
    op  = d15["open"].tolist(); hi = d15["high"].tolist(); lo = d15["low"].tolist(); cl = d15["close"].tolist()

    n = len(d15)
    signals = 0
    h1_ptr = 0
    equity_curve = []
    entry_indices = []
    for i in range(200, n):
        t = ts[i]
        # advance 1h pointer to latest 1h candle CLOSED by end of this 15m candle
        cand_close = t + pd.Timedelta(minutes=15)
        while h1_ptr + 1 < len(d1h_close) and d1h_close[h1_ptr+1] <= cand_close:
            h1_ptr += 1
        bias1h = d1h_bias[h1_ptr] if d1h_close[h1_ptr] <= cand_close else "NEUTRAL"
        bias15 = b15[i]

        # 1) manage open position with THIS candle's high/low (entry was a prior close)
        if TE.paper_state["position"]:
            TE.paper_check_close(cl[i], candle_high=hi[i], candle_low=lo[i])

        # 2) if flat, evaluate a new decision at this candle close
        if not TE.paper_state["position"]:
            day = t.date()
            dec = make_decision(cl[i], ema20[i], ema50[i],
                                ema200[i] if ema200[i] is not None else None,
                                macd[i], macds[i], macd[i-1], macds[i-1],
                                rsi[i], bbu[i], bbm[i], bbl[i], atr[i],
                                bias15, bias1h, piv.get(day))
            if dec:
                signals += 1
                entry_indices.append(i)
                TE.paper_open_trade(dec, cl[i])

        # record equity (balance + unrealized of open pos marked at close)
        bal = TE.paper_state["balance"]
        pos = TE.paper_state["position"]
        unreal = 0.0
        if pos:
            unreal = TE._realized_pnl(pos["side"], pos["entry"], cl[i], pos["qty_left"])
        equity_curve.append((t.isoformat(), round(bal+unreal,2)))

    # close any dangling position at last close
    if TE.paper_state["position"]:
        TE._paper_close_remaining(cl[-1], "EOD_CLOSE")

    stats = TE.get_paper_stats()

    # buy & hold baseline (same notional exposure as one trade: TRADE_USDT*LEVERAGE)
    first, last = cl[200], cl[-1]
    bh_ret_pct = (last/first - 1)*100
    bh_pnl = (config.TRADE_USDT*config.LEVERAGE) * (last/first - 1)

    # max drawdown on equity
    eq = [v for _, v in equity_curve]
    peak = -1e18; mdd = 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v - peak)
    mdd_pct = (mdd/peak*100) if peak else 0.0

    result = dict(
        period=f"{ts[200].date()} → {ts[-1].date()}",
        candles_15m=n, decision_bars=n-200, signals=signals,
        start_balance=START_BAL, end_balance=stats["balance"],
        net_pnl=round(stats["balance"]-START_BAL,2),
        return_pct=round((stats["balance"]/START_BAL-1)*100,2),
        total_trades=stats["total_trades"], wins=stats["wins"], losses=stats["losses"],
        winrate=stats["winrate"], fees_paid=stats["fees_paid"],
        max_drawdown_usd=round(mdd,2), max_drawdown_pct=round(mdd_pct,2),
        first_price=first, last_price=last,
        buyhold_return_pct=round(bh_ret_pct,2), buyhold_pnl=round(bh_pnl,2),
        trade_log=stats_full_log(),
    )
    with open("backtest_result.json","w") as f:
        json.dump(result, f, indent=2, default=str)
    with open("proxy_entry_indices.json","w") as f:
        json.dump(entry_indices, f)
    # save equity curve
    pd.DataFrame(equity_curve, columns=["timestamp","equity"]).to_csv("equity_curve.csv", index=False)
    print(json.dumps({k:v for k,v in result.items() if k!="trade_log"}, indent=2))
    print("TRADES:", len(result["trade_log"]))
    return result

def stats_full_log():
    return TE.paper_state["trade_log"]

if __name__ == "__main__":
    run()

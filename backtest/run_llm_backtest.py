"""
Phase 2 of the REAL-LLM backtest.
Replays the cached LLM decisions (llm_cache.json) through the SAME trade engine
as the proxy backtest, sequentially. At each of the 528 proxy candidate bars,
WHEN FLAT, we consult the LLM's decision:
  - signal LONG/SHORT and trade_quality not in {C, SKIP}  -> open the trade
  - otherwise                                             -> skip (stay flat)
Entry is a MARKET fill at that bar's close (same as the proxy backtest); we keep
the LLM's own stop_loss / take_profit levels. Positions are then managed candle
by candle by the real trade_engine (SL-priority, 50% partial TP1 + breakeven,
0.04%/leg taker fee).
"""
import sys, json
sys.path.insert(0, "..")
import pandas as pd
import config
import trade_engine as TE
import run_backtest as BT

START_BAL = 1000.0

def run():
    cache = json.load(open("llm_cache.json"))
    entry_set = set(json.load(open("proxy_entry_indices.json")))

    d15 = BT.load("15m")
    ts = d15["timestamp"].tolist()
    hi = d15["high"].tolist(); lo = d15["low"].tolist(); cl = d15["close"].tolist()
    n = len(d15)

    TE.paper_state.update(dict(balance=START_BAL, position=None, trade_log=[],
                               total_pnl=0.0, wins=0, losses=0, fees_paid=0.0))
    config.TRADE_USDT = 50; config.LEVERAGE = 5

    acted = 0            # trades actually opened
    consulted = 0        # candidate bars where we were flat & asked the LLM
    llm_long = llm_short = llm_hold = 0
    equity_curve = []

    for i in range(200, n):
        t = ts[i]
        if TE.paper_state["position"]:
            TE.paper_check_close(cl[i], candle_high=hi[i], candle_low=lo[i])

        if not TE.paper_state["position"] and i in entry_set:
            dec = cache.get(str(i))
            if dec:
                consulted += 1
                sig = (dec.get("signal") or "HOLD").upper()
                qual = (dec.get("trade_quality") or "SKIP")
                if sig == "LONG": llm_long += 1
                elif sig == "SHORT": llm_short += 1
                else: llm_hold += 1
                if sig in ("LONG","SHORT") and qual not in ("C","SKIP"):
                    d2 = dict(dec)
                    d2["entry_price"] = cl[i]   # market fill at close (no look-ahead limit)
                    before = len(TE.paper_state["trade_log"])
                    pos_before = TE.paper_state["position"]
                    TE.paper_open_trade(d2, cl[i])
                    if TE.paper_state["position"] and not pos_before:
                        acted += 1

        bal = TE.paper_state["balance"]; pos = TE.paper_state["position"]
        unreal = TE._realized_pnl(pos["side"], pos["entry"], cl[i], pos["qty_left"]) if pos else 0.0
        equity_curve.append((t.isoformat(), round(bal+unreal,2)))

    if TE.paper_state["position"]:
        TE._paper_close_remaining(cl[-1], "EOD_CLOSE")

    stats = TE.get_paper_stats()
    first, last = cl[200], cl[-1]
    eq = [v for _, v in equity_curve]
    peak = -1e18; mdd = 0.0
    for v in eq:
        peak = max(peak, v); mdd = min(mdd, v - peak)
    mdd_pct = (mdd/peak*100) if peak else 0.0

    result = dict(
        mode="REAL_LLM (MiniMax-M2.7-highspeed)",
        period=f"{ts[200].date()} → {ts[-1].date()}",
        candidate_bars=len(entry_set), consulted=consulted,
        llm_signal_breakdown=dict(LONG=llm_long, SHORT=llm_short, HOLD_SKIP=llm_hold),
        trades_opened=acted,
        start_balance=START_BAL, end_balance=stats["balance"],
        net_pnl=round(stats["balance"]-START_BAL,2),
        return_pct=round((stats["balance"]/START_BAL-1)*100,2),
        total_trades=stats["total_trades"], wins=stats["wins"], losses=stats["losses"],
        winrate=stats["winrate"], fees_paid=stats["fees_paid"],
        max_drawdown_usd=round(mdd,2), max_drawdown_pct=round(mdd_pct,2),
        first_price=first, last_price=last,
        trade_log=TE.paper_state["trade_log"],
    )
    with open("llm_backtest_result.json","w") as f:
        json.dump(result, f, indent=2, default=str)
    pd.DataFrame(equity_curve, columns=["timestamp","equity"]).to_csv("llm_equity_curve.csv", index=False)
    print(json.dumps({k:v for k,v in result.items() if k!="trade_log"}, indent=2))
    print("TRADES:", len(result["trade_log"]))
    return result

if __name__ == "__main__":
    run()

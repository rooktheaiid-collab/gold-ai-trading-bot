"""Full backtest of the SESSION FILTER through the REAL trade-engine code path.
Replays the 528 cached LLM decisions, passing each candle's UTC timestamp to
paper_open_trade(at=...) so config.TRADING_HOURS_UTC actually gates entries.
Compares filter OFF vs the new default (12-17 UTC overlap) + a few windows.
All other params at shipped defaults (slippage 2bps, MIN_RR=1.2)."""
import sys, json
sys.path.insert(0, "..")
import config, trade_engine as TE
import run_backtest as BT

START = 1000.0
WINDOWS = [
    ("OFF (semua jam)", None),
    ("Overlap 12-17 UTC (default baru)", config._parse_hours("12-17")),
    ("London+Overlap 07-17", config._parse_hours("7-17")),
    ("Skip Asia 07-22", config._parse_hours("7-22")),
]

def run(hours):
    cache = json.load(open("llm_cache.json"))
    entry_set = set(json.load(open("proxy_entry_indices.json")))
    d15 = BT.load("15m")
    ts = d15["timestamp"].tolist(); cl = d15["close"].tolist()
    hi = d15["high"].tolist(); lo = d15["low"].tolist(); n = len(d15)
    TE.paper_state.update(dict(balance=START, position=None, trade_log=[],
                               total_pnl=0.0, wins=0, losses=0, fees_paid=0.0))
    config.TRADE_USDT = 50; config.LEVERAGE = 5
    config.TRADING_HOURS_UTC = hours          # the lever under test
    for i in range(200, n):
        if TE.paper_state["position"]:
            TE.paper_check_close(cl[i], candle_high=hi[i], candle_low=lo[i])
        if not TE.paper_state["position"] and i in entry_set:
            dec = cache.get(str(i))
            if dec:
                sig = (dec.get("signal") or "HOLD").upper()
                qual = dec.get("trade_quality") or "SKIP"
                if sig in ("LONG", "SHORT") and qual not in ("C", "SKIP"):
                    d2 = dict(dec); d2["entry_price"] = cl[i]
                    TE.paper_open_trade(d2, cl[i], at=ts[i])   # ← session gate fires here
    if TE.paper_state["position"]:
        TE._paper_close_remaining(cl[-1], "EOD_CLOSE")
    s = TE.get_paper_stats()
    eq = s["balance"] - START
    return dict(tr=s["total_trades"], wr=s["winrate"], wins=s["wins"],
                losses=s["losses"], pnl=round(eq, 2), ret=round(eq/START*100, 2),
                fees=round(s["fees_paid"], 2))

def main():
    out = []
    print(f"{'Window':<34}{'Trade':>6}{'WinRate':>9}{'NetPnL':>10}{'Return':>9}")
    for label, h in WINDOWS:
        r = run(h)
        out.append({"label": label, **r})
        print(f"{label:<34}{r['tr']:>6}{r['wr']:>8}%{r['pnl']:>+10.2f}{r['ret']:>+8.2f}%")
    json.dump(out, open("session_full_result.json", "w"), indent=2)

if __name__ == "__main__":
    main()

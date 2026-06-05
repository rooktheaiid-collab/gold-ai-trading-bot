"""
LIVE PAPER-MODE DEMO of the Gold Trading Bot.
=============================================
Runs the bot's REAL pipeline — data -> technical analysis -> LLM brain (live call)
-> paper trade engine — once per hour over the most recent window of real XAUUSDT
data. No real money, no real orders. Simulates the bot "waking up" each hour,
looking at the market, and deciding/managing a paper position.

LLM provider is set via env below (NVIDIA NIM). Funding/OI/news are passed N/A
(no historical source) — same limitation as the backtest.
"""
import os, sys, json, datetime

# ---- LLM provider (set BEFORE importing config/llm_brain) ----
# Jangan hardcode API key di sini. Set lewat environment / .env:
#   export LLM_API_KEY=...   (mis. NVIDIA NIM, OpenAI, dll)
os.environ.setdefault("LLM_PROVIDER",   "openai")
os.environ.setdefault("LLM_BASE_URL",   "https://integrate.api.nvidia.com/v1")
os.environ.setdefault("LLM_MODEL",      "nvidia/nemotron-3-ultra-550b-a55b")
os.environ.setdefault("LLM_MAX_TOKENS", "3000")
os.environ.setdefault("LLM_TEMPERATURE","0.3")
if not os.environ.get("LLM_API_KEY"):
    raise SystemExit("Set LLM_API_KEY dulu (export LLM_API_KEY=...) sebelum jalankan demo ini.")

sys.path.insert(0, "..")
import pandas as pd
import config
import technical_analysis as TA
import trade_engine as TE
import llm_brain as BRAIN
import run_backtest as BT

START_BAL = 1000.0
N_CYCLES  = int(os.environ.get("DEMO_CYCLES", "24"))   # how many hourly cycles to simulate


def build_hour_payload(d15, d1h, d1d, d1d_dates, h_idx):
    """Build the market snapshot the bot would see at the close of 1h candle h_idx."""
    h_close = d1h["timestamp"].iloc[h_idx] + pd.Timedelta(hours=1)
    # 1h window up to & including this candle
    w1h = d1h.iloc[max(0, h_idx-299): h_idx+1].copy()
    # 15m window: candles closed by this 1h close
    mask15 = (d15["timestamp"] + pd.Timedelta(minutes=15)) <= h_close
    w15 = d15[mask15].tail(300).copy()
    if len(w1h) < 50 or len(w15) < 200:
        return None
    cur_date = h_close.date()
    ddf = d1d[[dt <= cur_date for dt in d1d_dates]].copy()
    t15 = TA.compute_indicators(w15, ddf if len(ddf) >= 2 else None)
    t1h = TA.compute_indicators(w1h)
    bias = TA.compute_multi_tf_bias(w15, w1h)
    price = float(w1h["close"].iloc[-1])
    # 24h change from 15m window (96 x 15m = 24h)
    j24 = max(0, len(w15)-97)
    prev24 = float(w15["close"].iloc[j24])
    change_pct = round((price/prev24 - 1)*100, 2)
    window24 = w15.tail(97)
    ticker = dict(timestamp=str(h_close), price=price, change_pct=change_pct,
                  high_24h=float(window24["high"].max()),
                  low_24h=float(window24["low"].min()))
    return dict(ticker=ticker, t15=t15, t1h=t1h, bias=bias, close=price,
                high=float(w1h["high"].iloc[-1]), low=float(w1h["low"].iloc[-1]),
                ts=str(h_close))


def run():
    d15 = BT.load("15m"); d1h = BT.load("1h"); d1d = BT.load("1d")
    d1d_dates = d1d["timestamp"].dt.date.tolist()

    TE.paper_state.update(dict(balance=START_BAL, position=None, trade_log=[],
                               total_pnl=0.0, wins=0, losses=0, fees_paid=0.0))
    config.TRADE_USDT = 50; config.LEVERAGE = 5

    n1h = len(d1h)
    start = n1h - N_CYCLES
    cycles = []
    print(f"=== LIVE PAPER DEMO | model={os.environ['LLM_MODEL']} ===")
    print(f"Simulating {N_CYCLES} hourly cycles ending {d1h['timestamp'].iloc[-1] + pd.Timedelta(hours=1)} UTC\n")

    for h_idx in range(start, n1h):
        pl = build_hour_payload(d15, d1h, d1d, d1d_dates, h_idx)
        if pl is None:
            continue
        ts = pl["ts"]; price = pl["close"]
        line = {"ts": ts, "price": price}

        # 1) manage open position first (SL/TP on this 1h candle)
        closed_note = ""
        if TE.paper_state["position"]:
            before = len(TE.paper_state["trade_log"])
            TE.paper_check_close(price, candle_high=pl["high"], candle_low=pl["low"])
            if len(TE.paper_state["trade_log"]) > before:
                for ev in TE.paper_state["trade_log"][before:]:
                    closed_note += f" | CLOSED {ev.get('reason','')} pnl={ev.get('pnl')}"
        line["manage"] = closed_note.strip(" |")

        # 2) if flat, consult the LLM brain (LIVE call)
        action = "HOLD (in position)" if TE.paper_state["position"] else None
        decision = None
        if not TE.paper_state["position"]:
            decision = BRAIN.analyze_market(
                ticker=pl["ticker"], technicals_15m=pl["t15"], technicals_1h=pl["t1h"],
                multi_tf_bias=pl["bias"], funding={}, open_interest={}, news=[])
            sig = (decision.get("signal") or "HOLD").upper()
            qual = decision.get("trade_quality") or "SKIP"
            conf = decision.get("confidence")
            reason = (decision.get("reasoning") or "")[:300]
            line.update(signal=sig, quality=qual, confidence=conf, reasoning=reason,
                        entry=decision.get("entry_price"), sl=decision.get("stop_loss"),
                        tp1=decision.get("take_profit_1"), tp2=decision.get("take_profit_2"))
            if sig in ("LONG", "SHORT") and qual not in ("C", "SKIP"):
                d2 = dict(decision); d2["entry_price"] = price  # market fill at close
                pos_before = TE.paper_state["position"]
                TE.paper_open_trade(d2, price)
                action = f"OPEN {sig} @ {price} (Q={qual}, conf={conf}%)" if (TE.paper_state["position"] and not pos_before) else f"{sig} signal but engine rejected"
            else:
                action = f"NO TRADE (signal={sig}, Q={qual})"
        line["action"] = action

        bal = TE.paper_state["balance"]; pos = TE.paper_state["position"]
        unreal = TE._realized_pnl(pos["side"], pos["entry"], price, pos["qty_left"]) if pos else 0.0
        line["equity"] = round(bal + unreal, 2)
        line["in_position"] = bool(pos)
        cycles.append(line)

        tstr = ts[5:16]
        rs = (line.get("reasoning") or "")[:150]
        print(f"[{tstr}] ${price:,.2f} | {action or line['manage']} | eq=${line['equity']:,.2f}")
        if rs:
            print(f"           brain: {rs}")

    # close any remaining position at last price
    if TE.paper_state["position"]:
        TE._paper_close_remaining(d1h["close"].iloc[-1], "DEMO_END_CLOSE")

    stats = TE.get_paper_stats()
    result = dict(
        mode=f"LIVE PAPER DEMO ({os.environ['LLM_MODEL']})",
        window_end=str(d1h["timestamp"].iloc[-1] + pd.Timedelta(hours=1)) + " UTC",
        cycles=len(cycles),
        start_balance=START_BAL, end_balance=stats["balance"],
        net_pnl=round(stats["balance"]-START_BAL, 2),
        return_pct=round((stats["balance"]/START_BAL-1)*100, 2),
        total_trades=stats["total_trades"], wins=stats["wins"], losses=stats["losses"],
        winrate=stats["winrate"], fees_paid=stats["fees_paid"],
        cycle_log=cycles, trade_log=TE.paper_state["trade_log"],
    )
    with open("demo_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("\n=== DEMO SUMMARY ===")
    print(json.dumps({k: v for k, v in result.items() if k not in ("cycle_log","trade_log")}, indent=2, default=str))
    print("trades:", len(result["trade_log"]))
    return result


if __name__ == "__main__":
    run()

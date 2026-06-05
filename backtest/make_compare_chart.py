import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
p = pd.read_csv("equity_curve.csv"); p["timestamp"]=pd.to_datetime(p["timestamp"])
l = pd.read_csv("llm_equity_curve.csv"); l["timestamp"]=pd.to_datetime(l["timestamp"])
fig, ax = plt.subplots(figsize=(11,5.2))
ax.plot(p["timestamp"], p["equity"], color="#c0392b", lw=1.4, label="Rules-Proxy (528 trades)")
ax.plot(l["timestamp"], l["equity"], color="#1e8449", lw=1.7, label="Real-LLM MiniMax-M2 (64 trades)")
ax.axhline(1000, color="#888", ls="--", lw=1, label="Start (1000)")
ax.set_title("Equity Curve — XAUUSDT Backtest (Jan–May 2026)\nReal-LLM vs Rules-Proxy", fontsize=13, fontweight="bold")
ax.set_ylabel("Equity (USDT)"); ax.legend(loc="lower left", fontsize=9)
ax.grid(alpha=0.25); fig.autofmt_xdate()
fig.tight_layout(); fig.savefig("compare_equity.png", dpi=140)
print("saved compare_equity.png")

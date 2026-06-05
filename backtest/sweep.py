import importlib, json
import run_backtest as BT
import trade_engine as TE
results=[]
for gate in [65,75,85]:
    BT.CONF_GATE=gate
    r=BT.run()
    results.append((gate, r["signals"], r["total_trades"], r["winrate"], r["net_pnl"], r["return_pct"], r["fees_paid"], r["max_drawdown_pct"]))
print("\n=== SENSITIVITY: confidence gate ===")
print(f"{'gate':>4} {'trades':>7} {'WR%':>6} {'netPnL$':>9} {'ret%':>7} {'fees$':>7} {'maxDD%':>7}")
for g,sig,tr,wr,pnl,ret,fee,dd in results:
    print(f"{g:>4} {tr:>7} {wr:>6} {pnl:>9} {ret:>7} {fee:>7} {dd:>7}")

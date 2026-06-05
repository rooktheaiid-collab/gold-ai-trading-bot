"""Render the Real-LLM vs Rules-Proxy comparison report to PDF (weasyprint, system python3)."""
import json, base64
from weasyprint import HTML

proxy = json.load(open("backtest_result.json"))
llm = json.load(open("llm_backtest_result.json"))
img_b64 = base64.b64encode(open("compare_equity.png","rb").read()).decode()

bd = llm["llm_signal_breakdown"]
filtered = bd["HOLD_SKIP"]
consulted = llm["consulted"]
filt_pct = round(filtered/consulted*100, 1)

def fmt(v, suf=""):
    return f"{v}{suf}"

rows = [
    ("Periode data", proxy["period"], llm["period"]),
    ("Sumber sinyal", "Rules proxy (hard rules)", "LLM MiniMax-M2 (judgment)"),
    ("Setup dievaluasi", f"{proxy['signals']} (saat flat)", f"{consulted} kandidat ditanya"),
    ("Trade dibuka", str(proxy["total_trades"]), str(llm["total_trades"])),
    ("Win rate", f"{proxy['winrate']}%", f"{llm['winrate']}%"),
    ("Wins / Losses", f"{proxy['wins']} / {proxy['losses']}", f"{llm['wins']} / {llm['losses']}"),
    ("Net PnL (USDT)", f"{proxy['net_pnl']}", f"{llm['net_pnl']}"),
    ("Return", f"{proxy['return_pct']}%", f"{llm['return_pct']}%"),
    ("Total fees (USDT)", f"{proxy['fees_paid']}", f"{llm['fees_paid']}"),
    ("Max drawdown", f"{proxy['max_drawdown_pct']}%", f"{llm['max_drawdown_pct']}%"),
    ("Saldo akhir (start 1000)", f"{proxy['end_balance']}", f"{llm['end_balance']}"),
]

trow = "".join(
    f"<tr><td class='lbl'>{a}</td><td>{b}</td><td class='hl'>{c}</td></tr>" for a,b,c in rows
)

html = f"""
<html><head><meta charset='utf-8'><style>
@page {{ size: A4; margin: 1.6cm; }}
body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color:#1c1c1c; font-size:11px; line-height:1.5; }}
h1 {{ font-size:21px; margin:0 0 2px; color:#0b3d2e; }}
h2 {{ font-size:14px; margin:18px 0 6px; color:#0b3d2e; border-bottom:2px solid #1e8449; padding-bottom:3px; }}
.sub {{ color:#666; font-size:11px; margin-bottom:10px; }}
table {{ width:100%; border-collapse:collapse; margin:6px 0; }}
th, td {{ border:1px solid #d8d8d8; padding:6px 8px; text-align:right; }}
th {{ background:#0b3d2e; color:#fff; text-align:right; font-size:11px; }}
th:first-child, td.lbl {{ text-align:left; }}
td.lbl {{ background:#f4f7f5; font-weight:600; width:34%; }}
td.hl {{ background:#eafaf1; font-weight:600; }}
.kpi {{ display:flex; gap:8px; margin:8px 0; }}
.card {{ flex:1; border:1px solid #d8d8d8; border-radius:8px; padding:8px 10px; background:#fafafa; }}
.card .big {{ font-size:18px; font-weight:700; color:#0b3d2e; }}
.card .lab {{ font-size:9.5px; color:#666; text-transform:uppercase; letter-spacing:.04em; }}
.note {{ background:#fff8e1; border-left:4px solid #f0ad4e; padding:8px 10px; border-radius:4px; margin:8px 0; font-size:10.5px; }}
.good {{ background:#eafaf1; border-left:4px solid #1e8449; padding:8px 10px; border-radius:4px; margin:8px 0; font-size:10.5px; }}
ul {{ margin:4px 0 4px 16px; padding:0; }} li {{ margin:2px 0; }}
.quote {{ background:#f4f7f5; border-left:3px solid #999; padding:5px 9px; margin:5px 0; font-size:10px; font-style:italic; color:#333; }}
img {{ width:100%; border:1px solid #ddd; border-radius:6px; margin-top:6px; }}
.foot {{ color:#999; font-size:9px; margin-top:14px; text-align:center; }}
</style></head><body>

<h1>XAUUSDT Backtest — Real-LLM vs Rules-Proxy</h1>
<div class='sub'>Gold AI Trading Bot &middot; Data: Binance Futures (UM) XAUUSDT, {llm['period']} &middot; LLM: MiniMax-M2.7-highspeed</div>

<div class='kpi'>
  <div class='card'><div class='lab'>Trade (LLM vs proxy)</div><div class='big'>{llm['total_trades']} <span style='font-size:11px;color:#888'>vs {proxy['total_trades']}</span></div></div>
  <div class='card'><div class='lab'>Win rate</div><div class='big'>{llm['winrate']}% <span style='font-size:11px;color:#888'>vs {proxy['winrate']}%</span></div></div>
  <div class='card'><div class='lab'>Return</div><div class='big'>{llm['return_pct']}% <span style='font-size:11px;color:#888'>vs {proxy['return_pct']}%</span></div></div>
  <div class='card'><div class='lab'>Max drawdown</div><div class='big'>{llm['max_drawdown_pct']}% <span style='font-size:11px;color:#888'>vs {proxy['max_drawdown_pct']}%</span></div></div>
</div>

<h2>Ringkasan: Apa yang LLM lakukan?</h2>
<div class='good'>
Dari <b>{consulted} setup teknikal</b> yang sebelumnya ditradein proxy, LLM <b>menolak {filtered} ({filt_pct}%)</b>
dan hanya entry di {bd['LONG']} LONG + {bd['SHORT']} SHORT. Hasilnya: jumlah trade turun drastis
(<b>{proxy['total_trades']} &rarr; {llm['total_trades']}</b>), win rate naik (<b>{proxy['winrate']}% &rarr; {llm['winrate']}%</b>),
biaya fee anjlok (<b>{proxy['fees_paid']} &rarr; {llm['fees_paid']} USDT</b>), dan kerugian nyaris hilang
(<b>{proxy['return_pct']}% &rarr; {llm['return_pct']}%</b>) dengan drawdown jauh lebih kecil.
</div>

<h2>Tabel Perbandingan</h2>
<table>
<tr><th>Metrik</th><th>Rules-Proxy</th><th>Real-LLM</th></tr>
{trow}
</table>

<h2>Kurva Equity</h2>
<img src='data:image/png;base64,{img_b64}'/>

<h2>Contoh "Judgment" LLM (yang proxy tidak punya)</h2>
<div class='quote'>"Trend bearish valid di semua TF, tapi StochRSI EXTREME OVERSOLD (K=7.81) &rarr; potensi bounce imminent &rarr; SKIP."</div>
<div class='quote'>"Bearish alignment kuat & MACD fresh cross turun, tapi StochRSI approaching oversold &rarr; quality C, HOLD."</div>
<div class='quote'>"Liquiditas sangat rendah (Minggu dini hari, 03:45 UTC); tanpa katalis & kondisi oversold, risiko fakeout tinggi &rarr; SKIP."</div>
<p style='font-size:10px;color:#555'>Proxy akan menradein semua setup itu (dan kena banyak SL). LLM menyaringnya pakai konteks tambahan: kondisi oversold/overbought ekstrem, waktu/likuiditas, dan kualitas struktur.</p>

<h2>Catatan & Keterbatasan (jujur)</h2>
<div class='note'>
<ul>
<li><b>Tanpa data funding / open-interest / berita historis</b> untuk periode ini &rarr; LLM mutusin dari harga + teknikal saja (sama keterbatasan dengan proxy). Edge sentimen berita BELUM teruji di sini.</li>
<li><b>Set kandidat dibatasi ke 528 titik entry proxy</b> ("apakah LLM menyaring lebih baik di peluang yang sama?"). LLM bisa saja menemukan setup lain yang tak dievaluasi di sini.</li>
<li><b>Entry = market fill di harga close</b> bar saat keputusan (bukan limit), konsisten dengan baseline proxy &rarr; tanpa look-ahead.</li>
<li>Masih sedikit rugi ({llm['return_pct']}%) & di bawah buy&hold (+{proxy['buyhold_return_pct']}%) untuk periode uptrend ini. Nilai utama LLM di sini = <b>manajemen risiko & anti-overtrading</b>, bukan profit agresif.</li>
<li>1 backtest, 1 aset, 5 bulan, model reasoning temperature 0.2 &rarr; bukan jaminan hasil live.</li>
</ul>
</div>

<div class='foot'>Generated by Viktor AI &middot; trade engine: real trade_engine.py (fee 0.04%/leg, partial TP1 50% + breakeven, SL-priority)</div>
</body></html>
"""
HTML(string=html).write_pdf("XAUUSDT_LLM_vs_Proxy_Report.pdf")
print("wrote XAUUSDT_LLM_vs_Proxy_Report.pdf")

import base64
img = open("_chart_b64.txt").read()
html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 22mm 18mm; @bottom-right {{ content: counter(page); color:#999; font-size:9pt; }} }}
* {{ font-family: 'Helvetica Neue', Arial, sans-serif; color:#1a1a1a; }}
body {{ font-size: 10.5pt; line-height: 1.5; }}
h1 {{ font-size: 22pt; margin:0 0 2pt; }}
h2 {{ font-size: 14pt; margin:22pt 0 6pt; border-bottom:2px solid #b8860b; padding-bottom:3pt; }}
.sub {{ color:#666; font-size:10pt; margin-bottom:4pt; }}
.tag {{ display:inline-block; background:#b8860b; color:#fff; font-size:8.5pt; padding:2pt 8pt; border-radius:10pt; letter-spacing:.5px; }}
table {{ border-collapse:collapse; width:100%; margin:6pt 0; font-size:10pt; }}
th,td {{ border:1px solid #ddd; padding:5pt 8pt; text-align:left; }}
th {{ background:#faf6ec; }}
td.r, th.r {{ text-align:right; }}
.callout {{ background:#fdf3f0; border-left:4px solid #d9663f; padding:8pt 12pt; margin:10pt 0; border-radius:4pt; }}
.good {{ background:#eef7ef; border-left:4px solid #3f9d52; padding:8pt 12pt; margin:10pt 0; border-radius:4pt; }}
.big {{ font-size:13pt; font-weight:bold; }}
.neg {{ color:#c0392b; font-weight:bold; }}
.pos {{ color:#2e7d32; font-weight:bold; }}
img {{ width:100%; border:1px solid #eee; border-radius:4pt; }}
small {{ color:#777; }}
</style></head><body>

<span class="tag">BACKTEST REPORT · DATA HISTORIS ASLI</span>
<h1>Gold AI Trading Bot — XAUUSDT</h1>
<div class="sub">Backtest pada data historis asli Binance Futures · Periode 3 Jan – 31 Mei 2026 (5 bulan)</div>

<div class="callout">
<b>⚠️ Catatan kejujuran (wajib dibaca).</b> Bot versi live mengambil keputusan dengan <b>LLM</b> di setiap siklus.
Memanggil LLM ~14.000 kali untuk backtest tidak realistis (butuh API key + biaya/waktu sangat besar).
Karena itu backtest ini memakai <b>proxy berbasis aturan deterministik</b> yang meniru <i>hard rules</i> &amp;
pipeline indikator bot (multi-timeframe trend alignment, RSI, MACD crossover, risk berbasis ATR).
Proxy ini <b>TIDAK</b> memodelkan pertimbangan diskresioner LLM maupun sentimen berita. Jadi hasil ini adalah
<b>sanity-check inti teknikal + trade engine pada data asli</b> — bukan performa persis bot yang digerakkan LLM.
</div>

<h2>1. Setup &amp; Metodologi</h2>
<table>
<tr><th>Item</th><th>Detail</th></tr>
<tr><td>Sumber data</td><td>Arsip resmi Binance Futures (UM) — XAUUSDT 15m / 1h / 1d</td></tr>
<tr><td>Periode</td><td>2026-01-03 → 2026-05-31 (14.496 candle 15m)</td></tr>
<tr><td>Modal awal (paper)</td><td>1.000 USDT · TRADE_USDT 50 · leverage 5× (notional ~250 USDT/trade)</td></tr>
<tr><td>Eksekusi</td><td>Pakai <b>trade_engine.py asli</b>: fill via high/low candle, taker fee 0,04%/sisi, partial TP1 50% + SL→breakeven, prioritas SL bila SL&amp;TP kena di candle sama</td></tr>
<tr><td>Indikator</td><td>Definisi sama dgn <b>technical_analysis.py</b> (pandas-ta), dihitung kausal pada deret penuh, dibaca walk-forward (tanpa look-ahead)</td></tr>
<tr><td>Aturan sinyal (proxy)</td><td>Bias multi-TF (15m &amp; 1h) harus selaras → trend EMA searah → MACD searah → RSI tidak overbought/oversold. SL = 1,2×ATR, TP1 = 1,5R, TP2 = 3R, gate confidence ≥ 65</td></tr>
<tr><td>Pivot</td><td>Classic pivots dari candle harian sebelumnya (standar intraday)</td></tr>
</table>

<h2>2. Hasil Utama (gate confidence ≥ 65)</h2>
<table>
<tr><th>Metrik</th><th class="r">Nilai</th><th>Metrik</th><th class="r">Nilai</th></tr>
<tr><td>Total trade</td><td class="r">528</td><td>Win rate</td><td class="r">39,2%</td></tr>
<tr><td>Menang / Kalah</td><td class="r">207 / 321</td><td>Reach TP2 penuh</td><td class="r">119</td></tr>
<tr><td>Reach TP1 (partial)</td><td class="r">182</td><td>Kena SL</td><td class="r">409</td></tr>
<tr><td>Saldo akhir</td><td class="r">907,17 USDT</td><td>Net PnL</td><td class="r"><span class="neg">−92,83 USDT</span></td></tr>
<tr><td>Return</td><td class="r"><span class="neg">−9,28%</span></td><td>Max drawdown</td><td class="r"><span class="neg">−9,28%</span></td></tr>
<tr><td><b>Total fee dibayar</b></td><td class="r"><b>105,60 USDT</b></td><td>Buy &amp; Hold (notional sama)</td><td class="r"><span class="pos">+4,87%</span></td></tr>
</table>

<div class="callout">
<b>Temuan kunci:</b> total <b>fee (105,6 USDT) lebih besar dari net loss (92,8 USDT)</b>. Artinya strategi ini
kurang-lebih <b>impas sebelum fee</b>, tapi <b>overtrading</b> (528 trade / 5 bulan ≈ 3–4 trade/hari) membuat biaya
menggerus akun. Win rate &lt;40% dengan struktur 1,5R/3R partial belum cukup memberi <i>edge</i> positif.
</div>

<img src="data:image/png;base64,{img}"/>
<small>Kuning = equity bot (proxy aturan). Abu putus-putus = Buy &amp; Hold notional sama. Bawah = harga XAUUSDT 15m.</small>

<h2>3. Sensitivitas — Seberapa Selektif Sinyal?</h2>
<p>Karena fee jadi biang kerugian, makin selektif (gate makin tinggi) → makin sedikit trade → kerugian makin kecil — tapi tetap negatif:</p>
<table>
<tr><th>Confidence gate</th><th class="r">Trade</th><th class="r">Win rate</th><th class="r">Net PnL</th><th class="r">Return</th><th class="r">Fee</th><th class="r">Max DD</th></tr>
<tr><td>≥ 65 (default)</td><td class="r">528</td><td class="r">39,2%</td><td class="r"><span class="neg">−92,83</span></td><td class="r">−9,28%</td><td class="r">105,60</td><td class="r">−9,28%</td></tr>
<tr><td>≥ 75</td><td class="r">486</td><td class="r">39,9%</td><td class="r"><span class="neg">−79,01</span></td><td class="r">−7,90%</td><td class="r">97,19</td><td class="r">−7,95%</td></tr>
<tr><td>≥ 85 (sangat selektif)</td><td class="r">202</td><td class="r">38,6%</td><td class="r"><span class="neg">−23,44</span></td><td class="r">−2,34%</td><td class="r">40,39</td><td class="r">−2,73%</td></tr>
</table>

<h2>4. Kesimpulan &amp; Rekomendasi</h2>
<div class="good">
<b>Yang sudah terbukti benar (kabar baik):</b>
<ul>
<li>Pipeline data → indikator → trade engine <b>jalan mulus pada 14.496 candle data asli</b>, tanpa crash, tanpa look-ahead.</li>
<li>Perbaikan dari audit (EMA200, Bollinger, pivot harian, partial TP1, fee, fill high/low) <b>semua berfungsi</b> di kondisi pasar nyata.</li>
<li>Risk management ketat: max drawdown hanya −9,3% meski 528 trade — SL &amp; sizing bekerja.</li>
</ul>
</div>
<div class="callout">
<b>Yang perlu jujur diakui:</b>
<ul>
<li>Inti teknikal <b>tanpa otak LLM &amp; filter berita</b> belum punya edge profit pada sampel 5 bulan ini (kalah vs buy &amp; hold).</li>
<li>Penyebab utama: <b>overtrading + fee</b> dan win rate &lt;40%. Justru di sinilah peran LLM: memfilter FOMO, grading kualitas A+/A/B, dan menghindari berita high-impact — hal yang <b>tidak</b> ditangkap proxy ini.</li>
</ul>
</div>
<p><b>Rekomendasi konkret:</b></p>
<ol>
<li><b>Kurangi frekuensi trade.</b> Tambah filter: jeda minimum antar-trade, hanya entry di sesi likuid, atau hanya saat ATR/volatilitas memadai. Lebih sedikit + lebih berkualitas &gt; banyak.</li>
<li><b>Naikkan ambang kualitas</b> ke ≥ 80–85 secara default, biar fee tidak menggerus.</li>
<li><b>Uji dengan LLM beneran</b> pada subset (mis. 200–300 sinyal kandidat), bukan tiap candle — untuk mengukur seberapa besar nilai tambah diskresi LLM vs proxy ini.</li>
<li><b>Walk-forward / out-of-sample</b> begitu data Juni+ tersedia, dan jalankan <b>paper trading live</b> dulu sebelum uang asli.</li>
</ol>

<div class="callout"><b>Disclaimer:</b> Backtest bukan jaminan profit masa depan. Hasil sangat bergantung asumsi fee, slippage (belum dimodelkan), dan periode sampel. Selalu mulai dari mode paper.</div>

</body></html>"""
open("report.html","w").write(html)
print("html bytes", len(html))

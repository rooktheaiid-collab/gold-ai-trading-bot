# 🟡 Gold AI Trading Bot

Bot trading **emas (XAUUSDT)** otomatis di **Binance Futures**, dengan otak **LLM** (AI)
yang menggabungkan analisa teknikal multi-timeframe + sentimen berita untuk mengambil
keputusan **LONG / SHORT / NO-TRADE**. Dilengkapi manajemen risiko, kontrol via Telegram,
dan kemampuan **belajar dari evaluasi performanya sendiri**.

> ⚠️ **Disclaimer:** Ini alat bantu, bukan jaminan profit. Trading futures berleverage
> berisiko tinggi. Mulai dari **mode paper** lalu **size kecil**. Tanggung jawab di tangan kamu.

---

## ✨ Fitur Utama

- **Otak AI fleksibel** — bisa pakai OpenAI, OpenRouter, Groq, DeepSeek, Gemini, NVIDIA NIM,
  Claude, atau model lokal (Ollama / LM Studio). Cukup ganti 4 baris di `.env`.
- **Analisa multi-timeframe** — 15m (utama) + 1h (konfirmasi tren) + 1d (pivot points).
  Indikator: EMA, RSI, MACD, Bollinger Bands, ATR, dll.
- **Sentimen berita** — tarik headline gold/Fed/inflasi (NewsAPI + fallback RSS) untuk konteks.
- **Manajemen risiko** — multi-TP (TP1 partial 50% → SL geser ke breakeven → TP2),
  clamp jarak SL, dan **circuit breaker harian** (batas trade/hari, max rugi harian, cooldown rugi beruntun).
- **Mode Paper & Live** — paper = simulasi penuh tanpa order nyata; live = order asli ke Binance
  (perilaku **identik** dengan paper).
- **Kontrol via Telegram** — notifikasi real-time + perintah `/status` `/pause` `/resume` `/close` dll.
- **Self-learning** — tiap tengah malam bot mengevaluasi trade-nya, menyuling "pelajaran",
  lalu menyuntikkannya ke prompt keputusan berikutnya.
- **Tahan restart** — posisi, balance, riwayat, & memori disimpan ke disk (atomic write).

---

## 🚀 Instalasi Cepat

### ⚡ Install 1 baris (paling cepat — Linux / macOS / VPS)
```bash
curl -fsSL https://raw.githubusercontent.com/rooktheaiid-collab/gold-ai-trading-bot/main/bootstrap.sh | bash
```
Otomatis: pasang prasyarat (git/python), clone repo ke `~/gold-ai-trading-bot`, bikin venv,
install dependency, siapkan `.env`, lalu kasih tau langkah terakhir. Setelahnya tinggal:
```bash
cd ~/gold-ai-trading-bot && source venv/bin/activate
python setup.py        # wizard isi API key
bash run.sh            # jalankan (default PAPER = simulasi)
```
> Catatan: one-liner ini ambil `bootstrap.sh` lewat URL `raw.githubusercontent.com`,
> jadi hanya jalan selama repo **public**. Kalau repo kamu jadikan private, pakai cara
> clone manual di bawah (atau ganti URL pakai token).

### 🐳 Docker (1 perintah, anti ribet venv)
```bash
git clone https://github.com/rooktheaiid-collab/gold-ai-trading-bot.git
cd gold-ai-trading-bot
cp .env.example .env && nano .env   # isi API key (atau jalankan: python setup.py)
docker compose up -d                # build + jalan di background, auto-restart
docker compose logs -f              # pantau log   |   docker compose down = stop
```
State (`bot_memory/`) & `.env` disimpan di host, jadi aman saat container dibuild ulang.
Telegram pakai long-polling — tidak perlu buka port.

### Manual — Linux / macOS / VPS
```bash
bash install.sh        # buat venv + install deps + siapkan .env
source venv/bin/activate
python setup.py        # wizard konfigurasi (isi API key, dll)
bash run.sh            # jalankan bot
```

### Windows
```bat
install.bat            REM buat venv + install deps + siapkan .env
venv\Scripts\activate.bat
python setup.py
python main.py
```

### Manual (kalau mau atur sendiri)
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # lalu edit isi .env
python main.py
```

> **Python 3.10–3.12 disarankan.** Catatan dependency: `pandas-ta 0.3.x` butuh `numpy < 2`
> (sudah dikunci di `requirements.txt`). Jangan upgrade numpy ke 2.x tanpa juga upgrade pandas-ta ke ≥0.4.

---

## ⚙️ Konfigurasi (`.env`)

Cara termudah: **`python setup.py`** (wizard menu, ada tes koneksi Telegram). Atau edit `.env` manual.
Semua opsi ada di **`.env.example`**. Yang penting:

| Variabel | Arti | Default |
|---|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | API Binance (LIVE wajib enable Futures) | — |
| `LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | otak AI (lihat contoh provider di `.env.example`) | openai / gpt-4o |
| `NEWS_API_KEY` | NewsAPI (opsional, kosong = lewati berita) | — |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | notifikasi + kontrol (opsional) | kosong = off |
| `PAPER_TRADING` | `True` = simulasi (AMAN), `False` = order nyata | `True` |
| `TRADE_USDT` / `LEVERAGE` | modal per trade & leverage | 50 / 5 |
| `MAX_TRADES_PER_DAY` / `MAX_DAILY_LOSS_USDT` / `LOSS_COOLDOWN_TRADES` | circuit breaker harian | 10 / 50 / 3 |
| `MAX_SL_DISTANCE_PCT` | tolak SL kejauhan (0 = off) | 0.02 |
| `MIN_CONFIDENCE` / `MIN_QUALITY` | filter eksekusi sinyal (confidence & kualitas) | 65 / A+,A |
| `MIN_RR` | tolak Risk:Reward (entry→TP1) di bawah ini (0 = off) | 1.2 |
| `SLIPPAGE_BPS` | simulasi slippage/spread paper (bps, 0 = ideal) | 2 |
| `TRADING_HOURS_UTC` | filter sesi: jam entry UTC (overlap London-NY). Format `12-17` atau `7-10,12-17`; kosong/`all` = semua jam | 12-17 |
| `REGIME_FILTER` | tolak entry lawan tren 1h (LONG saat 1h bearish / SHORT saat 1h bullish) | True |
| `MIN_ADX` | minimal ADX-14 (15m) untuk konfirmasi tren; 0 = off (backtest: over-filter) | 0 |
| `USE_CLOSED_CANDLES` | analisa candle yang sudah close (anti-repaint) | True |
| `AUTO_DAILY_EVAL` / `EVAL_TZ_OFFSET_HOURS` | evaluasi harian otomatis & zona waktu | True / 7 (WIB) |
| `SCAN_INTERVAL_SEC` | jeda scan market (detik) | 60 |

---

## 📲 Telegram (opsional tapi recommended)

1. Buat bot di **@BotFather** → dapat **token**.
2. Ambil **Chat ID** kamu di **@userinfobot**.
3. Isi `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (via `setup.py` atau `.env`).

Perintah yang tersedia:

| Perintah | Fungsi |
|---|---|
| `/status`, `/posisi` | posisi & PnL terkini |
| `/report` | ringkasan performa |
| `/evaluasi` | evaluasi performa hari ini (preview, tidak disimpan) |
| `/pelajaran` (`/lessons`) | pelajaran yang sudah dikumpulkan bot |
| `/pause`, `/resume` | jeda / lanjutkan buka posisi baru |
| `/close` | tutup paksa posisi terbuka di harga pasar |
| `/settings`, `/help` | konfigurasi & bantuan |

Notifikasi otomatis: posisi dibuka, TP1 kena (+ SL→breakeven), posisi ditutup, circuit breaker aktif.

---

## 🔴 Beralih ke LIVE (uang nyata)

1. **Uji di Binance Testnet** atau dengan **size sangat kecil** dulu.
2. API key Binance harus **Enable Futures** (disarankan IP whitelist).
3. Set `PAPER_TRADING=False` di `.env`.
4. Pastikan `TRADE_USDT` × `LEVERAGE` menghasilkan qty di atas minimum exchange.
5. Pantau log + Telegram di hari-hari pertama.

> Mode live mereplikasi perilaku paper persis: TP1 partial → breakeven → TP2, dengan
> guard anti dobel-posisi (cek ledger **dan** posisi nyata di exchange) dan rekonsiliasi tiap cycle.

---

## 🖥️ Jalan 24/7 di VPS (systemd)

Buat `/etc/systemd/system/goldbot.service`:
```ini
[Unit]
Description=Gold AI Trading Bot
After=network-online.target

[Service]
WorkingDirectory=/path/ke/gold_bot
ExecStart=/path/ke/gold_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Lalu:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now goldbot
sudo journalctl -u goldbot -f      # lihat log live
```
Alternatif ringan: `tmux` / `screen` / `nohup python main.py &`.

---

## 🧱 Struktur Proyek

| File | Peran |
|---|---|
| `main.py` | loop utama — orkestrasi tiap cycle (fetch → analisa → keputusan → eksekusi) |
| `config.py` | semua setting (baca dari `.env`) |
| `data_fetcher.py` | ambil harga/candle & berita dari Binance + NewsAPI/RSS |
| `technical_analysis.py` | hitung indikator teknikal multi-timeframe |
| `llm_brain.py` | kirim konteks ke LLM, ambil keputusan trading |
| `trade_engine.py` | eksekusi paper & live (multi-TP, circuit breaker, state persist) |
| `bot_memory.py` | memori self-learning (lessons + riwayat evaluasi) |
| `daily_eval.py` | evaluasi performa harian → menyuling pelajaran baru |
| `telegram_bot.py` | menu kontrol Telegram (long-poll) |
| `telegram_notifier.py` | format & kirim notifikasi |
| `setup.py` | wizard konfigurasi interaktif |
| `install.sh` / `install.bat` / `run.sh` | installer & runner |

Folder `bot_memory/` (dibuat otomatis) menyimpan `paper_state.json`, `lessons.json`,
`evaluations.json`. `backtest/` berisi tooling backtest historis.

---

## 🧰 Troubleshooting

- **`ImportError: cannot import name 'NaN' from 'numpy'`** → numpy 2.x tak kompatibel pandas-ta 0.3.x.
  Pakai `pip install -r requirements.txt` (numpy sudah dikunci <2), atau upgrade `pandas-ta>=0.4`.
- **Order ditolak (qty/price)** → naikkan `TRADE_USDT`/`LEVERAGE` agar qty ≥ minimum, atau cek tickSize.
- **`HTTP 451` / region blocked** → Binance memblokir sebagian region/IP. Pakai VPS region yang didukung.
- **LLM error 401/quota** → cek `LLM_API_KEY` & saldo provider. Bisa ganti provider via `.env`.
- **Telegram diam** → pastikan token+chat id benar dan kamu sudah `/start` bot kamu.

---

## 🔒 Keamanan

- Jangan commit `.env` (sudah di `.gitignore`). Jangan share API key.
- Gunakan key dengan permission seminimal mungkin + IP whitelist.
- **Revoke** API key apa pun yang pernah tersebar.

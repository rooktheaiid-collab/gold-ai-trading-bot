"""
Gold Trading Bot - Configuration
=================================
Set your API keys via environment variables or .env file
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Binance ──────────────────────────────────────────────────────────────────
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "YOUR_BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "YOUR_BINANCE_API_SECRET")

# ── LLM (BEBAS GANTI MODEL / PROVIDER) ───────────────────────────────────────
# Bot ini bisa pakai LLM apa saja. Cukup atur 4 hal di bawah lewat .env:
#
#   LLM_PROVIDER  : "openai" (default, OpenAI-compatible) atau "anthropic" (native)
#   LLM_BASE_URL  : URL endpoint API (kosongkan utk default provider)
#   LLM_API_KEY   : API key provider tsb
#   LLM_MODEL     : nama model
#
# Provider "openai" mencakup SEMUA layanan yang OpenAI-compatible:
#   • OpenAI       → base_url=https://api.openai.com/v1            model=gpt-4o, gpt-4o-mini, o3, ...
#   • OpenRouter   → base_url=https://openrouter.ai/api/v1         model=anthropic/claude-3.7-sonnet, ...
#   • Groq         → base_url=https://api.groq.com/openai/v1       model=llama-3.3-70b-versatile, ...
#   • DeepSeek     → base_url=https://api.deepseek.com             model=deepseek-chat
#   • Together AI  → base_url=https://api.together.xyz/v1          model=meta-llama/Llama-3.3-70B-...
#   • Google Gemini→ base_url=https://generativelanguage.googleapis.com/v1beta/openai/   model=gemini-2.0-flash
#   • Lokal (LM Studio / Ollama) → base_url=http://localhost:11434/v1   model=llama3.1, qwen2.5, ...
#
# Provider "anthropic" → pakai SDK native Anthropic (Claude).
#   LLM_BASE_URL boleh dikosongkan; LLM_API_KEY = Anthropic key.

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL    = os.getenv("LLM_MODEL", "gpt-4o")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1200"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# LLM_API_KEY = key utama. Fallback ke ANTHROPIC_API_KEY / OPENAI_API_KEY demi kompatibilitas lama.
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") \
              or os.getenv("ANTHROPIC_API_KEY", "YOUR_LLM_API_KEY")

# Alias lama (dipertahankan supaya kode/env lama tetap jalan)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", LLM_API_KEY)

# ── News (NewsAPI.org — free tier OK) ───────────────────────────────────────
NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "YOUR_NEWSAPI_KEY")
NEWS_QUERIES       = ["gold price", "XAUUSD", "gold market", "federal reserve", "inflation"]

# ── Trading Symbol ───────────────────────────────────────────────────────────
# Catatan: XAUUSDT = perpetual "TradFi" gold di Binance Futures (rilis Jan 2026).
# Mungkin dibatasi di sebagian region. Alternatif gold-token: PAXGUSDT.
SYMBOL             = os.getenv("SYMBOL", "XAUUSDT")   # Gold/USDT perpetual futures di Binance
TIMEFRAME          = "15m"       # Candle utama: 15 menit
HIGHER_TF          = "1h"        # Konfirmasi higher timeframe
DAILY_TF           = "1d"        # Untuk perhitungan Pivot Points (standar intraday)

# Jumlah candle yang diambil. WAJIB >= 250 supaya EMA200 valid (bukan NaN).
CANDLE_LIMIT       = 300

# ── Risk Management ──────────────────────────────────────────────────────────
TRADE_USDT         = float(os.getenv("TRADE_USDT", "50"))     # Modal per trade (USDT)
LEVERAGE           = int(os.getenv("LEVERAGE", "5"))          # Leverage (5x = moderate)
STOP_LOSS_PCT      = float(os.getenv("STOP_LOSS_PCT", "0.005"))    # 0.5% stop loss dari entry
TAKE_PROFIT_PCT    = float(os.getenv("TAKE_PROFIT_PCT", "0.015"))  # 1.5% take profit (RR 1:3)
MAX_OPEN_TRADES    = 1           # Maksimum posisi terbuka bersamaan

# Tolak setup dengan SL kejauhan (risiko/trade membengkak). 0 = nonaktif.
MAX_SL_DISTANCE_PCT = float(os.getenv("MAX_SL_DISTANCE_PCT", "0.02"))   # 2% dari entry

# Risk:Reward minimum (diukur entry→TP1). Tolak setup di bawah ini. 0 = nonaktif.
MIN_RR = float(os.getenv("MIN_RR", "1.2"))

# ── Filter Sinyal (gating eksekusi) ──────────────────────────────────────────
# Hanya eksekusi sinyal dengan confidence & kualitas minimum. Dipindah dari
# hardcode di main.py agar bisa diatur lewat .env & konsisten dengan param lain.
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "65"))               # 0-100
MIN_QUALITY    = set(q.strip() for q in os.getenv("MIN_QUALITY", "A+,A").split(",") if q.strip())

# ── Slippage / spread model (paper) ──────────────────────────────────────────
# Simulasi biaya eksekusi nyata: entry & exit diisi sedikit lebih buruk dari
# harga ideal (basis poin). 0 = isi persis (idealis). 2 bps = 0.02%.
SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", "2"))

# ── Filter Sesi / Jam Trading (time-of-day) ──────────────────────────────────
# Gold paling likuid & terarah saat overlap London–New York (12:00–17:00 UTC =
# 19:00–24:00 WIB); sesi Asia cenderung choppy. Riset + backtest cache LLM
# menunjukkan membatasi entry ke jam overlap membalik hasil dari rugi → untung.
# Format: rentang jam UTC [start-end) dipisah koma, mis. "12-17" atau
# "7-10,12-17". Kosong / "all" = semua jam (filter nonaktif).
def _parse_hours(spec: str):
    spec = (spec or "").strip().lower()
    if not spec or spec in ("all", "*", "24h"):
        return None  # None = semua jam diizinkan
    hours = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            hours |= set(range(a, b)) if a <= b else (set(range(a, 24)) | set(range(0, b)))
        else:
            hours.add(int(part))
    return frozenset(h % 24 for h in hours)

TRADING_HOURS_UTC = _parse_hours(os.getenv("TRADING_HOURS_UTC", "12-17"))

# ── Filter Regime (tren HTF + kekuatan ADX) ──────────────────────────────────
# Gold itu aset TRENDING, bukan mean-reverting. Riset: jangan lawan tren HTF &
# hindari pasar choppy (ADX rendah). 2 gate ini menyaring sinyal lawan-arah &
# kondisi sideways yang jadi sumber loss utama.
#  • REGIME_FILTER: tolak LONG saat tren 1h BEARISH / SHORT saat 1h BULLISH.
#  • MIN_ADX: minimal ADX-14 (15m) untuk konfirmasi ada tren. 0 = nonaktif.
# CATATAN: pada backtest cache (sampel kecil di window overlap), ADX gate justru
# over-filter & menurunkan hasil → default 0 (OFF). Regime filter default ON
# (netral di backtest, guardrail anti lawan-tren, didukung riset).
REGIME_FILTER = os.getenv("REGIME_FILTER", "True").lower() == "true"
MIN_ADX = float(os.getenv("MIN_ADX", "0"))

# ── Circuit Breakers (safety net harian) ─────────────────────────────────────
# Bot berhenti buka posisi baru hari itu kalau salah satu batas tersentuh.
MAX_TRADES_PER_DAY  = int(os.getenv("MAX_TRADES_PER_DAY", "10"))        # 0 = tak terbatas
MAX_DAILY_LOSS_USDT = float(os.getenv("MAX_DAILY_LOSS_USDT", "50"))     # 0 = nonaktif
LOSS_COOLDOWN_TRADES = int(os.getenv("LOSS_COOLDOWN_TRADES", "3"))      # rugi beruntun N → jeda hari itu

# Analisa hanya di candle yang sudah CLOSED (hindari repainting sinyal).
USE_CLOSED_CANDLES  = os.getenv("USE_CLOSED_CANDLES", "True").lower() == "true"

# ── Bot Mode ─────────────────────────────────────────────────────────────────
# True = simulasi (paper), False = live order ke Binance. Default AMAN = paper.
PAPER_TRADING      = os.getenv("PAPER_TRADING", "True").lower() == "true"
SCAN_INTERVAL_SEC  = int(os.getenv("SCAN_INTERVAL_SEC", "60"))   # Scan market tiap N detik

# ── Self-learning / Evaluasi harian ──────────────────────────────────────────
AUTO_DAILY_EVAL    = os.getenv("AUTO_DAILY_EVAL", "True").lower() == "true"  # auto evaluasi tiap tengah malam
EVAL_TZ_OFFSET_HOURS = int(os.getenv("EVAL_TZ_OFFSET_HOURS", "7"))           # 7 = WIB (tengah malam waktu lokal)

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE           = "gold_bot.log"

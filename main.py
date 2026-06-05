"""
Gold Trading Bot - Main Loop
==============================
Entry point: jalankan dengan `python main.py`

Mode:
  PAPER_TRADING = True   → Simulasi (tidak ada order nyata)
  PAPER_TRADING = False  → Live order ke Binance Futures

DISCLAIMER: Bot ini untuk edukasi. Trading futures berisiko tinggi.
"""

import time
import logging
import json
import threading
from datetime import datetime, timezone
from colorama import Fore, Style, init as colorama_init

import config
from data_fetcher import (
    get_binance_client, fetch_ohlcv, fetch_ticker,
    fetch_open_interest, fetch_funding_rate, fetch_gold_news,
)
from technical_analysis import compute_indicators, compute_multi_tf_bias
from llm_brain import analyze_market
import trade_engine as TE
from trade_engine import (
    paper_open_trade, paper_check_close, get_paper_stats,
    live_open_trade, paper_force_close,
    live_manage, live_force_close,
)

# Optional add-ons (Telegram + self-learning). Bot runs fine without them.
try:
    import daily_eval
except Exception:
    daily_eval = None
try:
    import telegram_bot
except Exception:
    telegram_bot = None
try:
    import telegram_notifier
except Exception:
    telegram_notifier = None

colorama_init(autoreset=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def banner():
    print(Fore.YELLOW + """
╔══════════════════════════════════════════════════════╗
║        🥇  GOLD AI TRADING BOT  (XAUUSDT)          ║
║       LLM Brain × Binance Futures × TA Engine       ║
║  Mode: """ + ("📋 PAPER" if config.PAPER_TRADING else "🔴 LIVE") + f"""  |  Interval: {config.SCAN_INTERVAL_SEC}s  |  Symbol: {config.SYMBOL}  ║
╚══════════════════════════════════════════════════════╝
""" + Style.RESET_ALL)


def print_decision(decision: dict, ticker: dict):
    sig = decision.get("signal", "HOLD")
    conf = decision.get("confidence", 0)
    quality = decision.get("trade_quality", "?")

    color = Fore.GREEN if sig == "LONG" else Fore.RED if sig == "SHORT" else Fore.YELLOW

    print(color + f"""
┌─────────────────────────────────────────────┐
│  🤖 LLM DECISION @ {datetime.now().strftime('%H:%M:%S')}              │
│  Signal      : {sig:<10}  Confidence: {conf}%    │
│  Quality     : {quality:<6}    Price: ${ticker['price']:,.2f}        │
│  Entry       : {str(decision.get('entry_price','N/A')):<12}                    │
│  Stop Loss   : {str(decision.get('stop_loss','N/A')):<12}                    │
│  Take Profit1: {str(decision.get('take_profit_1','N/A')):<12}                    │
│  Take Profit2: {str(decision.get('take_profit_2','N/A')):<12}                    │
│  R:R         : {str(decision.get('risk_reward','N/A')):<12}                    │
│  Bias        : {decision.get('market_bias','N/A'):<10}                       │
│  Sentiment   : {decision.get('news_sentiment','N/A'):<10}                     │
└─────────────────────────────────────────────┘
💬 {decision.get('reasoning','')[:120]}
""" + Style.RESET_ALL)

    warnings = decision.get("warnings", [])
    for w in warnings:
        print(Fore.MAGENTA + f"  ⚠️  {w}" + Style.RESET_ALL)


def run_cycle(client, state: dict) -> dict:
    """
    Satu siklus analisa + keputusan + eksekusi.
    `state` menyimpan cache: last_news_fetch (float) dan news_cache (list).
    Returns: state yang sudah diperbarui.
    """
    now = time.time()

    # ── 1. Fetch Market Data ──────────────────────────────────────────────────
    ticker  = fetch_ticker(client, config.SYMBOL)
    df_15m  = fetch_ohlcv(client, config.SYMBOL, config.TIMEFRAME, limit=config.CANDLE_LIMIT)
    df_1h   = fetch_ohlcv(client, config.SYMBOL, config.HIGHER_TF, limit=config.CANDLE_LIMIT)
    df_1d   = fetch_ohlcv(client, config.SYMBOL, config.DAILY_TF,  limit=30)   # utk pivot
    oi      = fetch_open_interest(client, config.SYMBOL)
    fr      = fetch_funding_rate(client, config.SYMBOL)

    # ── 2. Technical Analysis ─────────────────────────────────────────────────
    # Anti-repainting: analisa indikator HANYA di candle yang sudah CLOSED
    # (buang candle terakhir yang masih terbentuk). Candle penuh tetap dipakai
    # untuk cek SL/TP intra-candle di bawah.
    use_closed = getattr(config, "USE_CLOSED_CANDLES", True)
    a15 = df_15m.iloc[:-1] if (use_closed and len(df_15m) > 1) else df_15m
    a1h = df_1h.iloc[:-1]  if (use_closed and len(df_1h)  > 1) else df_1h
    ta_15m       = compute_indicators(a15, daily_df=df_1d)
    ta_1h        = compute_indicators(a1h, daily_df=df_1d)
    multi_bias   = compute_multi_tf_bias(a15, a1h)

    # ── 3. Fetch News (tiap 10 menit, sisanya pakai CACHE asli) ───────────────
    if now - state["last_news_fetch"] > 600 or not state["news_cache"]:
        state["news_cache"] = fetch_gold_news(max_articles=8)
        state["last_news_fetch"] = now
    news = state["news_cache"]   # selalu kirim berita terakhir ke LLM

    # ── 4. LLM Analysis ───────────────────────────────────────────────────────
    decision = analyze_market(ticker, ta_15m, ta_1h, multi_bias, fr, oi, news)

    # ── 5. Display + simpan keputusan terakhir (untuk /sinyal Telegram) ───────
    print_decision(decision, ticker)
    if telegram_bot is not None:
        try:
            telegram_bot.set_last_decision(decision, ticker["price"], ticker.get("timestamp"))
        except Exception:
            pass

    # ── 5b. Manual force-close dari Telegram (/close) ─────────────────────────
    manual_closed = False
    if telegram_bot is not None and telegram_bot.control.get("force_close"):
        telegram_bot.control["force_close"] = False
        if TE.paper_state["position"]:
            if config.PAPER_TRADING:
                ev = paper_force_close(ticker["price"])
            else:
                ev = live_force_close(client, ticker["price"])
            logger.info(f"[{'PAPER' if config.PAPER_TRADING else 'LIVE'}] Manual close: {ev}")
            manual_closed = True
            if ev and telegram_notifier is not None:
                _notify(telegram_notifier.fmt_close(ev))

    # ── 6. Cek penutupan posisi existing ──────────────────────────────────────
    if config.PAPER_TRADING:
        # Pakai high/low candle 15m terakhir agar wick yang menyentuh SL/TP terdeteksi
        last_c = df_15m.iloc[-1]
        hit = paper_check_close(ticker["price"],
                                candle_high=float(last_c["high"]),
                                candle_low=float(last_c["low"]))
    else:
        # Live: rekonsiliasi dengan exchange (deteksi TP1 fill / SL / TP2)
        hit = live_manage(client, ticker["price"])

    if hit:
        logger.info(f"[{'PAPER' if config.PAPER_TRADING else 'LIVE'}] Position event: {hit}")
        if telegram_notifier is not None:
            if hit == "TP1_PARTIAL":
                _notify("🟡 *TP1 tercapai* — sebagian profit dibukukan, SL → breakeven.")
            else:
                last_ev = TE.paper_state["trade_log"][-1] if TE.paper_state["trade_log"] else {}
                _notify(telegram_notifier.fmt_close(last_ev))

    # ── 7. Execute Signal ─────────────────────────────────────────────────────
    min_confidence = 65
    min_quality    = {"A+", "A"}

    is_signal = (
        decision.get("signal") in ("LONG", "SHORT")
        and decision.get("confidence", 0) >= min_confidence
        and decision.get("trade_quality") in min_quality
    )

    if is_signal and not manual_closed:
        # Gate 1: dijeda manual via Telegram
        paused = telegram_bot is not None and telegram_bot.control.get("paused")
        # Gate 2: circuit breaker risiko harian
        blocked, reason = _daily_risk_block()
        if paused:
            logger.info("[SKIP] Trading dijeda (Telegram /pause).")
        elif blocked:
            logger.warning(f"[CIRCUIT BREAKER] Entry diblok: {reason}")
            if not state.get("cb_notified"):
                _notify(f"🛑 *Circuit breaker aktif*: {reason}. Tidak buka posisi baru hari ini.")
                state["cb_notified"] = True
        else:
            had_pos = TE.paper_state["position"] is not None
            if config.PAPER_TRADING:
                paper_open_trade(decision, ticker["price"])
            else:
                live_open_trade(client, decision, ticker["price"])
            # Notifikasi kalau posisi benar-benar terbuka
            if (not had_pos and TE.paper_state["position"] is not None
                    and telegram_notifier is not None):
                _notify(telegram_notifier.fmt_open(decision, ticker["price"]))

    # ── 8. Paper Stats ────────────────────────────────────────────────────────
    if config.PAPER_TRADING:
        stats = get_paper_stats()
        print(Fore.CYAN + f"""
📊 PAPER STATS  Balance={stats['balance']} USDT | PnL={stats['total_pnl']:+.2f} | 
   Trades={stats['total_trades']} (W:{stats['wins']} L:{stats['losses']}) | WR={stats['winrate']}%
   Position: {stats['position']}
""" + Style.RESET_ALL)

    return state


def _notify(text):
    """Push to Telegram if the notifier is configured (no-op otherwise)."""
    if telegram_notifier is not None:
        try:
            telegram_notifier.notify(text)
        except Exception:
            pass


def _daily_risk_block():
    """Circuit breaker: return (blocked: bool, reason: str) berdasarkan trade hari ini."""
    if daily_eval is None:
        return False, ""
    try:
        today = daily_eval.local_today()
        trades = daily_eval._trades_on(today, TE.paper_state.get("trade_log", []),
                                       tz_offset=config.EVAL_TZ_OFFSET_HOURS)
    except Exception:
        return False, ""

    n = len(trades)
    if getattr(config, "MAX_TRADES_PER_DAY", 0) and n >= config.MAX_TRADES_PER_DAY:
        return True, f"sudah {n} trade hari ini (limit {config.MAX_TRADES_PER_DAY})"

    net = sum((t.get("pnl") if t.get("pnl") is not None else t.get("pnl_final_leg", 0)) or 0
              for t in trades)
    if getattr(config, "MAX_DAILY_LOSS_USDT", 0) and net <= -abs(config.MAX_DAILY_LOSS_USDT):
        return True, f"rugi harian {net:+.2f} USDT (limit -{config.MAX_DAILY_LOSS_USDT})"

    # Rugi beruntun di hari ini
    cd = getattr(config, "LOSS_COOLDOWN_TRADES", 0)
    if cd:
        streak = 0
        for t in reversed(trades):
            pnl = t.get("pnl") if t.get("pnl") is not None else t.get("pnl_final_leg", 0)
            if (pnl or 0) < 0:
                streak += 1
            else:
                break
        if streak >= cd:
            return True, f"{streak} kekalahan beruntun (cooldown {cd})"
    return False, ""


def check_midnight_eval(state):
    """Run the daily evaluation once when the local date rolls over (tengah malam)."""
    if not (config.AUTO_DAILY_EVAL and daily_eval is not None):
        return
    today = daily_eval.local_today()
    last = state.get("last_eval_date")
    if last is None:
        state["last_eval_date"] = today
        return
    if today > last:
        day_done = last   # the day that just ended
        logger.info(f"🕛 Tengah malam — menjalankan evaluasi harian untuk {day_done}...")
        try:
            ev = daily_eval.evaluate_day(day_done, send_fn=_notify)
            logger.info(f"Evaluasi {day_done} selesai. Pelajaran di memori: {ev.get('n_lessons_total')}")
        except Exception as e:
            logger.error(f"Auto-eval gagal: {e}", exc_info=True)
        state["last_eval_date"] = today
        state["cb_notified"] = False   # reset notifikasi circuit breaker untuk hari baru


def main():
    banner()
    client = get_binance_client()
    logger.info(f"Bot started | Symbol={config.SYMBOL} | Mode={'PAPER' if config.PAPER_TRADING else 'LIVE'}")

    # Muat state tersimpan (balance/posisi/riwayat) agar tahan restart VPS
    TE.load_state()

    # Live: rekonsiliasi ledger dgn posisi NYATA di exchange saat startup
    if not config.PAPER_TRADING:
        try:
            amt = abs(TE.live_position_amt(client, config.SYMBOL))
            led = TE.paper_state.get("position")
            if led and amt < led["qty"] * 0.05:
                logger.warning("[LIVE] Ledger punya posisi tapi exchange FLAT → bersihkan ledger.")
                TE.paper_state["position"] = None
                TE.save_state()
            elif not led and amt > 0:
                logger.warning(f"[LIVE] Exchange punya posisi ({amt}) tapi ledger kosong. "
                               "Bot tidak akan mengelolanya (buka via bot agar terttrack).")
        except Exception as e:
            logger.warning(f"[LIVE] Rekonsiliasi startup gagal: {e}")

    # Start Telegram control menu (background long-poll) if configured
    if telegram_bot is not None and getattr(telegram_bot, "BOT_TOKEN", ""):
        threading.Thread(target=telegram_bot.run, daemon=True).start()
        logger.info("Telegram control menu aktif.")
        if config.AUTO_DAILY_EVAL:
            _notify("🤖 *Gold Bot aktif.* Auto-evaluasi harian: ON (tiap tengah malam WIB).")

    state = {"last_news_fetch": 0.0, "news_cache": [],
             "last_eval_date": daily_eval.local_today() if daily_eval else None,
             "cb_notified": False}
    cycle = 0

    while True:
        cycle += 1
        logger.info(f"── Cycle {cycle} ──────────────────────────────────")
        try:
            state = run_cycle(client, state)
        except KeyboardInterrupt:
            logger.info("Bot dihentikan oleh user.")
            break
        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)

        check_midnight_eval(state)
        logger.info(f"Menunggu {config.SCAN_INTERVAL_SEC}s untuk siklus berikutnya...")
        time.sleep(config.SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    main()

"""
Gold Trading Bot — Telegram Control Interface
=============================================
Registers a command menu (the "/" list) and serves an inline-keyboard menu so
the user can monitor & control the bot from Telegram. Long-polls getUpdates, so
it works on any VPS without a public webhook.

Wire-up:
  - main.py should read `telegram_bot.control["paused"]` before opening trades,
    and call `telegram_bot.set_last_decision(decision, price, ts)` each cycle.
  - run the poller in a background thread:  threading.Thread(target=telegram_bot.run, daemon=True).start()
"""
import os, time, logging, requests
import config
import trade_engine as TE
try:
    import daily_eval as EVAL
    import bot_memory as MEM
except Exception:
    EVAL = MEM = None

logger = logging.getLogger("tg_bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = str(os.getenv("TELEGRAM_CHAT_ID", ""))
_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# shared runtime state (main loop reads these)
control = {"paused": False, "force_close": False}
_last = {"decision": None, "price": None, "ts": None}


def set_last_decision(decision, price, ts):
    _last.update(decision=decision, price=price, ts=ts)


# ── Command list shown in Telegram's "/" menu ────────────────────────────────
COMMANDS = [
    ("start",    "Mulai & tampilkan menu utama"),
    ("status",   "Status bot (aktif/jeda, mode, uptime)"),
    ("saldo",    "Saldo akun & PnL"),
    ("posisi",   "Posisi terbuka saat ini"),
    ("sinyal",   "Sinyal & analisa terakhir"),
    ("riwayat",  "Riwayat trade terakhir"),
    ("report",   "Laporan ringkas performa"),
    ("evaluasi", "Evaluasi harian + self-learning"),
    ("pelajaran","Lihat pelajaran yang sudah dipelajari bot"),
    ("pause",    "Jeda trading (stop buka posisi baru)"),
    ("resume",   "Lanjutkan trading"),
    ("close",    "Tutup posisi terbuka sekarang"),
    ("settings", "Lihat konfigurasi bot"),
    ("help",     "Bantuan"),
]


def set_commands():
    if not BOT_TOKEN:
        return
    cmds = [{"command": c, "description": d} for c, d in COMMANDS]
    try:
        requests.post(f"{_API}/setMyCommands", json={"commands": cmds}, timeout=10)
    except Exception as e:
        logger.warning("setMyCommands failed: %s", e)


# ── Inline keyboard main menu ────────────────────────────────────────────────
def main_menu_kb():
    return {"inline_keyboard": [
        [{"text": "📊 Status", "callback_data": "status"},
         {"text": "💰 Saldo", "callback_data": "saldo"}],
        [{"text": "📈 Posisi", "callback_data": "posisi"},
         {"text": "🔔 Sinyal", "callback_data": "sinyal"}],
        [{"text": "📜 Riwayat", "callback_data": "riwayat"},
         {"text": "🧾 Report", "callback_data": "report"}],
        [{"text": "📅 Evaluasi Harian", "callback_data": "evaluasi"},
         {"text": "🧠 Pelajaran", "callback_data": "pelajaran"}],
        [{"text": "⏸️ Pause", "callback_data": "pause"},
         {"text": "▶️ Resume", "callback_data": "resume"}],
        [{"text": "❌ Tutup Posisi", "callback_data": "close"},
         {"text": "⚙️ Settings", "callback_data": "settings"}],
    ]}


# ── Content builders (read real bot state) ───────────────────────────────────
def build_status():
    mode = "PAPER 🧪" if getattr(config, "PAPER_TRADING", True) else "LIVE 🔴"
    state = "⏸️ JEDA" if control["paused"] else "✅ AKTIF"
    pos = "Ada posisi terbuka" if TE.snapshot_state()["position"] else "Tidak ada posisi"
    return (f"📊 *STATUS BOT*\n"
            f"Kondisi : {state}\n"
            f"Mode    : {mode}\n"
            f"Simbol  : `{getattr(config,'SYMBOL','XAUUSDT')}`  TF: {getattr(config,'TIMEFRAME','15m')}\n"
            f"Posisi  : {pos}")


def build_balance():
    s = TE.get_paper_stats()
    return (f"💰 *SALDO & PNL*\n"
            f"Saldo  : `${s.get('balance',0):,.2f}`\n"
            f"Total PnL : `{s.get('total_pnl',0):+.2f} USDT`\n"
            f"Fees   : `${s.get('fees_paid',0):,.2f}`")


def build_position():
    p = TE.snapshot_state()["position"]
    if not p:
        return "📈 *POSISI*\nTidak ada posisi terbuka saat ini."
    em = "🟢" if p["side"] == "LONG" else "🔴"
    return (f"{em} *POSISI TERBUKA — {p['side']}*\n"
            f"Entry : `${p.get('entry','-')}`\n"
            f"Qty   : `{p.get('qty_left','-')}`\n"
            f"SL    : `${p.get('sl','-')}`\n"
            f"TP1   : `${p.get('tp1','-')}` {'✅' if p.get('tp1_done') else ''}\n"
            f"TP2   : `${p.get('tp2','-')}`\n"
            f"Quality: *{p.get('quality','-')}* | Conf: *{p.get('confidence','-')}%*")


def build_signal():
    d = _last["decision"]
    if not d:
        return "🔔 *SINYAL TERAKHIR*\nBelum ada analisa. Tunggu siklus berikutnya."
    return (f"🔔 *SINYAL TERAKHIR* ({_last.get('ts','-')})\n"
            f"Harga : `${_last.get('price',0):,.2f}`\n"
            f"Sinyal: *{(d.get('signal') or 'HOLD').upper()}* "
            f"(Q={d.get('trade_quality','-')}, conf={d.get('confidence','-')}%)\n"
            f"_Alasan:_ {(d.get('reasoning') or '')[:300]}")


def build_history(n=5):
    log = TE.snapshot_state().get("trade_log", [])
    if not log:
        return "📜 *RIWAYAT*\nBelum ada trade."
    lines = ["📜 *RIWAYAT TRADE (terakhir)*"]
    for ev in log[-n:]:
        pnl = ev.get("pnl") or ev.get("pnl_final_leg") or 0
        em = "✅" if pnl >= 0 else "❌"
        lines.append(f"{em} {ev.get('side','')} {ev.get('reason','')} → `{pnl:+.2f}`")
    return "\n".join(lines)


def build_report():
    s = TE.get_paper_stats()
    return (f"🧾 *LAPORAN PERFORMA*\n"
            f"Saldo  : `${s.get('balance',0):,.2f}`\n"
            f"Trade  : {s.get('total_trades',0)} | "
            f"Menang {s.get('wins',0)} / Kalah {s.get('losses',0)}\n"
            f"Winrate: *{s.get('winrate',0)}%*\n"
            f"Fees   : `${s.get('fees_paid',0):,.2f}`")


def build_settings():
    return (f"⚙️ *KONFIGURASI*\n"
            f"Modal/trade : `{getattr(config,'TRADE_USDT',50)} USDT`\n"
            f"Leverage    : `{getattr(config,'LEVERAGE',5)}x`\n"
            f"Stop Loss   : `{getattr(config,'STOP_LOSS_PCT',0.005)*100:.2f}%`\n"
            f"Take Profit : `{getattr(config,'TAKE_PROFIT_PCT',0.015)*100:.2f}%`\n"
            f"Max posisi  : `{getattr(config,'MAX_OPEN_TRADES',1)}`\n"
            f"Mode        : {'PAPER' if getattr(config,'PAPER_TRADING',True) else 'LIVE'}")


def build_evaluation():
    if EVAL is None:
        return "📅 Modul evaluasi belum tersedia."
    try:
        # preview: jalankan refleksi hari ini TANPA menyimpan (hindari polusi memori
        # dari evaluasi parsial tengah hari). Evaluasi resmi tetap jalan tiap tengah malam.
        ev = EVAL.evaluate_day(send_fn=None, persist=False)
        return "👁️ _(preview hari berjalan — pelajaran disimpan saat evaluasi tengah malam)_\n\n" + \
               EVAL.build_eval_report(ev)
    except Exception as e:
        return f"📅 Gagal evaluasi: {e}"


def build_lessons():
    if MEM is None:
        return "🧠 Memori belajar belum tersedia."
    lessons = MEM.load_lessons()
    if not lessons:
        return "🧠 *MEMORI PELAJARAN*\nBelum ada pelajaran. Bot belajar otomatis tiap evaluasi harian."
    lines = [f"🧠 *MEMORI PELAJARAN BOT* ({len(lessons)} tersimpan)"]
    for i, l in enumerate(lessons[-15:], 1):
        lines.append(f"{i}. [{l.get('category','')}] {l.get('lesson','')}  _({l.get('date','')})_")
    return "\n".join(lines)


HELP = ("🤖 *GOLD TRADING BOT*\nKetik perintah atau pakai tombol menu:\n" +
        "\n".join(f"/{c} — {d}" for c, d in COMMANDS))


# ── Dispatcher ───────────────────────────────────────────────────────────────
def handle(action: str) -> str:
    a = action.lstrip("/").split("@")[0].split()[0] if action else ""
    if a in ("start", "menu", "help"):
        return HELP
    if a == "status":   return build_status()
    if a == "saldo":    return build_balance()
    if a == "posisi":   return build_position()
    if a == "sinyal":   return build_signal()
    if a == "riwayat":  return build_history()
    if a == "report":   return build_report()
    if a == "evaluasi": return build_evaluation()
    if a in ("pelajaran", "lessons"): return build_lessons()
    if a == "settings": return build_settings()
    if a == "pause":
        control["paused"] = True
        return "⏸️ Trading *dijeda*. Bot tidak akan buka posisi baru (posisi terbuka tetap dikelola)."
    if a == "resume":
        control["paused"] = False
        return "▶️ Trading *dilanjutkan*."
    if a == "close":
        if TE.paper_state["position"]:
            control["force_close"] = True
            return "❌ Permintaan *tutup posisi* diterima. Akan dieksekusi di harga pasar pada cek berikutnya."
        return "Tidak ada posisi yang perlu ditutup."
    return "Perintah tidak dikenal. Ketik /help."


def send(text, kb=None):
    if not (BOT_TOKEN and CHAT_ID):
        return
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if kb:
        payload["reply_markup"] = kb
    try:
        requests.post(f"{_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logger.warning("send failed: %s", e)


def run(poll_timeout=30):
    """Long-poll loop. Run in a background thread."""
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram menu disabled.")
        return
    set_commands()
    offset = None
    logger.info("Telegram control bot started.")
    while True:
        try:
            r = requests.get(f"{_API}/getUpdates",
                             params={"timeout": poll_timeout, "offset": offset},
                             timeout=poll_timeout + 10)
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                if "message" in upd and upd["message"].get("text"):
                    txt = upd["message"]["text"]
                    reply = handle(txt)
                    kb = main_menu_kb() if txt.lstrip("/").startswith(("start", "menu")) else None
                    send(reply, kb)
                elif "callback_query" in upd:
                    cq = upd["callback_query"]
                    data = cq.get("data", "")
                    try:
                        requests.post(f"{_API}/answerCallbackQuery",
                                      json={"callback_query_id": cq["id"]}, timeout=10)
                    except Exception:
                        pass
                    send(handle(data))
        except Exception as e:
            logger.warning("poll error: %s", e)
            time.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()

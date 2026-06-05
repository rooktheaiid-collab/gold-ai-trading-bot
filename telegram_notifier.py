"""
Telegram notifier for the Gold Trading Bot.
===========================================
One-way push notifications (trade alerts, PnL, errors) to a Telegram chat.
Uses the Telegram Bot HTTP API directly (no extra deps beyond `requests`) so it
works on any VPS without Pipedream. Set these env vars / config:

    TELEGRAM_BOT_TOKEN   - from @BotFather  (e.g. 123456:ABC-DEF...)
    TELEGRAM_CHAT_ID     - your chat id (number) or @channel_username

If the token/chat are not set, notify() becomes a silent no-op so the bot keeps
running normally.
"""
import os, logging, requests

logger = logging.getLogger("telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def enabled() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


def notify(text: str, silent: bool = False) -> bool:
    """Send a Markdown message to the configured chat. No-op if not configured."""
    if not enabled():
        return False
    try:
        r = requests.post(f"{_API}/sendMessage", json={
            "chat_id": CHAT_ID, "text": text,
            "parse_mode": "Markdown", "disable_notification": silent,
        }, timeout=10)
        if r.status_code != 200:
            logger.warning("Telegram send failed %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning("Telegram error: %s", e)
        return False


# ---- pre-formatted message builders ----------------------------------------

def fmt_open(decision: dict, price: float) -> str:
    sig = (decision.get("signal") or "?").upper()
    emoji = "🟢" if sig == "LONG" else "🔴"
    return (
        f"{emoji} *TRADE DIBUKA — {sig}*  (XAUUSDT)\n"
        f"Entry  : `${price:,.2f}`\n"
        f"Stop   : `${decision.get('stop_loss','-')}`\n"
        f"TP1    : `${decision.get('take_profit_1','-')}`\n"
        f"TP2    : `${decision.get('take_profit_2','-')}`\n"
        f"Quality: *{decision.get('trade_quality','-')}*  |  Conf: *{decision.get('confidence','-')}%*\n"
        f"_Alasan:_ {(decision.get('reasoning') or '')[:280]}"
    )


def fmt_close(event: dict) -> str:
    pnl = event.get("pnl") or event.get("pnl_final_leg") or 0
    emoji = "✅" if (pnl or 0) >= 0 else "❌"
    return (
        f"{emoji} *POSISI DITUTUP* — {event.get('side','')}\n"
        f"Sebab : {event.get('reason','')}\n"
        f"Exit  : `${event.get('exit','-')}`\n"
        f"PnL   : `{pnl:+.2f} USDT`"
    )


def fmt_decision(decision: dict, price: float, ts: str) -> str:
    sig = (decision.get("signal") or "HOLD").upper()
    return (
        f"🔍 *Cek pasar* {ts}\n"
        f"Harga: `${price:,.2f}`  →  *{sig}* "
        f"(Q={decision.get('trade_quality','-')}, conf={decision.get('confidence','-')}%)"
    )


def fmt_stats(stats: dict) -> str:
    return (
        f"📊 *Status Akun (paper)*\n"
        f"Saldo : `${stats.get('balance',0):,.2f}`\n"
        f"Trade : {stats.get('total_trades',0)} | "
        f"W/L: {stats.get('wins',0)}/{stats.get('losses',0)} | "
        f"WR: {stats.get('winrate',0)}%\n"
        f"Fees  : `${stats.get('fees_paid',0):,.2f}`"
    )

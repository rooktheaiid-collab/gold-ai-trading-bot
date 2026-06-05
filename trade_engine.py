"""
Gold Trading Bot - Trade Execution Engine
==========================================
Paper trading (simulasi) dan Live order ke Binance Futures.

Perbaikan hasil audit:
- Paper: cek SL/TP pakai high/low candle (bukan hanya close) + biaya taker fee.
- Paper: TP1 = partial close (default 50%) lalu SL pindah ke breakeven, sisanya
  dibiarkan ke TP2. Ini membuat target berlapis benar-benar berfungsi.
- Live: quantity & harga SL/TP DIBULATKAN ke stepSize / tickSize dari
  futures_exchange_info (mencegah error -1111 LOT_SIZE / -4014 PRICE_FILTER).
- Live: SL/TP pakai reduceOnly + closePosition yang konsisten.
"""

import os
import json
import logging
import threading
from datetime import datetime, timezone
from binance.client import Client
from binance.enums import *
from binance.helpers import round_step_size
import config

logger = logging.getLogger(__name__)

# Taker fee Binance Futures ~0.04% per sisi (entry+exit ~0.08% notional).
TAKER_FEE = 0.0004
TP1_CLOSE_FRACTION = 0.5   # porsi posisi yang ditutup di TP1


# ─────────────────────────────────────────────────────────────────────────────
# PAPER TRADING STATE
# ─────────────────────────────────────────────────────────────────────────────

paper_state = {
    "balance":   1000.0,
    "position":  None,    # {'side','entry','qty','qty_left','sl','tp1','tp2',
                          #  'tp1_done','time','quality','confidence'}
    "trade_log": [],
    "total_pnl": 0.0,
    "wins":      0,
    "losses":    0,
    "fees_paid": 0.0,
}


def _fee(notional: float) -> float:
    return abs(notional) * TAKER_FEE


# ─────────────────────────────────────────────────────────────────────────────
# STATE PERSISTENCE (tahan restart VPS) — atomic write
# ─────────────────────────────────────────────────────────────────────────────
_STATE_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_memory")
STATE_PATH  = os.path.join(_STATE_DIR, "paper_state.json")
_STATE_LOCK = threading.RLock()   # serialize write state antar-thread (loop utama vs Telegram)


def _atomic_write(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, path)   # atomic on POSIX → no half-written/corrupt file


def save_state():
    """Persist paper_state to disk (atomic) so balance/posisi/riwayat tahan restart."""
    try:
        with _STATE_LOCK:
            _atomic_write(STATE_PATH, paper_state)
    except Exception as e:
        logger.warning(f"[STATE] Gagal simpan state: {e}")


def load_state():
    """Muat paper_state dari disk jika ada. Dipanggil sekali saat startup."""
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            paper_state.update(data)
            logger.info(f"[STATE] State dimuat: balance={paper_state.get('balance')} "
                        f"trades={len(paper_state.get('trade_log', []))} "
                        f"posisi={'ADA' if paper_state.get('position') else 'tidak ada'}")
            return True
    except Exception as e:
        logger.warning(f"[STATE] Gagal muat state ({e}); mulai dari default.")
    return False


def paper_open_trade(decision: dict, current_price: float):
    """Buka posisi paper trading."""
    if paper_state["position"]:
        logger.info("[PAPER] Sudah ada posisi terbuka, skip.")
        return

    signal = decision.get("signal")
    if signal not in ("LONG", "SHORT"):
        return

    entry = decision.get("entry_price") or current_price
    sl    = decision.get("stop_loss")
    tp1   = decision.get("take_profit_1")
    tp2   = decision.get("take_profit_2")

    if not sl or not tp1:
        logger.warning("[PAPER] SL/TP tidak ada, skip trade.")
        return

    # Validasi arah SL/TP supaya logis (cegah setup terbalik dari LLM)
    if signal == "LONG" and not (sl < entry < tp1):
        logger.warning(f"[PAPER] LONG tidak valid (sl<{entry}<tp1) sl={sl} tp1={tp1}, skip.")
        return
    if signal == "SHORT" and not (tp1 < entry < sl):
        logger.warning(f"[PAPER] SHORT tidak valid (tp1<{entry}<sl) sl={sl} tp1={tp1}, skip.")
        return

    # Clamp jarak SL: tolak setup dengan SL kejauhan (risiko per-trade membengkak)
    max_sl_pct = getattr(config, "MAX_SL_DISTANCE_PCT", 0)
    if max_sl_pct and abs(entry - sl) / entry > max_sl_pct:
        logger.warning(f"[PAPER] SL terlalu jauh ({abs(entry-sl)/entry*100:.2f}% > "
                       f"{max_sl_pct*100:.2f}%), skip trade berisiko.")
        return

    qty = round((config.TRADE_USDT * config.LEVERAGE) / entry, 4)
    entry_fee = _fee(qty * entry)
    paper_state["balance"]   -= entry_fee
    paper_state["fees_paid"] += entry_fee

    paper_state["position"] = {
        "side": signal, "entry": entry, "qty": qty, "qty_left": qty,
        "sl": sl, "tp1": tp1, "tp2": tp2 or tp1, "tp1_done": False,
        "pnl_tp1": 0.0,   # profit yang sudah dibukukan di TP1 (untuk PnL total trade)
        "time": datetime.now(timezone.utc).isoformat(),
        "quality": decision.get("trade_quality"),
        "confidence": decision.get("confidence"),
    }
    logger.info(f"[PAPER] ✅ OPEN {signal} @ {entry} | SL={sl} | TP1={tp1} | TP2={tp2} | qty={qty} | fee={entry_fee:.4f}")
    save_state()


def paper_check_close(current_price: float, candle_high: float | None = None,
                      candle_low: float | None = None) -> str | None:
    """
    Cek SL/TP. Pakai high/low candle jika tersedia (lebih realistis daripada
    hanya close). Returns 'SL_HIT' / 'TP1_PARTIAL' / 'TP2_HIT' / None.
    Jika SL & TP tersentuh di candle yang sama → konservatif: anggap SL dulu.
    """
    pos = paper_state["position"]
    if not pos:
        return None

    hi = candle_high if candle_high is not None else current_price
    lo = candle_low  if candle_low  is not None else current_price
    side = pos["side"]

    if side == "LONG":
        sl_hit  = lo <= pos["sl"]
        tp2_hit = hi >= pos["tp2"]
        tp1_hit = hi >= pos["tp1"]
    else:  # SHORT
        sl_hit  = hi >= pos["sl"]
        tp2_hit = lo <= pos["tp2"]
        tp1_hit = lo <= pos["tp1"]

    # Konservatif: SL diprioritaskan jika kena di candle yang sama.
    if sl_hit:
        _paper_close_remaining(pos["sl"], "SL_HIT")
        return "SL_HIT"
    if tp2_hit:
        _paper_close_remaining(pos["tp2"], "TP2_HIT")
        return "TP2_HIT"
    if tp1_hit and not pos["tp1_done"]:
        _paper_partial_tp1(pos["tp1"])
        return "TP1_PARTIAL"
    return None


def _realized_pnl(side, entry, exit_p, qty):
    return (exit_p - entry) * qty if side == "LONG" else (entry - exit_p) * qty


def _paper_partial_tp1(price: float):
    """Tutup sebagian di TP1, pindahkan SL ke breakeven untuk sisa posisi."""
    pos = paper_state["position"]
    close_qty = round(pos["qty"] * TP1_CLOSE_FRACTION, 6)
    pnl = _realized_pnl(pos["side"], pos["entry"], price, close_qty)
    fee = _fee(close_qty * price)
    paper_state["total_pnl"] += pnl
    paper_state["balance"]   += pnl - fee
    paper_state["fees_paid"] += fee
    pos["qty_left"] -= close_qty
    pos["tp1_done"]  = True
    pos["pnl_tp1"]   = pos.get("pnl_tp1", 0.0) + (pnl - fee)   # profit bersih TP1 utk PnL total
    pos["sl"]        = pos["entry"]   # breakeven stop
    logger.info(f"[PAPER] 🟡 TP1 PARTIAL close {close_qty} @ {price} | PnL={pnl:+.2f} | SL→BE | sisa qty={pos['qty_left']:.4f}")
    save_state()


def _paper_close_remaining(price: float, reason: str):
    """Tutup sisa posisi dan catat ke log."""
    pos = paper_state["position"]
    qty = pos["qty_left"]
    pnl = _realized_pnl(pos["side"], pos["entry"], price, qty)
    fee = _fee(qty * price)
    paper_state["total_pnl"] += pnl
    paper_state["balance"]   += pnl - fee
    paper_state["fees_paid"] += fee

    # PnL TOTAL trade = leg sisa (bersih) + profit yang sudah dibukukan di TP1.
    # Inilah angka yang dipakai untuk W/L, statistik harian, & self-learning.
    pnl_leg_net = pnl - fee
    pnl_total   = round(pnl_leg_net + pos.get("pnl_tp1", 0.0), 2)

    is_win = pnl_total > 0
    if is_win:
        paper_state["wins"] += 1; emoji = "✅"
    else:
        paper_state["losses"] += 1; emoji = "❌"

    paper_state["trade_log"].append({
        "side": pos["side"], "entry": pos["entry"], "exit": price,
        "pnl": pnl_total,                       # PnL total trade (TP1 + leg sisa, net fee)
        "pnl_final_leg": round(pnl, 2),         # leg terakhir saja (untuk audit)
        "pnl_tp1": round(pos.get("pnl_tp1", 0.0), 2),
        "reason": reason,
        "tp1_done": pos["tp1_done"], "quality": pos.get("quality"),
        "confidence": pos.get("confidence"),
        "opened": pos["time"], "closed": datetime.now(timezone.utc).isoformat(),
    })
    paper_state["position"] = None

    total = paper_state["wins"] + paper_state["losses"]
    wr = paper_state["wins"] / total * 100 if total else 0
    logger.info(f"[PAPER] {emoji} CLOSE {reason} @ {price} | trade PnL={pnl_total:+.2f} "
                f"(leg={pnl:+.2f}, tp1={pos.get('pnl_tp1',0):+.2f}) | "
                f"Balance={paper_state['balance']:.2f} | WR={wr:.1f}%")
    save_state()
    return paper_state["trade_log"][-1]


def paper_force_close(current_price: float) -> dict | None:
    """Tutup paksa posisi terbuka di harga pasar (dipakai tombol /close Telegram)."""
    if not paper_state["position"]:
        return None
    return _paper_close_remaining(current_price, "MANUAL_CLOSE")


def get_paper_stats() -> dict:
    total = paper_state["wins"] + paper_state["losses"]
    wr = paper_state["wins"] / total * 100 if total else 0
    return {
        "balance": round(paper_state["balance"], 2),
        "total_pnl": round(paper_state["total_pnl"], 2),
        "fees_paid": round(paper_state["fees_paid"], 2),
        "total_trades": total, "wins": paper_state["wins"],
        "losses": paper_state["losses"], "winrate": round(wr, 1),
        "position": paper_state["position"],
        "recent_trades": paper_state["trade_log"][-5:],
    }


# ─────────────────────────────────────────────────────────────────────────────
# LIVE TRADING (Binance Futures)
# ─────────────────────────────────────────────────────────────────────────────

_filters_cache: dict = {}


def get_symbol_filters(client: Client, symbol: str) -> dict:
    """Ambil stepSize (LOT_SIZE) & tickSize (PRICE_FILTER) dari exchange info."""
    if symbol in _filters_cache:
        return _filters_cache[symbol]
    info = client.futures_exchange_info()
    step_size = tick_size = min_qty = None
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            for f in s["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"]); min_qty = float(f["minQty"])
                elif f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])
            break
    if step_size is None or tick_size is None:
        raise ValueError(f"Filter LOT_SIZE/PRICE_FILTER tidak ditemukan untuk {symbol}")
    _filters_cache[symbol] = {"step_size": step_size, "tick_size": tick_size, "min_qty": min_qty}
    return _filters_cache[symbol]


def live_position_amt(client: Client, symbol: str) -> float:
    """Posisi terbuka NYATA di exchange (signed). >0 long, <0 short, 0 flat."""
    try:
        info = client.futures_position_information(symbol=symbol)
        if isinstance(info, dict):
            info = [info]
        for p in info:
            if p.get("symbol") == symbol:
                return float(p.get("positionAmt", 0) or 0)
    except Exception as e:
        logger.warning(f"[LIVE] Gagal cek posisi exchange: {e}")
    return 0.0


def _cancel_order_silent(client, symbol, order_id):
    if not order_id:
        return
    try:
        client.futures_cancel_order(symbol=symbol, orderId=order_id)
    except Exception as e:
        logger.warning(f"[LIVE] Gagal cancel order {order_id}: {e}")


def live_open_trade(client: Client, decision: dict, current_price: float):
    """
    Eksekusi order LIVE ke Binance Futures — DISELARASKAN dengan paper:
    TP1 partial (reduceOnly 50%) + TP2 (closePosition) + SL (closePosition).
    Quantity & harga dibulatkan ke stepSize/tickSize. Guard anti dobel-posisi.
    Mencatat posisi ke paper_state agar /status, circuit breaker, evaluasi
    harian, & notifikasi Telegram bekerja sama persis seperti mode paper.
    """
    signal = decision.get("signal")
    if signal not in ("LONG", "SHORT"):
        return None

    # Guard 1: ledger internal sudah punya posisi
    if paper_state["position"]:
        logger.info("[LIVE] Ledger sudah ada posisi terbuka, skip.")
        return None

    sl  = decision.get("stop_loss")
    tp1 = decision.get("take_profit_1")
    tp2 = decision.get("take_profit_2") or tp1
    entry = decision.get("entry_price") or current_price
    if not sl or not tp1:
        logger.error("[LIVE] SL/TP wajib ada!")
        return None

    # Validasi arah + clamp jarak SL (sama seperti paper)
    if signal == "LONG" and not (sl < entry < tp1):
        logger.warning(f"[LIVE] LONG tidak valid sl={sl} tp1={tp1}, skip."); return None
    if signal == "SHORT" and not (tp1 < entry < sl):
        logger.warning(f"[LIVE] SHORT tidak valid sl={sl} tp1={tp1}, skip."); return None
    max_sl_pct = getattr(config, "MAX_SL_DISTANCE_PCT", 0)
    if max_sl_pct and abs(entry - sl) / entry > max_sl_pct:
        logger.warning(f"[LIVE] SL terlalu jauh ({abs(entry-sl)/entry*100:.2f}%), skip."); return None

    try:
        # Guard 2: posisi NYATA di exchange (cegah dobel/stacking)
        if abs(live_position_amt(client, config.SYMBOL)) > 0:
            logger.warning("[LIVE] Sudah ada posisi NYATA di exchange, skip entry baru.")
            return None

        filt = get_symbol_filters(client, config.SYMBOL)
        step, tick, min_qty = filt["step_size"], filt["tick_size"], filt["min_qty"]

        qty_raw = (config.TRADE_USDT * config.LEVERAGE) / current_price
        qty = round_step_size(qty_raw, step)
        if min_qty and qty < min_qty:
            logger.error(f"[LIVE] qty {qty} < minQty {min_qty}. Naikkan TRADE_USDT/LEVERAGE. Skip.")
            return None
        qty_tp1 = round_step_size(qty * TP1_CLOSE_FRACTION, step)
        sl_r  = round_step_size(sl,  tick)
        tp1_r = round_step_size(tp1, tick)
        tp2_r = round_step_size(tp2, tick)

        side_enum  = SIDE_BUY  if signal == "LONG" else SIDE_SELL
        close_side = SIDE_SELL if signal == "LONG" else SIDE_BUY

        client.futures_change_leverage(symbol=config.SYMBOL, leverage=config.LEVERAGE)

        entry_order = client.futures_create_order(
            symbol=config.SYMBOL, side=side_enum,
            type=ORDER_TYPE_MARKET, quantity=qty,
        )
        logger.info(f"[LIVE] Entry: {signal} qty={qty} @~{current_price}")

        # SL: tutup seluruh sisa posisi saat tersentuh
        sl_order = client.futures_create_order(
            symbol=config.SYMBOL, side=close_side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=sl_r, closePosition=True, workingType="MARK_PRICE",
        )
        # TP1: partial (reduceOnly) — hanya menutup sebagian (mirror paper)
        tp1_order = None
        if qty_tp1 and qty_tp1 >= (min_qty or 0):
            tp1_order = client.futures_create_order(
                symbol=config.SYMBOL, side=close_side,
                type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                stopPrice=tp1_r, quantity=qty_tp1, reduceOnly=True,
                workingType="MARK_PRICE",
            )
        # TP2: tutup seluruh sisa posisi
        tp2_order = client.futures_create_order(
            symbol=config.SYMBOL, side=close_side,
            type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
            stopPrice=tp2_r, closePosition=True, workingType="MARK_PRICE",
        )

        # Catat ke ledger internal (schema sama dgn paper + id order live)
        paper_state["position"] = {
            "side": signal, "entry": entry, "qty": qty, "qty_left": qty,
            "sl": sl_r, "tp1": tp1_r, "tp2": tp2_r, "tp1_done": False,
            "pnl_tp1": 0.0,
            "time": datetime.now(timezone.utc).isoformat(),
            "quality": decision.get("trade_quality"),
            "confidence": decision.get("confidence"),
            "live": True,
            "sl_order_id":  (sl_order  or {}).get("orderId"),
            "tp1_order_id": (tp1_order or {}).get("orderId"),
            "tp2_order_id": (tp2_order or {}).get("orderId"),
        }
        save_state()
        logger.info(f"[LIVE] ✅ {signal} qty={qty} (TP1 {qty_tp1}) | SL={sl_r} | TP1={tp1_r} | TP2={tp2_r}")
        return {"entry": entry_order, "sl": sl_order, "tp1": tp1_order, "tp2": tp2_order}

    except Exception as e:
        logger.error(f"[LIVE] Order failed: {e}")
        return None


def live_manage(client: Client, current_price: float) -> str | None:
    """
    Rekonsiliasi posisi LIVE tiap cycle (mirror paper_check_close):
      • Deteksi TP1 fill (posisi menyusut) → pindahkan SL ke breakeven.
      • Deteksi posisi tertutup penuh di exchange (SL/TP2 kena) → catat trade.
    Returns 'TP1_PARTIAL' / 'CLOSED' / None.
    """
    pos = paper_state["position"]
    if not pos or not pos.get("live"):
        return None

    amt = abs(live_position_amt(client, config.SYMBOL))

    # 1) Posisi sudah flat di exchange → SL atau TP2 sudah eksekusi
    if amt < (pos["qty"] * 0.05):   # toleransi pembulatan
        reason = "TP2_HIT" if pos["tp1_done"] else "SL_HIT"
        # estimasi harga exit dari sisi yg paling mungkin
        exit_px = pos["tp2"] if reason == "TP2_HIT" else pos["sl"]
        _live_record_close(exit_px, reason, client)
        return "CLOSED"

    # 2) TP1 fill terdeteksi (posisi menyusut ~separuh) & belum ditandai
    if not pos["tp1_done"] and amt <= pos["qty"] * (1 - TP1_CLOSE_FRACTION + 0.05):
        closed_qty = pos["qty"] - amt
        pnl = _realized_pnl(pos["side"], pos["entry"], pos["tp1"], closed_qty)
        fee = _fee(closed_qty * pos["tp1"])
        pos["qty_left"] = amt
        pos["tp1_done"] = True
        pos["pnl_tp1"]  = pos.get("pnl_tp1", 0.0) + (pnl - fee)
        paper_state["total_pnl"] += pnl
        paper_state["fees_paid"] += fee
        # Pindahkan SL ke breakeven: cancel SL lama, pasang baru di entry
        _cancel_order_silent(client, config.SYMBOL, pos.get("sl_order_id"))
        try:
            filt = get_symbol_filters(client, config.SYMBOL)
            be = round_step_size(pos["entry"], filt["tick_size"])
            close_side = SIDE_SELL if pos["side"] == "LONG" else SIDE_BUY
            new_sl = client.futures_create_order(
                symbol=config.SYMBOL, side=close_side,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=be, closePosition=True, workingType="MARK_PRICE",
            )
            pos["sl"] = be
            pos["sl_order_id"] = (new_sl or {}).get("orderId")
        except Exception as e:
            logger.warning(f"[LIVE] Gagal pindah SL ke breakeven: {e}")
        save_state()
        logger.info(f"[LIVE] 🟡 TP1 fill terdeteksi @ {pos['tp1']} | PnL={pnl:+.2f} | SL→BE")
        return "TP1_PARTIAL"

    return None


def _live_record_close(exit_price: float, reason: str, client: Client | None = None):
    """Catat penutupan posisi LIVE ke ledger (mirror _paper_close_remaining) + bersihkan order sisa."""
    pos = paper_state["position"]
    if not pos:
        return None
    qty = pos["qty_left"]
    pnl = _realized_pnl(pos["side"], pos["entry"], exit_price, qty)
    fee = _fee(qty * exit_price)
    paper_state["total_pnl"] += pnl
    paper_state["balance"]   += pnl - fee   # ledger informatif (sumber kebenaran = Binance)
    paper_state["fees_paid"] += fee

    pnl_leg_net = pnl - fee
    pnl_total   = round(pnl_leg_net + pos.get("pnl_tp1", 0.0), 2)
    is_win = pnl_total > 0
    if is_win: paper_state["wins"] += 1; emoji = "✅"
    else:      paper_state["losses"] += 1; emoji = "❌"

    paper_state["trade_log"].append({
        "side": pos["side"], "entry": pos["entry"], "exit": exit_price,
        "pnl": pnl_total, "pnl_final_leg": round(pnl, 2),
        "pnl_tp1": round(pos.get("pnl_tp1", 0.0), 2),
        "reason": reason, "tp1_done": pos["tp1_done"],
        "quality": pos.get("quality"), "confidence": pos.get("confidence"),
        "opened": pos["time"], "closed": datetime.now(timezone.utc).isoformat(),
        "live": True,
    })
    # Bersihkan order yang masih nyangkut di exchange
    if client is not None:
        try:
            client.futures_cancel_all_open_orders(symbol=config.SYMBOL)
        except Exception as e:
            logger.warning(f"[LIVE] Gagal cancel sisa order: {e}")
    paper_state["position"] = None
    save_state()
    logger.info(f"[LIVE] {emoji} CLOSE {reason} @ {exit_price} | trade PnL={pnl_total:+.2f}")
    return paper_state["trade_log"][-1]


def live_force_close(client: Client, current_price: float) -> dict | None:
    """Tutup paksa posisi LIVE di harga pasar (tombol /close Telegram)."""
    pos = paper_state["position"]
    if not pos or not pos.get("live"):
        return None
    try:
        amt = abs(live_position_amt(client, config.SYMBOL))
        if amt > 0:
            filt = get_symbol_filters(client, config.SYMBOL)
            qty = round_step_size(amt, filt["step_size"])
            close_side = SIDE_SELL if pos["side"] == "LONG" else SIDE_BUY
            client.futures_create_order(
                symbol=config.SYMBOL, side=close_side,
                type=ORDER_TYPE_MARKET, quantity=qty, reduceOnly=True,
            )
        client.futures_cancel_all_open_orders(symbol=config.SYMBOL)
    except Exception as e:
        logger.error(f"[LIVE] Force close gagal: {e}")
    return _live_record_close(current_price, "MANUAL_CLOSE", client=None)

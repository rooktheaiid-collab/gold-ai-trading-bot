"""
Gold Trading Bot - Technical Analysis Engine
=============================================
Menghitung semua indikator teknikal yang relevan untuk gold trading.
Library: pandas-ta

CATATAN PENTING (hasil audit):
- Nama kolom pandas-ta berubah antar versi (mis. Bollinger Bands:
  0.3.x -> 'BBU_20_2.0', 0.4.x -> 'BBU_20_2.0_2.0'). Karena itu semua
  pengambilan kolom memakai pencocokan PREFIX agar tahan versi.
- EMA_200 hanya muncul jika data >= 200 candle. compute_indicators
  mengembalikan None untuk EMA200 jika data kurang (bukan crash).
- Pivot Points dihitung dari candle HARIAN sebelumnya (standar untuk
  chart intraday <=15m), bukan dari candle 15m sebelumnya.
"""

import pandas as pd
import pandas_ta as ta   # type: ignore
import numpy as np
import logging

logger = logging.getLogger(__name__)

_BASE_COLS = {"timestamp", "open", "high", "low", "close", "volume"}


def _col_like(d: pd.DataFrame, prefix: str):
    """Kembalikan nama kolom pertama yang diawali `prefix` (tahan beda versi)."""
    for c in d.columns:
        if c.startswith(prefix) and c not in _BASE_COLS:
            return c
    return None


def _val(d: pd.DataFrame, prefix: str, row_idx: int = -1):
    """Ambil nilai indikator dari kolom yang cocok prefix; None jika NaN/missing."""
    col = _col_like(d, prefix)
    if col is None:
        return None
    v = d[col].iloc[row_idx]
    return round(float(v), 4) if pd.notna(v) else None


def compute_pivots(daily_df: pd.DataFrame) -> dict:
    """
    Classic pivot points dari candle HARIAN terakhir yang sudah closed.
    daily_df: DataFrame OHLCV timeframe 1d (minimal 2 baris).
    """
    if daily_df is None or len(daily_df) < 2:
        return {}
    prev = daily_df.iloc[-2]   # hari sebelumnya yang sudah closed
    h, l, c = float(prev.high), float(prev.low), float(prev.close)
    pp = (h + l + c) / 3
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)
    r3 = pp + 2 * (h - l)
    s3 = pp - 2 * (h - l)
    return {
        "pivot": round(pp, 4),
        "r1": round(r1, 4), "r2": round(r2, 4), "r3": round(r3, 4),
        "s1": round(s1, 4), "s2": round(s2, 4), "s3": round(s3, 4),
        "basis": "previous_daily_candle",
    }


def compute_indicators(df: pd.DataFrame, daily_df: pd.DataFrame | None = None) -> dict:
    """
    Terima DataFrame OHLCV, kembalikan dict ringkasan semua indikator.
      - Trend     : EMA 20/50/200, MACD
      - Momentum  : RSI-14, Stochastic RSI
      - Volatility: Bollinger Bands, ATR
      - Volume    : OBV
      - S/R       : Pivot Points (Classic, basis harian)
    `daily_df` opsional: jika diberikan, pivot dihitung dari candle harian.
    """
    d = df.copy()
    n = len(d)

    # ── Indikator ─────────────────────────────────────────────────────────────
    d.ta.ema(length=20,  append=True)
    d.ta.ema(length=50,  append=True)
    if n >= 200:
        d.ta.ema(length=200, append=True)
    d.ta.macd(fast=12, slow=26, signal=9, append=True)
    d.ta.rsi(length=14, append=True)
    d.ta.stochrsi(length=14, rsi_length=14, k=3, d=3, append=True)
    d.ta.bbands(length=20, std=2, append=True)
    d.ta.atr(length=14, append=True)
    d.ta.obv(append=True)

    last  = d.iloc[-1]
    price = float(last["close"])

    # ── Trend (EMA) ───────────────────────────────────────────────────────────
    ema20  = _val(d, "EMA_20")
    ema50  = _val(d, "EMA_50")
    ema200 = _val(d, "EMA_200")   # None jika data < 200 candle

    trend = "NEUTRAL"
    if ema20 and ema50:
        if ema200:
            if   price > ema20 > ema50 > ema200: trend = "STRONG BULLISH"
            elif price < ema20 < ema50 < ema200: trend = "STRONG BEARISH"
            elif price > ema20 > ema50:          trend = "BULLISH"
            elif price < ema20 < ema50:          trend = "BEARISH"
        else:
            # fallback tanpa EMA200 (data pendek) — beri label jelas
            if   price > ema20 > ema50: trend = "BULLISH (no EMA200)"
            elif price < ema20 < ema50: trend = "BEARISH (no EMA200)"

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi = _val(d, "RSI_14")
    rsi_signal = "NEUTRAL"
    if rsi is not None:
        if   rsi > 70: rsi_signal = "OVERBOUGHT"
        elif rsi < 30: rsi_signal = "OVERSOLD"
        elif rsi > 55: rsi_signal = "BULLISH MOMENTUM"
        elif rsi < 45: rsi_signal = "BEARISH MOMENTUM"

    # ── MACD (deteksi CROSS sungguhan: bandingkan 2 bar terakhir) ─────────────
    macd_line   = _val(d, "MACD_")    # MACD_12_26_9
    macd_signal = _val(d, "MACDs_")
    macd_hist   = _val(d, "MACDh_")
    macd_line_prev   = _val(d, "MACD_",  row_idx=-2)
    macd_signal_prev = _val(d, "MACDs_", row_idx=-2)

    macd_cross = "NEUTRAL"
    if None not in (macd_line, macd_signal, macd_line_prev, macd_signal_prev):
        crossed_up   = macd_line_prev <= macd_signal_prev and macd_line > macd_signal
        crossed_down = macd_line_prev >= macd_signal_prev and macd_line < macd_signal
        if   crossed_up:   macd_cross = "BULLISH CROSS (fresh)"
        elif crossed_down: macd_cross = "BEARISH CROSS (fresh)"
        elif macd_line > macd_signal: macd_cross = "BULLISH (above signal)"
        elif macd_line < macd_signal: macd_cross = "BEARISH (below signal)"

    # ── Bollinger Bands (prefix detection, tahan versi) ───────────────────────
    bb_upper = _val(d, "BBU_")
    bb_mid   = _val(d, "BBM_")
    bb_lower = _val(d, "BBL_")
    bb_pos   = "UNKNOWN"
    if bb_upper and bb_lower and bb_mid:
        if   price >= bb_upper: bb_pos = "ABOVE UPPER BAND (overbought)"
        elif price <= bb_lower: bb_pos = "BELOW LOWER BAND (oversold)"
        elif price >  bb_mid:   bb_pos = "UPPER HALF"
        else:                   bb_pos = "LOWER HALF"

    # ── ATR ───────────────────────────────────────────────────────────────────
    atr = _val(d, "ATRr_") or _val(d, "ATR_")

    # ── Pivot Points (basis harian) ───────────────────────────────────────────
    pivots = compute_pivots(daily_df) if daily_df is not None else {}
    if not pivots:
        # fallback aman: pakai candle sebelumnya pada TF ini + tandai basisnya
        prev = d.iloc[-2]
        pp = (float(prev.high) + float(prev.low) + float(prev.close)) / 3
        pivots = {
            "pivot": round(pp, 4),
            "r1": round(2*pp - float(prev.low), 4),
            "s1": round(2*pp - float(prev.high), 4),
            "r2": round(pp + (float(prev.high)-float(prev.low)), 4),
            "s2": round(pp - (float(prev.high)-float(prev.low)), 4),
            "r3": None, "s3": None,
            "basis": "previous_intraday_candle (fallback)",
        }

    # ── Candle body analysis (3 candle terakhir) ──────────────────────────────
    recent = d.tail(3)
    bullish_candles = int((recent["close"] > recent["open"]).sum())

    return {
        "price": round(price, 4),
        "candles_used": n,
        "trend": {
            "direction": trend,
            "ema20": ema20, "ema50": ema50, "ema200": ema200,
            "price_vs_ema20": round(price - ema20, 4) if ema20 else None,
        },
        "momentum": {
            "rsi": rsi, "rsi_signal": rsi_signal,
            "macd_line": macd_line, "macd_signal": macd_signal,
            "macd_hist": macd_hist, "macd_cross": macd_cross,
            "stochrsi_k": _val(d, "STOCHRSIk_"),
            "stochrsi_d": _val(d, "STOCHRSId_"),
        },
        "volatility": {
            "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
            "bb_position": bb_pos, "atr": atr,
            "bb_width": round(bb_upper - bb_lower, 4) if (bb_upper and bb_lower) else None,
        },
        "support_resistance": pivots,
        "candles": {
            "last_3_bullish": bullish_candles,
            "last_3_bearish": 3 - bullish_candles,
            "last_candle_body": round(abs(float(last["close"]) - float(last["open"])), 4),
            "last_candle_wick_upper": round(float(last["high"]) - max(float(last["open"]), float(last["close"])), 4),
            "last_candle_wick_lower": round(min(float(last["open"]), float(last["close"])) - float(last["low"]), 4),
        },
    }


def compute_multi_tf_bias(df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> str:
    """
    Bandingkan bias 15m vs 1h memakai EMA20/50 (min_periods agar stabil).
    Returns: 'ALIGNED_BULL' | 'ALIGNED_BEAR' | 'CONFLICTING' | 'NEUTRAL'
    """
    def simple_bias(df):
        c   = float(df["close"].iloc[-1])
        e20 = df["close"].ewm(span=20, min_periods=20).mean().iloc[-1]
        e50 = df["close"].ewm(span=50, min_periods=50).mean().iloc[-1]
        if pd.isna(e20) or pd.isna(e50):
            return "NEUTRAL"
        if c > e20 > e50: return "BULL"
        if c < e20 < e50: return "BEAR"
        return "NEUTRAL"

    b15, b1h = simple_bias(df_15m), simple_bias(df_1h)
    if b15 == "BULL" and b1h == "BULL":      return "ALIGNED_BULL"
    if b15 == "BEAR" and b1h == "BEAR":      return "ALIGNED_BEAR"
    if b15 == "NEUTRAL" or b1h == "NEUTRAL": return "NEUTRAL"
    return "CONFLICTING"

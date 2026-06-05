"""
Gold Trading Bot - Data Fetcher
================================
Mengambil data OHLCV dari Binance + berita terbaru dari NewsAPI
"""

import requests
import pandas as pd
from datetime import datetime, timezone
from binance.client import Client
import config
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# BINANCE DATA
# ─────────────────────────────────────────────────────────────────────────────

def get_binance_client() -> Client:
    """Buat koneksi ke Binance."""
    return Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)


def fetch_ohlcv(client: Client, symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    """
    Ambil candle OHLCV dari Binance Futures.
    Returns DataFrame dengan kolom: open, high, low, close, volume, timestamp
    """
    raw = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["timestamp", "open", "high", "low", "close", "volume"]].copy()


def fetch_ticker(client: Client, symbol: str) -> dict:
    """
    Harga terkini + 24h stats. Memakai SATU call (futures_ticker sudah berisi
    lastPrice), jadi tidak perlu futures_symbol_ticker terpisah.
    """
    s = client.futures_ticker(symbol=symbol)
    return {
        "price":        float(s["lastPrice"]),
        "change_pct":   float(s["priceChangePercent"]),
        "high_24h":     float(s["highPrice"]),
        "low_24h":      float(s["lowPrice"]),
        "volume_24h":   float(s["volume"]),
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }


def fetch_open_interest(client: Client, symbol: str) -> dict:
    """Open interest — indikator sentimen futures."""
    try:
        oi = client.futures_open_interest(symbol=symbol)
        return {"open_interest": float(oi["openInterest"])}
    except Exception:
        return {"open_interest": None}


def fetch_funding_rate(client: Client, symbol: str) -> dict:
    """Funding rate 8jam — positif = bullish bias, negatif = bearish."""
    try:
        fr = client.futures_funding_rate(symbol=symbol, limit=1)
        rate = float(fr[0]["fundingRate"]) if fr else 0.0
        return {"funding_rate": rate, "funding_rate_pct": round(rate * 100, 4)}
    except Exception:
        return {"funding_rate": 0.0, "funding_rate_pct": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# NEWS DATA
# ─────────────────────────────────────────────────────────────────────────────

def fetch_gold_news(max_articles: int = 8) -> list[dict]:
    """
    Ambil berita terkini soal gold dari NewsAPI.
    Fallback ke RSS jika NewsAPI key tidak tersedia.
    """
    headlines = []

    # ── NewsAPI ──────────────────────────────────────────────────────────────
    if config.NEWS_API_KEY and config.NEWS_API_KEY != "YOUR_NEWSAPI_KEY":
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q":        "gold price OR XAUUSD OR gold market",
                "sortBy":   "publishedAt",
                "pageSize": max_articles,
                "language": "en",
                "apiKey":   config.NEWS_API_KEY,
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            for art in data.get("articles", []):
                headlines.append({
                    "title":       art.get("title", ""),
                    "description": art.get("description", ""),
                    "source":      art.get("source", {}).get("name", ""),
                    "published":   art.get("publishedAt", ""),
                    "url":         art.get("url", ""),
                })
            logger.info(f"Fetched {len(headlines)} news from NewsAPI")
            return headlines
        except Exception as e:
            logger.warning(f"NewsAPI error: {e}")

    # ── Fallback: RSS (Kitco + Yahoo Finance gold-futures GC=F) ──────────────
    # Catatan: feed Reuters lama (feeds.reuters.com) sudah dimatikan → diganti.
    rss_feeds = [
        "https://www.kitco.com/rss/news.xml",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US",
        "https://www.investing.com/rss/commodities_Gold.rss",
    ]
    for feed_url in rss_feeds:
        try:
            r = requests.get(feed_url, timeout=8,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; GoldBot/1.0)"})
            # parse naif — ambil judul dari <title> tag
            import re
            titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)
            if not titles:
                titles = re.findall(r"<title>(.*?)</title>", r.text)
            for t in titles[1:max_articles+1]:   # skip feed title
                if any(kw in t.lower() for kw in ["gold", "xau", "metal", "fed", "inflat"]):
                    headlines.append({"title": t, "description": "", "source": feed_url, "published": "", "url": ""})
        except Exception:
            pass

    logger.info(f"Fetched {len(headlines)} headlines from RSS fallback")
    return headlines[:max_articles]

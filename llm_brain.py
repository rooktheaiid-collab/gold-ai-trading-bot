"""
Gold Trading Bot - LLM Brain (Provider-Agnostic)
=================================================
Otak utama bot — menerima semua data market + teknikal + berita,
lalu menghasilkan keputusan trading terstruktur.

LLM BEBAS DIGANTI lewat config (LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL).
- provider "openai"   → OpenAI-compatible (OpenAI, OpenRouter, Groq, DeepSeek,
                        Together, Gemini-compat, Ollama/LM Studio lokal, dll)
- provider "anthropic"→ SDK native Anthropic (Claude)
"""

import json
import re
import logging
import config
try:
    import bot_memory as MEM   # self-learning: injects past lessons into prompts
except Exception:
    MEM = None

logger = logging.getLogger(__name__)


def _to_float(v):
    """Coerce nilai LLM ke float dengan aman. Return None kalau gagal.
    Banyak provider (DeepSeek, Llama, Qwen, dll) kadang kirim angka sebagai
    string ("3401.5") atau dengan simbol ("$3,401.5") → tanpa coerce ini,
    aritmetika SL/TP melempar TypeError dan trade gagal diam-diam."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace("$", "").replace(",", "").replace("%", "")
        if s == "" or s.lower() in ("null", "none", "n/a", "na"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _sanitize_decision(d: dict) -> dict:
    """Bersihkan output LLM: coerce angka ke float + normalisasi urutan TP.
    - entry/sl/tp1/tp2/RR/confidence → float (atau None).
    - Untuk LONG pastikan tp1<=tp2; untuk SHORT pastikan tp1>=tp2 (target
      terdekat = TP1). Mencegah partial-TP1 & geser-SL-ke-BE terlewat saat LLM
      membalik urutan TP."""
    for k in ("entry_price", "stop_loss", "take_profit_1", "take_profit_2",
              "risk_reward", "confidence"):
        if k in d:
            d[k] = _to_float(d[k])

    sig = d.get("signal")
    tp1, tp2 = d.get("take_profit_1"), d.get("take_profit_2")
    if tp1 is not None and tp2 is not None and sig in ("LONG", "SHORT"):
        if sig == "LONG" and tp1 > tp2:
            d["take_profit_1"], d["take_profit_2"] = tp2, tp1
            logger.info("[SANITIZE] TP LONG terbalik → ditukar (TP1<=TP2).")
        elif sig == "SHORT" and tp1 < tp2:
            d["take_profit_1"], d["take_profit_2"] = tp2, tp1
            logger.info("[SANITIZE] TP SHORT terbalik → ditukar (TP1>=TP2).")
    return d


# ── Inisialisasi client sesuai provider ──────────────────────────────────────
def _build_client():
    """Bangun client LLM sesuai LLM_PROVIDER. Return (provider, client)."""
    provider = (config.LLM_PROVIDER or "openai").lower()

    if provider == "anthropic":
        import anthropic
        kwargs = {"api_key": config.LLM_API_KEY}
        # base_url opsional — hanya dipakai bila di-set (mis. proxy)
        if config.LLM_BASE_URL and "api.openai.com" not in config.LLM_BASE_URL:
            kwargs["base_url"] = config.LLM_BASE_URL
        logger.info(f"LLM provider=anthropic model={config.LLM_MODEL}")
        return "anthropic", anthropic.Anthropic(**kwargs)

    # default: OpenAI-compatible
    from openai import OpenAI
    logger.info(f"LLM provider=openai base_url={config.LLM_BASE_URL} model={config.LLM_MODEL}")
    return "openai", OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL or None)


LLM_PROVIDER, client_llm = _build_client()


def _call_llm(system_prompt: str, user_message: str) -> str:
    """Panggil LLM (apa pun providernya) dan kembalikan teks mentah jawaban."""
    if LLM_PROVIDER == "anthropic":
        resp = client_llm.messages.create(
            model=config.LLM_MODEL,
            max_tokens=config.LLM_MAX_TOKENS,
            temperature=config.LLM_TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text.strip()

    # OpenAI-compatible
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs = dict(
        model=config.LLM_MODEL,
        messages=messages,
        max_tokens=config.LLM_MAX_TOKENS,
        temperature=config.LLM_TEMPERATURE,
    )
    # Minta output JSON kalau provider mendukung; abaikan kalau ditolak.
    try:
        resp = client_llm.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs
        )
    except Exception as e:
        logger.warning(f"response_format json_object tidak didukung ({str(e)[:80]}); retry tanpa itu.")
        resp = client_llm.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


SYSTEM_PROMPT = """
Kamu adalah AI Trading Analyst spesialis Gold (XAUUSD) berpengalaman 15 tahun.
Kamu menggabungkan analisa teknikal, fundamental, dan sentimen berita untuk menghasilkan
sinyal trading yang presisi.

KEAHLIANMU:
- Multi-timeframe analysis (HTF untuk bias, LTF untuk entry)
- ICT / Smart Money Concepts (Order Blocks, Liquidity, Fair Value Gap)
- Wyckoff Method (Accumulation / Distribution phase)
- Elliott Wave dasar
- Risk Management ketat (RR minimal 1:2)

ATURAN WAJIB:
1. Jangan pernah FOMO — kalau tidak yakin, output HOLD/SKIP
2. Selalu pertimbangkan korelasi: DXY naik → gold cenderung turun
3. Berita high-impact (NFP, CPI, FOMC) = hindari entry baru
4. Funding rate sangat positif = hati-hati LONG (crowded trade)
5. Selalu hitung SL dari ATR (1-1.5x ATR), TP dari pivot / BB / RR 1:3

OUTPUT FORMAT (JSON strict):
{
  "signal": "LONG" | "SHORT" | "HOLD",
  "confidence": 0-100,
  "entry_price": float | null,
  "stop_loss": float | null,
  "take_profit_1": float | null,
  "take_profit_2": float | null,
  "risk_reward": float | null,
  "timeframe": "15m",
  "reasoning": "penjelasan singkat 3-5 kalimat",
  "key_levels": {"support": float, "resistance": float},
  "market_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "news_sentiment": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
  "warnings": ["list of warnings jika ada"],
  "trade_quality": "A+" | "A" | "B" | "C" | "SKIP"
}

Jika trade_quality C atau SKIP, signal harus HOLD.
"""


def analyze_market(
    ticker: dict,
    technicals_15m: dict,
    technicals_1h: dict,
    multi_tf_bias: str,
    funding: dict,
    open_interest: dict,
    news: list[dict],
) -> dict:
    """
    Kirim semua data ke Claude, dapatkan keputusan trading.
    """

    # Format berita
    news_text = ""
    for i, art in enumerate(news[:6], 1):
        news_text += f"{i}. [{art.get('source','')}] {art.get('title','')}"
        if art.get("description"):
            news_text += f" — {art['description'][:120]}"
        news_text += f" ({art.get('published','')[:10]})\n"

    user_message = f"""
=== GOLD TRADING ANALYSIS REQUEST ===
Timestamp: {ticker.get('timestamp')}

📊 MARKET DATA (XAUUSDT Binance Futures):
- Current Price  : ${ticker['price']:,.2f}
- 24h Change     : {ticker['change_pct']}%
- 24h High       : ${ticker['high_24h']:,.2f}
- 24h Low        : ${ticker['low_24h']:,.2f}
- Open Interest  : {open_interest.get('open_interest', 'N/A')}
- Funding Rate   : {funding.get('funding_rate_pct', 'N/A')}%

📈 TECHNICAL — 15 MINUTE TIMEFRAME:
Trend    : {technicals_15m['trend']['direction']}
EMA20    : {technicals_15m['trend']['ema20']} | EMA50: {technicals_15m['trend']['ema50']} | EMA200: {technicals_15m['trend']['ema200']}
ADX(14)  : {technicals_15m['trend'].get('adx')} → {technicals_15m['trend'].get('adx_signal')} (>=25 tren kuat, <20 choppy/range)
RSI(14)  : {technicals_15m['momentum']['rsi']} → {technicals_15m['momentum']['rsi_signal']}
MACD     : Line={technicals_15m['momentum']['macd_line']} Sig={technicals_15m['momentum']['macd_signal']} Hist={technicals_15m['momentum']['macd_hist']} → {technicals_15m['momentum']['macd_cross']}
StochRSI : K={technicals_15m['momentum']['stochrsi_k']} D={technicals_15m['momentum']['stochrsi_d']}
BB       : Upper={technicals_15m['volatility']['bb_upper']} Mid={technicals_15m['volatility']['bb_mid']} Lower={technicals_15m['volatility']['bb_lower']}
BB Pos   : {technicals_15m['volatility']['bb_position']}
ATR(14)  : {technicals_15m['volatility']['atr']}
Pivots   : PP={technicals_15m['support_resistance']['pivot']} R1={technicals_15m['support_resistance']['r1']} S1={technicals_15m['support_resistance']['s1']}
           R2={technicals_15m['support_resistance']['r2']} S2={technicals_15m['support_resistance']['s2']}
Candles  : Bullish={technicals_15m['candles']['last_3_bullish']}/3 | Body={technicals_15m['candles']['last_candle_body']} | Upper Wick={technicals_15m['candles']['last_candle_wick_upper']}

📈 TECHNICAL — 1 HOUR TIMEFRAME:
Trend    : {technicals_1h['trend']['direction']}
ADX(14)  : {technicals_1h['trend'].get('adx')} → {technicals_1h['trend'].get('adx_signal')}
RSI(14)  : {technicals_1h['momentum']['rsi']} → {technicals_1h['momentum']['rsi_signal']}
MACD     : {technicals_1h['momentum']['macd_cross']}
BB Pos   : {technicals_1h['volatility']['bb_position']}

🔀 MULTI-TF BIAS: {multi_tf_bias}

📰 LATEST NEWS (Gold-related):
{news_text if news_text else "No recent news available."}

Berikan analisa dan keputusan trading dalam format JSON yang sudah ditentukan.
"""

    logger.info("Sending market data to LLM for analysis...")

    # Self-learning: tambahkan pelajaran dari evaluasi harian ke system prompt
    sys_prompt = SYSTEM_PROMPT
    if MEM is not None:
        try:
            sys_prompt = SYSTEM_PROMPT + MEM.lessons_prompt_block()
        except Exception:
            pass

    raw = _call_llm(sys_prompt, user_message)

    # Parse JSON dari response
    try:
        # Buang reasoning tag inline (mis. MiniMax-M3 menaruh <think>...</think> di content)
        if "<think>" in raw:
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Ekstrak JSON jika ada markdown code block
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        decision = json.loads(raw)
        decision = _sanitize_decision(decision)   # coerce angka + normalisasi urutan TP
        logger.info(f"LLM Decision: {decision.get('signal')} | Confidence: {decision.get('confidence')}% | Quality: {decision.get('trade_quality')}")
        return decision
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}\nRaw: {raw}")
        return {
            "signal": "HOLD",
            "confidence": 0,
            "reasoning": f"LLM parse error: {str(e)[:100]}",
            "trade_quality": "SKIP",
        }

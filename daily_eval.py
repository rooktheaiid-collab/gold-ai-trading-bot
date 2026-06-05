"""
Daily Evaluation & Self-Learning
================================
At the end of each trading day the bot reviews its OWN trades, computes
performance metrics, and asks the LLM to reflect: what worked, what failed, and
what concrete lessons to apply going forward. The distilled lessons are saved to
bot_memory and automatically injected into every future decision prompt — a
practical "continual learning" loop (prompt/memory-based, no model retraining).
"""
import json
from datetime import datetime, date, timedelta, timezone
import config
import bot_memory as MEM
import llm_brain as BRAIN
import trade_engine as TE


def local_today(tz_offset: int | None = None) -> date:
    off = config.EVAL_TZ_OFFSET_HOURS if tz_offset is None else tz_offset
    return (datetime.now(timezone.utc) + timedelta(hours=off)).date()


REFLECT_SYSTEM = """
Kamu adalah mentor trading & risk manager senior. Tugasmu mengevaluasi performa
trading harian sebuah bot Gold (XAUUSDT) dan menghasilkan PELAJARAN konkret yang
bisa langsung diterapkan untuk memperbaiki keputusan besok. Jujur dan kritis.

Balas HANYA JSON valid dengan struktur:
{
  "ringkasan": "ringkasan performa hari ini 2-3 kalimat",
  "yang_berhasil": ["poin-poin yang berjalan baik"],
  "yang_gagal": ["kesalahan / kelemahan yang terlihat"],
  "pelajaran": [
     {"category": "entry|exit|risk|timing|psikologi|filter", "lesson": "aturan konkret & actionable, 1 kalimat"}
  ],
  "skor_disiplin": 0-100
}
Pelajaran harus spesifik & bisa dieksekusi (mis. "Hindari SHORT saat RSI 1H < 30
karena rawan pantulan"), bukan klise. Maksimal 5 pelajaran terbaik.
"""


def _trades_on(day: date, trade_log: list, tz_offset: int = 0) -> list:
    """Trades closed on `day` (local date, converting UTC timestamps by tz_offset)."""
    out = []
    for ev in trade_log:
        c = ev.get("closed") or ev.get("time") or ""
        try:
            dt = datetime.fromisoformat(str(c).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            d = (dt + timedelta(hours=tz_offset)).date()
        except Exception:
            continue
        if d == day:
            out.append(ev)
    return out


def compute_metrics(trades: list) -> dict:
    pnls = [(t.get("pnl") or t.get("pnl_final_leg") or 0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = sum(pnls)
    best = max(pnls) if pnls else 0
    worst = min(pnls) if pnls else 0
    return dict(
        n_trades=len(trades),
        wins=len(wins), losses=len(losses),
        winrate=round(len(wins)/len(trades)*100, 1) if trades else 0,
        net_pnl=round(total, 2),
        best=round(best, 2), worst=round(worst, 2),
        avg_win=round(sum(wins)/len(wins), 2) if wins else 0,
        avg_loss=round(sum(losses)/len(losses), 2) if losses else 0,
    )


def evaluate_day(day: date | None = None, send_fn=None, tz_offset: int | None = None,
                 persist: bool = True) -> dict:
    """Run the daily evaluation. `send_fn(text)` optionally pushes report to Telegram.
    persist=False → mode preview (tidak menyimpan pelajaran/record; untuk tombol on-demand).
    """
    off = config.EVAL_TZ_OFFSET_HOURS if tz_offset is None else tz_offset
    day = day or local_today(off)
    trades = _trades_on(day, TE.paper_state.get("trade_log", []), tz_offset=off)
    metrics = compute_metrics(trades)

    # Ask the LLM to reflect (skip if no trades — still record a no-trade note)
    reflection = {}
    if trades:
        payload = json.dumps(dict(tanggal=str(day), metrik=metrics,
                                  trades=[{k: t.get(k) for k in
                                           ("side", "entry", "exit", "reason",
                                            "pnl", "pnl_final_leg", "quality")}
                                          for t in trades]),
                             ensure_ascii=False, default=str)
        raw = BRAIN._call_llm(REFLECT_SYSTEM,
                              f"Evaluasi performa trading hari {day}:\n{payload}")
        reflection = BRAIN._extract_json(raw) if hasattr(BRAIN, "_extract_json") else _safe_json(raw)
    else:
        reflection = {"ringkasan": f"Tidak ada trade pada {day}. Bot menjaga modal (no-trade day).",
                      "yang_berhasil": ["Disiplin tidak overtrading"],
                      "yang_gagal": [], "pelajaran": [], "skor_disiplin": 100}

    lessons = reflection.get("pelajaran", []) or []
    if persist:
        MEM.add_lessons(lessons, str(day))

    ev = dict(date=str(day), metrics=metrics, reflection=reflection,
              n_lessons_total=len(MEM.load_lessons()),
              preview=(not persist),
              created=datetime.now(timezone.utc).isoformat())
    if persist:
        MEM.log_evaluation(ev)

    report = build_eval_report(ev)
    if send_fn:
        send_fn(report)
    return ev


def _safe_json(raw: str) -> dict:
    import re
    s = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    m = re.search(r"\{.*\}", s, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {"ringkasan": raw[:200], "pelajaran": []}


def build_eval_report(ev: dict) -> str:
    m = ev["metrics"]; r = ev.get("reflection", {})
    lines = [f"📅 *EVALUASI HARIAN — {ev['date']}*",
             f"Trade: {m['n_trades']} | Menang {m['wins']}/{m['losses']} | WR {m['winrate']}%",
             f"PnL hari ini: `{m['net_pnl']:+.2f} USDT` | Terbaik `{m['best']:+.2f}` Terburuk `{m['worst']:+.2f}`",
             f"Skor disiplin: *{r.get('skor_disiplin','-')}*",
             "",
             f"📝 {r.get('ringkasan','')}"]
    if r.get("yang_berhasil"):
        lines.append("\n✅ *Yang berhasil:*")
        lines += [f"• {x}" for x in r["yang_berhasil"][:4]]
    if r.get("yang_gagal"):
        lines.append("\n⚠️ *Yang perlu diperbaiki:*")
        lines += [f"• {x}" for x in r["yang_gagal"][:4]]
    if r.get("pelajaran"):
        lines.append("\n🧠 *Pelajaran baru (disimpan ke memori):*")
        lines += [f"• [{l.get('category','')}] {l.get('lesson','')}" for l in r["pelajaran"][:5]]
    lines.append(f"\n_Total pelajaran di memori bot: {ev['n_lessons_total']}_")
    return "\n".join(lines)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(evaluate_day(), indent=2, ensure_ascii=False, default=str))

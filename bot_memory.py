"""
Bot Memory — persistent self-learning store.
============================================
Holds the distilled "lessons" the bot has learned from evaluating its own past
trades, plus the full daily-evaluation history. Kept dependency-free so BOTH
llm_brain.py (reads lessons to inject into prompts) and daily_eval.py (writes
new lessons) can import it without a circular import.

Files (created automatically):
  bot_memory/lessons.json      - cumulative distilled lessons (capped)
  bot_memory/evaluations.json  - full daily evaluation records
"""
import os, json, threading

# Lindungi operasi read-modify-write dari race antara thread Telegram & loop utama.
_LOCK = threading.RLock()

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_memory")
LESSONS_PATH = os.path.join(_DIR, "lessons.json")
EVAL_PATH    = os.path.join(_DIR, "evaluations.json")
MAX_LESSONS  = 40   # keep the most recent N lessons in active memory


def _ensure():
    os.makedirs(_DIR, exist_ok=True)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_dump(path, data):
    """Write JSON atomically (tmp + os.replace) to avoid corruption on crash."""
    _ensure()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def load_lessons() -> list:
    """Return list of lesson dicts: {date, category, lesson}."""
    return _read(LESSONS_PATH, [])


def save_lessons(lessons: list):
    _atomic_dump(LESSONS_PATH, lessons[-MAX_LESSONS:])


def add_lessons(new_lessons: list, date: str):
    """Merge new lessons (list of str or dict), dedupe by text, cap to MAX_LESSONS."""
    with _LOCK:   # serialize read-modify-write (cegah lost update antar-thread)
        cur = load_lessons()
        seen = {l["lesson"].strip().lower() for l in cur if l.get("lesson")}
        for nl in new_lessons:
            if isinstance(nl, dict):
                text = (nl.get("lesson") or "").strip()
                cat = nl.get("category", "umum")
            else:
                text = str(nl).strip(); cat = "umum"
            if text and text.lower() not in seen:
                cur.append({"date": date, "category": cat, "lesson": text})
                seen.add(text.lower())
        save_lessons(cur)
        return load_lessons()


def lessons_prompt_block() -> str:
    """Formatted block injected into the LLM system prompt each decision."""
    lessons = load_lessons()
    if not lessons:
        return ""
    lines = ["\n=== PELAJARAN DARI PENGALAMAN TRADING SEBELUMNYA ===",
             "Terapkan pelajaran berikut (hasil evaluasi performa bot sendiri):"]
    for i, l in enumerate(lessons[-MAX_LESSONS:], 1):
        lines.append(f"{i}. [{l.get('category','umum')}] {l.get('lesson','')}")
    lines.append("Pertimbangkan pelajaran ini saat menilai setup saat ini.\n")
    return "\n".join(lines)


def log_evaluation(ev: dict):
    with _LOCK:   # serialize read-modify-write
        hist = _read(EVAL_PATH, [])
        hist.append(ev)
        _atomic_dump(EVAL_PATH, hist)


def list_evaluations() -> list:
    return _read(EVAL_PATH, [])
